from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
import uuid


class InstrumentType(str, Enum):
    INDEX = "INDEX"
    EQUITY = "EQUITY"
    FUTURES = "FUTURES"
    OPTION_CE = "OPTION_CE"
    OPTION_PE = "OPTION_PE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_LOSS = "STOP_LOSS"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"


class PositionStatus(str, Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class PositionDirection(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class DecisionAction(str, Enum):
    NO_TRADE = "NO_TRADE"
    ENTER_LONG = "ENTER_LONG"
    ENTER_SHORT = "ENTER_SHORT"
    EXIT = "EXIT"
    HOLD = "HOLD"
    PAUSE_TRADING = "PAUSE_TRADING"


class LedgerTxType(str, Enum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"
    MARGIN_HOLD = "MARGIN_HOLD"
    MARGIN_RELEASE = "MARGIN_RELEASE"
    TRADE_PNL = "TRADE_PNL"
    FEE = "FEE"


class Tick(BaseModel):
    instrument: str
    timestamp: datetime
    ltp: float
    volume: int = 0
    open_interest: int = 0
    bid: float = 0.0
    ask: float = 0.0
    bid_qty: int = 0
    ask_qty: int = 0


class Candle(BaseModel):
    instrument: str
    timeframe: str = "1m"
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
    open_interest: int = 0


class OptionContract(BaseModel):
    symbol: str
    underlying: str
    strike: float
    expiry: str
    option_type: InstrumentType  # OPTION_CE or OPTION_PE
    lot_size: int
    ltp: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    iv: float = 0.0
    delta: float = 0.0
    gamma: float = 0.0
    theta: float = 0.0
    vega: float = 0.0
    open_interest: int = 0
    volume: int = 0


class Order(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    position_id: Optional[str] = None
    decision_id: Optional[str] = None
    instrument: str
    side: OrderSide
    order_type: OrderType
    price: float
    quantity: int
    status: OrderStatus = OrderStatus.PENDING
    slippage_paid: float = 0.0
    fee_incurred: float = 0.0
    rejection_reason: Optional[str] = None
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None


class Position(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    instrument: str
    underlying: str
    direction: PositionDirection
    quantity: int
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    capital_allocated: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    status: PositionStatus = PositionStatus.OPEN
    exit_reason: Optional[str] = None
    opened_at: datetime = Field(default_factory=datetime.utcnow)
    closed_at: Optional[datetime] = None


class LedgerTransaction(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tx_type: LedgerTxType
    amount: float
    balance_after: float
    idempotency_key: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    instrument: str
    action: DecisionAction
    raw_confidence: float
    calibrated_probability: float
    expected_value_r: float
    regime: str
    features: Dict[str, Any] = Field(default_factory=dict)
    veto_reason: Optional[str] = None
    rationale: str = ""
