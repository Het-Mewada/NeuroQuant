from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.core.state_machine import market_lifecycle
from app.models.database import AccountDB, PositionDB
from app.models.domain import Order, PositionStatus


class RiskEngineGate:
    """
    Deterministic capital safety engine.
    Has absolute veto authority over the Decision Engine and Machine Learning signals.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.is_circuit_breaker_tripped: bool = False
        self.circuit_breaker_reason: Optional[str] = None

    async def evaluate_order_proposal(
        self,
        order: Order,
        stop_loss: float,
        target: float,
        account_id: str = "default_user"
    ) -> tuple[bool, Optional[str]]:
        """
        Runs exhaustive pre-trade risk checks. Returns (Approved: bool, Reason: str).
        """
        # 1. Circuit Breaker Check
        if self.is_circuit_breaker_tripped:
            return False, f"TRADING HALTED: Circuit breaker is active ({self.circuit_breaker_reason})"

        # 2. Market Schedule Check
        can_trade, schedule_msg = market_lifecycle.can_open_new_position()
        if not can_trade:
            return False, f"Schedule rejection: {schedule_msg}"

        # 3. Account Health & Daily Drawdown Check
        acc_result = await self.session.execute(select(AccountDB).where(AccountDB.id == account_id))
        account = acc_result.scalars().first()
        if not account:
            return False, "Account record missing in ledger."

        # Fetch open positions
        pos_result = await self.session.execute(
            select(PositionDB).where(
                PositionDB.account_id == account_id,
                PositionDB.status == PositionStatus.OPEN.value
            )
        )
        open_positions = pos_result.scalars().all()

        # Check concurrent positions limit
        if len(open_positions) >= settings.MAX_CONCURRENT_POSITIONS:
            return False, f"Maximum concurrent positions ({settings.MAX_CONCURRENT_POSITIONS}) reached."

        # Check total unrealized PnL + daily loss
        total_open_unrealized = sum(p.unrealized_pnl for p in open_positions)
        effective_equity = account.total_equity + total_open_unrealized
        daily_loss_threshold = account.total_equity * (settings.MAX_DAILY_LOSS_PCT / 100.0)

        # Total open risk
        if total_open_unrealized < -daily_loss_threshold:
            self.trip_circuit_breaker(
                f"Open drawdown (-₹{abs(total_open_unrealized):,.2f}) exceeded daily limit of ₹{daily_loss_threshold:,.2f}"
            )
            return False, self.circuit_breaker_reason

        # 4. Cash and Margin Availability Check
        order_cost = order.price * order.quantity
        if account.available_cash < order_cost:
            return False, f"Insufficient available cash: Required ₹{order_cost:,.2f}, Available: ₹{account.available_cash:,.2f}"

        # 5. Risk-Reward Ratio Sanity Check
        per_unit_risk = abs(order.price - stop_loss)
        per_unit_reward = abs(target - order.price)
        if per_unit_risk <= 0.05:
            return False, "Invalid stop loss: Risk distance is near zero."

        rr_ratio = per_unit_reward / per_unit_risk
        if rr_ratio < settings.MIN_REWARD_RISK_RATIO:
            return False, f"Reward-to-risk ({rr_ratio:.2f}) is below minimum acceptable {settings.MIN_REWARD_RISK_RATIO}:1"

        # 6. Single-Trade Maximum Capital Risk Check
        trade_risk_rupees = per_unit_risk * order.quantity
        max_allowed_trade_risk = account.total_equity * (settings.MAX_TRADE_RISK_PCT / 100.0)
        if trade_risk_rupees > max_allowed_trade_risk * 1.25:
            return False, f"Single-trade risk (₹{trade_risk_rupees:,.2f}) exceeds max allowed (₹{max_allowed_trade_risk:,.2f})"

        return True, "Risk checks passed successfully."

    def trip_circuit_breaker(self, reason: str):
        self.is_circuit_breaker_tripped = True
        self.circuit_breaker_reason = reason

    def reset_circuit_breaker(self):
        self.is_circuit_breaker_tripped = False
        self.circuit_breaker_reason = None
