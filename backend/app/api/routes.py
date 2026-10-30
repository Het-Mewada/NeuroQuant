from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.models.database import (
    AsyncSessionLocal, AccountDB, PositionDB, OrderDB, DecisionDB, LedgerTransactionDB, CounterfactualDB
)
from app.models.domain import PositionStatus
from app.execution.position_manager import PositionManager
from app.execution.ledger import DoubleEntryLedger
from app.core.state_machine import market_lifecycle
from app.data.live_feed import live_feed

router = APIRouter(prefix="/api/v1")


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class CapitalActionRequest(BaseModel):
    amount: float
    account_id: str = "default_user"


class ManualExitRequest(BaseModel):
    account_id: str = "default_user"


@router.get("/summary")
async def get_account_summary(db: AsyncSession = Depends(get_db)):
    ledger = DoubleEntryLedger(db)
    account = await ledger.get_or_create_account("default_user")

    # Fetch open positions
    pos_res = await db.execute(
        select(PositionDB).where(
            PositionDB.account_id == "default_user",
            PositionDB.status == PositionStatus.OPEN.value
        )
    )
    open_positions = pos_res.scalars().all()
    unrealized_pnl = sum(p.unrealized_pnl for p in open_positions)

    # Fetch closed positions for total realized P&L
    closed_res = await db.execute(
        select(PositionDB).where(
            PositionDB.account_id == "default_user",
            PositionDB.status == PositionStatus.CLOSED.value
        )
    )
    closed_positions = closed_res.scalars().all()
    realized_pnl = sum(p.realized_pnl for p in closed_positions)

    market_state = market_lifecycle.determine_state()

    return {
        "account_id": account.id,
        "total_equity": round(account.total_equity + unrealized_pnl, 2),
        "available_cash": round(account.available_cash, 2),
        "reserved_margin": round(account.reserved_margin, 2),
        "unrealized_pnl": round(unrealized_pnl, 2),
        "realized_pnl": round(realized_pnl, 2),
        "open_positions_count": len(open_positions),
        "market_state": market_state.value,
        "currency": account.currency,
        "nifty_spot": live_feed.spots.get("NIFTY", 22936.75),
        "banknifty_spot": live_feed.spots.get("BANKNIFTY", 54909.65)
    }


@router.get("/positions/active")
async def get_active_positions(db: AsyncSession = Depends(get_db)):
    pos_res = await db.execute(
        select(PositionDB).where(
            PositionDB.account_id == "default_user",
            PositionDB.status == PositionStatus.OPEN.value
        ).order_by(desc(PositionDB.opened_at))
    )
    positions = pos_res.scalars().all()
    return positions


@router.get("/positions/history")
async def get_positions_history(limit: int = 50, db: AsyncSession = Depends(get_db)):
    pos_res = await db.execute(
        select(PositionDB).where(
            PositionDB.account_id == "default_user",
            PositionDB.status == PositionStatus.CLOSED.value
        ).order_by(desc(PositionDB.closed_at)).limit(limit)
    )
    return pos_res.scalars().all()


@router.post("/positions/{position_id}/exit")
async def manual_exit_position(
    position_id: str,
    req: ManualExitRequest,
    db: AsyncSession = Depends(get_db)
):
    manager = PositionManager(db)
    pos_res = await db.execute(select(PositionDB).where(PositionDB.id == position_id))
    pos = pos_res.scalars().first()
    if not pos:
        raise HTTPException(status_code=404, detail="Position not found")

    # In paper simulation, use current price as reference
    bid = max(0.05, pos.current_price - 0.5)
    ask = pos.current_price + 0.5
    success, msg = await manager.manual_exit_position(position_id, bid, ask, req.account_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"status": "SUCCESS", "message": msg}


@router.post("/capital/deposit")
async def deposit_capital(req: CapitalActionRequest, db: AsyncSession = Depends(get_db)):
    ledger = DoubleEntryLedger(db)
    try:
        tx = await ledger.deposit(req.account_id, req.amount)
        return {
            "status": "SUCCESS",
            "transaction_id": tx.id,
            "new_balance": tx.balance_after
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/capital/withdraw")
async def withdraw_capital(req: CapitalActionRequest, db: AsyncSession = Depends(get_db)):
    ledger = DoubleEntryLedger(db)
    try:
        tx = await ledger.withdraw(req.account_id, req.amount)
        return {
            "status": "SUCCESS",
            "transaction_id": tx.id,
            "new_balance": tx.balance_after
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/decisions")
async def get_decisions(limit: int = 50, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(DecisionDB).order_by(desc(DecisionDB.timestamp)).limit(limit)
    )
    return res.scalars().all()


@router.get("/ledger")
async def get_ledger_history(limit: int = 100, db: AsyncSession = Depends(get_db)):
    res = await db.execute(
        select(LedgerTransactionDB).order_by(desc(LedgerTransactionDB.created_at)).limit(limit)
    )
    return res.scalars().all()


@router.get("/options/chain")
async def get_options_chain(underlying: str = "NIFTY"):
    underlying = underlying.upper()
    if underlying not in ["NIFTY", "BANKNIFTY"]:
        raise HTTPException(status_code=400, detail="Invalid underlying index")
    chain = live_feed.generate_option_chain(underlying, num_strikes=5)
    return {
        "underlying": underlying,
        "spot": live_feed.spots[underlying],
        "vix": live_feed.vix,
        "chain": [c.model_dump() for c in chain]
    }
