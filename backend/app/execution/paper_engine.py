import uuid
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import PositionDB, OrderDB
from app.models.domain import (
    Order, Position, OrderStatus, PositionStatus, OrderSide, PositionDirection
)
from app.risk.formulas import calculate_slippage, calculate_indian_fo_taxes
from app.execution.ledger import DoubleEntryLedger


class PaperExecutionEngine:
    """
    Simulated order fill engine featuring realistic slippage, regulatory Indian F&O fees,
    and double-entry ledger settlement.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.ledger = DoubleEntryLedger(session)

    async def execute_entry_order(
        self,
        order: Order,
        bid: float,
        ask: float,
        stop_loss: float,
        take_profit: float,
        underlying: str,
        account_id: str = "default_user",
        depth_vol: int = 500
    ) -> tuple[Optional[PositionDB], OrderDB]:
        """
        Executes a paper order to open a new position.
        """
        fill_price = calculate_slippage(
            order_price=order.price,
            quantity=order.quantity,
            bid=bid,
            ask=ask,
            order_side=order.side.value,
            depth_vol=depth_vol
        )
        slippage_paid = round(abs(fill_price - order.price) * order.quantity, 2)
        total_order_cost = round(fill_price * order.quantity, 2)

        # Estimate entry transaction fee (Brokerage ₹20 + Turnover + GST + Stamp Duty)
        tax_breakdown = calculate_indian_fo_taxes(
            entry_price=fill_price,
            exit_price=fill_price,
            quantity=order.quantity,
            is_option=True
        )
        entry_fee = round(tax_breakdown["total_friction"] * 0.5, 2)

        # Reserve margin in ledger
        margin_reserved = await self.ledger.reserve_margin(
            account_id=account_id,
            amount=total_order_cost,
            order_id=order.id
        )
        if not margin_reserved:
            order.status = OrderStatus.REJECTED
            order.rejection_reason = "Insufficient funds to reserve margin"
            order_db = OrderDB(
                id=order.id,
                decision_id=order.decision_id,
                instrument=order.instrument,
                side=order.side.value,
                order_type=order.order_type.value,
                price=order.price,
                quantity=order.quantity,
                status=OrderStatus.REJECTED.value,
                rejection_reason=order.rejection_reason
            )
            self.session.add(order_db)
            await self.session.commit()
            return None, order_db

        # Order filled
        order.status = OrderStatus.FILLED
        order.executed_at = datetime.utcnow()
        order.slippage_paid = slippage_paid
        order.fee_incurred = entry_fee

        order_db = OrderDB(
            id=order.id,
            position_id=order.position_id,
            decision_id=order.decision_id,
            instrument=order.instrument,
            side=order.side.value,
            order_type=order.order_type.value,
            price=fill_price,
            quantity=order.quantity,
            status=OrderStatus.FILLED.value,
            slippage_paid=slippage_paid,
            fee_incurred=entry_fee,
            submitted_at=order.submitted_at,
            executed_at=order.executed_at
        )
        self.session.add(order_db)

        # Create Open Position
        pos_id = str(uuid.uuid4())
        order_db.position_id = pos_id

        position_db = PositionDB(
            id=pos_id,
            account_id=account_id,
            instrument=order.instrument,
            underlying=underlying,
            direction=PositionDirection.LONG.value if order.side == OrderSide.BUY else PositionDirection.SHORT.value,
            quantity=order.quantity,
            entry_price=fill_price,
            current_price=fill_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            capital_allocated=total_order_cost,
            unrealized_pnl=0.0,
            realized_pnl=0.0,
            total_fees=entry_fee,
            status=PositionStatus.OPEN.value,
            opened_at=datetime.utcnow()
        )
        self.session.add(position_db)
        await self.session.commit()
        await self.session.refresh(position_db)
        return position_db, order_db

    async def execute_exit_order(
        self,
        position: PositionDB,
        bid: float,
        ask: float,
        exit_reason: str,
        account_id: str = "default_user",
        depth_vol: int = 500
    ) -> OrderDB:
        """
        Executes a paper exit order, liquidates position, settles P&L and fees in ledger.
        """
        exit_side = OrderSide.SELL if position.direction == PositionDirection.LONG.value else OrderSide.BUY
        fill_price = calculate_slippage(
            order_price=position.current_price,
            quantity=position.quantity,
            bid=bid,
            ask=ask,
            order_side=exit_side.value,
            depth_vol=depth_vol
        )

        # Compute full round-trip taxes
        tax_info = calculate_indian_fo_taxes(
            entry_price=position.entry_price,
            exit_price=fill_price,
            quantity=position.quantity,
            is_option=True
        )
        total_fees = tax_info["total_friction"]

        # Gross P&L
        if position.direction == PositionDirection.LONG.value:
            gross_pnl = (fill_price - position.entry_price) * position.quantity
        else:
            gross_pnl = (position.entry_price - fill_price) * position.quantity

        gross_pnl = round(gross_pnl, 2)
        net_pnl = round(gross_pnl - total_fees, 2)

        # Release reserved margin and settle PnL
        await self.ledger.release_margin(
            account_id=account_id,
            amount=position.capital_allocated,
            order_id=position.id
        )
        await self.ledger.settle_trade(
            account_id=account_id,
            realized_pnl=gross_pnl,
            fees=total_fees,
            position_id=position.id
        )

        # Update position record
        position.current_price = fill_price
        position.status = PositionStatus.CLOSED.value
        position.realized_pnl = net_pnl
        position.unrealized_pnl = 0.0
        position.total_fees = total_fees
        position.exit_reason = exit_reason
        position.closed_at = datetime.utcnow()

        exit_order = OrderDB(
            id=str(uuid.uuid4()),
            position_id=position.id,
            instrument=position.instrument,
            side=exit_side.value,
            order_type="MARKET",
            price=fill_price,
            quantity=position.quantity,
            status=OrderStatus.FILLED.value,
            fee_incurred=total_fees,
            executed_at=datetime.utcnow()
        )
        self.session.add(exit_order)
        await self.session.commit()
        return exit_order
