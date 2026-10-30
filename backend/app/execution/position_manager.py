from datetime import datetime
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import PositionDB
from app.models.domain import PositionStatus, PositionDirection
from app.execution.paper_engine import PaperExecutionEngine
from app.core.state_machine import market_lifecycle


class PositionManager:
    """
    Tracks and manages active positions, mark-to-market updates,
    trailing stop-loss evaluation, and autonomous/manual exits.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        self.engine = PaperExecutionEngine(session)

    async def get_open_positions(self, account_id: str = "default_user") -> List[PositionDB]:
        result = await self.session.execute(
            select(PositionDB).where(
                PositionDB.account_id == account_id,
                PositionDB.status == PositionStatus.OPEN.value
            )
        )
        return list(result.scalars().all())

    async def update_mark_to_market(
        self,
        instrument: str,
        current_ltp: float,
        bid: float,
        ask: float,
        account_id: str = "default_user",
        current_dt: Optional[datetime] = None
    ) -> List[dict]:
        """
        Updates unrealized PnL for matching positions and triggers autonomous exits if SL/TP hit.
        """
        open_positions = await self.get_open_positions(account_id)
        updates = []

        for pos in open_positions:
            if pos.instrument != instrument:
                continue

            pos.current_price = current_ltp
            if pos.direction == PositionDirection.LONG.value:
                pos.unrealized_pnl = round((current_ltp - pos.entry_price) * pos.quantity, 2)
            else:
                pos.unrealized_pnl = round((pos.entry_price - current_ltp) * pos.quantity, 2)

            # 1. Stop-Loss check
            sl_hit = False
            if pos.direction == PositionDirection.LONG.value and current_ltp <= pos.stop_loss:
                sl_hit = True
            elif pos.direction == PositionDirection.SHORT.value and current_ltp >= pos.stop_loss:
                sl_hit = True

            if sl_hit:
                await self.engine.execute_exit_order(
                    position=pos,
                    bid=bid,
                    ask=ask,
                    exit_reason=f"Autonomous Stop-Loss triggered at {current_ltp:.2f} (SL: {pos.stop_loss:.2f})",
                    account_id=pos.account_id
                )
                updates.append({"position_id": pos.id, "action": "EXITED_SL", "price": current_ltp})
                continue

            # 2. Take-Profit check
            tp_hit = False
            if pos.direction == PositionDirection.LONG.value and current_ltp >= pos.take_profit:
                tp_hit = True
            elif pos.direction == PositionDirection.SHORT.value and current_ltp <= pos.take_profit:
                tp_hit = True

            if tp_hit:
                await self.engine.execute_exit_order(
                    position=pos,
                    bid=bid,
                    ask=ask,
                    exit_reason=f"Autonomous Take-Profit triggered at {current_ltp:.2f} (TP: {pos.take_profit:.2f})",
                    account_id=pos.account_id
                )
                updates.append({"position_id": pos.id, "action": "EXITED_TP", "price": current_ltp})
                continue

            # 3. Market Session Auto Square-Off Check (15:15 IST)
            if market_lifecycle.should_force_exit_intraday(current_dt):
                await self.engine.execute_exit_order(
                    position=pos,
                    bid=bid,
                    ask=ask,
                    exit_reason="Autonomous EOD Market Square-Off (15:15 IST reached)",
                    account_id=pos.account_id
                )
                updates.append({"position_id": pos.id, "action": "EXITED_EOD_SQUAREOFF", "price": current_ltp})
                continue

            updates.append({"position_id": pos.id, "action": "MTM_UPDATE", "unrealized_pnl": pos.unrealized_pnl})

        await self.session.commit()
        return updates

    async def manual_exit_position(
        self,
        position_id: str,
        bid: float,
        ask: float,
        account_id: str = "default_user"
    ) -> tuple[bool, str]:
        """
        Manually liquidates an open position on demand from the dashboard.
        """
        result = await self.session.execute(
            select(PositionDB).where(
                PositionDB.id == position_id,
                PositionDB.account_id == account_id,
                PositionDB.status == PositionStatus.OPEN.value
            )
        )
        pos = result.scalars().first()
        if not pos:
            return False, "Position not found or already closed."

        await self.engine.execute_exit_order(
            position=pos,
            bid=bid,
            ask=ask,
            exit_reason="Manual Exit requested from Dashboard",
            account_id=pos.account_id
        )
        return True, f"Successfully liquidated position {pos.instrument} at market."
