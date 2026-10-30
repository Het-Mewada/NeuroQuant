import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.database import CounterfactualDB


class CounterfactualEngine:
    """
    Shadow-evaluates trade opportunities rejected by the risk engine or decision filters.
    Quantifies capital saved vs. alpha missed to avoid confirmation bias.
    """

    def __init__(self, session: AsyncSession):
        self.session = session
        # In-memory active shadow trackers: decision_id -> dict
        self.active_shadows: Dict[str, dict] = {}

    def register_rejected_trade(
        self,
        decision_id: str,
        instrument: str,
        shadow_entry_price: float,
        stop_loss: float,
        target: float,
        side: str
    ):
        self.active_shadows[decision_id] = {
            "id": str(uuid.uuid4()),
            "decision_id": decision_id,
            "instrument": instrument,
            "shadow_entry_price": shadow_entry_price,
            "stop_loss": stop_loss,
            "target": target,
            "side": side,
            "started_at": datetime.utcnow(),
            "max_adverse": 0.0,
            "max_favorable": 0.0,
            "is_resolved": False
        }

    async def update_market_price(self, instrument: str, current_price: float):
        now = datetime.utcnow()
        resolved_keys = []

        for dec_id, shadow in self.active_shadows.items():
            if shadow["instrument"] != instrument or shadow["is_resolved"]:
                continue

            entry = shadow["shadow_entry_price"]
            sl = shadow["stop_loss"]
            tp = shadow["target"]
            side = shadow["side"]

            if side == "BUY":
                pnl_points = current_price - entry
                sl_hit = current_price <= sl
                tp_hit = current_price >= tp
            else:
                pnl_points = entry - current_price
                sl_hit = current_price >= sl
                tp_hit = current_price <= tp

            duration_sec = int((now - shadow["started_at"]).total_seconds())

            # Check resolution (SL, TP, or 60-minute shadow timeout)
            if sl_hit or tp_hit or duration_sec >= 3600:
                shadow["is_resolved"] = True
                resolved_keys.append(dec_id)

                cf_record = CounterfactualDB(
                    id=shadow["id"],
                    decision_id=shadow["decision_id"],
                    instrument=instrument,
                    shadow_entry_price=entry,
                    shadow_exit_price=current_price,
                    hypothetical_pnl=round(pnl_points, 2),
                    hypothetical_pnl_pct=round((pnl_points / entry) * 100.0, 2),
                    tracking_duration_sec=duration_sec,
                    evaluated_at=now
                )
                self.session.add(cf_record)

        if resolved_keys:
            await self.session.commit()
            for k in resolved_keys:
                self.active_shadows.pop(k, None)
