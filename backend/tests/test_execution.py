from datetime import datetime
import zoneinfo
import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.models.database import Base, AccountDB, PositionDB, OrderDB
from app.models.domain import Order, OrderSide, OrderType, PositionStatus
from app.execution.ledger import DoubleEntryLedger
from app.execution.paper_engine import PaperExecutionEngine
from app.execution.position_manager import PositionManager
from app.risk.engine import RiskEngineGate


@pytest.fixture
async def test_session():
    # Use in-memory SQLite for high-speed isolated test execution
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with Session() as session:
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_full_trade_lifecycle_and_ledger_invariants(test_session):
    ledger = DoubleEntryLedger(test_session)
    exec_engine = PaperExecutionEngine(test_session)
    pos_manager = PositionManager(test_session)

    # Simulated active market time: Wednesday 10:30 AM IST
    ist_tz = zoneinfo.ZoneInfo("Asia/Kolkata")
    active_mkt_time = datetime(2026, 10, 28, 10, 30, tzinfo=ist_tz)

    # 1. Initialize account with ₹5,00,000
    account = await ledger.get_or_create_account("test_user")
    assert account.available_cash == 500000.0
    assert account.total_equity == 500000.0
    assert account.reserved_margin == 0.0

    # 2. Submit Buy Order for Nifty 24500 CE (50 units @ ₹120.0)
    order = Order(
        instrument="NIFTY_24500_CE",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=120.0,
        quantity=50
    )

    pos_db, order_db = await exec_engine.execute_entry_order(
        order=order,
        bid=119.5,
        ask=120.5,
        stop_loss=100.0,
        take_profit=150.0,
        underlying="NIFTY",
        account_id="test_user"
    )

    assert pos_db is not None
    assert pos_db.status == PositionStatus.OPEN.value
    # Reserved margin should equal allocated capital
    await test_session.refresh(account)
    assert account.reserved_margin == pos_db.capital_allocated
    assert account.available_cash == 500000.0 - pos_db.capital_allocated

    # 3. Mark to Market: Price rises to ₹140.0 during active market hours
    updates = await pos_manager.update_mark_to_market(
        instrument="NIFTY_24500_CE",
        current_ltp=140.0,
        bid=139.5,
        ask=140.5,
        account_id="test_user",
        current_dt=active_mkt_time
    )
    assert len(updates) > 0
    await test_session.refresh(pos_db)
    assert pos_db.unrealized_pnl > 0

    # 4. Take Profit triggered: Price hits ₹152.0 (Target was 150.0)
    exit_updates = await pos_manager.update_mark_to_market(
        instrument="NIFTY_24500_CE",
        current_ltp=152.0,
        bid=151.5,
        ask=152.5,
        account_id="test_user",
        current_dt=active_mkt_time
    )
    assert any(u.get("action") == "EXITED_TP" for u in exit_updates)

    # 5. Verify ledger post-trade settlement
    await test_session.refresh(account)
    await test_session.refresh(pos_db)
    assert pos_db.status == PositionStatus.CLOSED.value
    assert pos_db.realized_pnl > 0.0
    assert account.reserved_margin == 0.0  # All margin must be completely released!
    assert account.total_equity > 500000.0  # Profitable trade increased total equity
    assert round(account.total_equity, 2) == round(account.available_cash, 2)

