import json
from datetime import datetime
from sqlalchemy import (
    Column, String, Float, Integer, DateTime, Text, Boolean, ForeignKey
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

Base = declarative_base()


class AccountDB(Base):
    __tablename__ = "virtual_accounts"

    id = Column(String(36), primary_key=True)
    total_equity = Column(Float, nullable=False, default=500000.0)
    available_cash = Column(Float, nullable=False, default=500000.0)
    reserved_margin = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), default="INR")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class LedgerTransactionDB(Base):
    __tablename__ = "ledger_transactions"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), ForeignKey("virtual_accounts.id"), nullable=False)
    tx_type = Column(String(32), nullable=False)
    amount = Column(Float, nullable=False)
    balance_after = Column(Float, nullable=False)
    idempotency_key = Column(String(64), unique=True, nullable=False, index=True)
    metadata_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class PositionDB(Base):
    __tablename__ = "positions"

    id = Column(String(36), primary_key=True)
    account_id = Column(String(36), ForeignKey("virtual_accounts.id"), nullable=False)
    instrument = Column(String(64), nullable=False, index=True)
    underlying = Column(String(32), nullable=False)
    direction = Column(String(16), nullable=False)
    quantity = Column(Integer, nullable=False)
    entry_price = Column(Float, nullable=False)
    current_price = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    capital_allocated = Column(Float, nullable=False)
    unrealized_pnl = Column(Float, default=0.0)
    realized_pnl = Column(Float, default=0.0)
    total_fees = Column(Float, default=0.0)
    status = Column(String(16), default="OPEN", index=True)
    exit_reason = Column(String(128), nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)


class OrderDB(Base):
    __tablename__ = "orders"

    id = Column(String(36), primary_key=True)
    position_id = Column(String(36), nullable=True)
    decision_id = Column(String(36), nullable=True)
    instrument = Column(String(64), nullable=False, index=True)
    side = Column(String(16), nullable=False)
    order_type = Column(String(16), nullable=False)
    price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    status = Column(String(16), default="PENDING", index=True)
    slippage_paid = Column(Float, default=0.0)
    fee_incurred = Column(Float, default=0.0)
    rejection_reason = Column(String(256), nullable=True)
    submitted_at = Column(DateTime, default=datetime.utcnow, index=True)
    executed_at = Column(DateTime, nullable=True)


class DecisionDB(Base):
    __tablename__ = "decisions"

    id = Column(String(36), primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    instrument = Column(String(64), nullable=False, index=True)
    action = Column(String(32), nullable=False)
    raw_confidence = Column(Float, nullable=False)
    calibrated_probability = Column(Float, nullable=False)
    expected_value_r = Column(Float, nullable=False)
    regime = Column(String(32), nullable=False)
    features_json = Column(Text, default="{}")
    veto_reason = Column(String(256), nullable=True)
    rationale = Column(Text, default="")


class CounterfactualDB(Base):
    __tablename__ = "counterfactual_trades"

    id = Column(String(36), primary_key=True)
    decision_id = Column(String(36), nullable=False, index=True)
    instrument = Column(String(64), nullable=False)
    shadow_entry_price = Column(Float, nullable=False)
    shadow_exit_price = Column(Float, nullable=True)
    hypothetical_pnl = Column(Float, nullable=True)
    hypothetical_pnl_pct = Column(Float, nullable=True)
    tracking_duration_sec = Column(Integer, default=0)
    evaluated_at = Column(DateTime, default=datetime.utcnow, index=True)


class CandleDB(Base):
    __tablename__ = "market_candles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    instrument = Column(String(64), nullable=False, index=True)
    timeframe = Column(String(8), default="1m", index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, default=0)
    open_interest = Column(Integer, default=0)


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
