from typing import Dict, Any
from app.models.database import PositionDB


class PostMortemAnalyzer:
    """
    Deconstructs closed trades into mathematical attribution factors.
    Validates whether winning trades were driven by genuine skill or lucky market noise.
    """

    @staticmethod
    def analyze_trade(position: PositionDB, max_adverse_excursion: float, max_favorable_excursion: float) -> Dict[str, Any]:
        pnl = position.realized_pnl
        won = pnl > 0
        fees = position.total_fees
        fee_drag_pct = round((fees / max(1.0, abs(pnl + fees))) * 100.0, 2)

        risk_distance = abs(position.entry_price - position.stop_loss)
        target_distance = abs(position.take_profit - position.entry_price)

        # Adverse excursion ratio
        mae_ratio = max_adverse_excursion / max(0.1, risk_distance)
        mfe_ratio = max_favorable_excursion / max(0.1, target_distance)

        # Attribution Classification
        if won:
            if mae_ratio > 0.75:
                verdict = "LUCKY_WIN"
                insight = (
                    f"Profitable trade (+₹{pnl:,.2f}), but experienced severe adverse excursion "
                    f"({mae_ratio*100:.1f}% of stop distance). Timing was poor; near-death experience."
                )
            else:
                verdict = "CLEAN_SKILL_WIN"
                insight = (
                    f"High-quality execution (+₹{pnl:,.2f}) with minimal adverse excursion "
                    f"({mae_ratio*100:.1f}% of risk). Generalizes well."
                )
        else:
            if fee_drag_pct > 30.0:
                verdict = "COST_DRAG_LOSS"
                insight = f"Loss was heavily exacerbated by transaction friction and taxes ({fee_drag_pct}% fee drag)."
            elif mae_ratio >= 1.0:
                verdict = "STRUCTURAL_STOP_LOSS"
                insight = "Stop-loss functioned as intended: disciplined risk invalidation prevented catastrophe."
            else:
                verdict = "EARLY_EXIT_LOSS"
                insight = "Exited early before structural invalidation."

        return {
            "position_id": position.id,
            "instrument": position.instrument,
            "realized_pnl": pnl,
            "won": won,
            "verdict": verdict,
            "fee_drag_pct": fee_drag_pct,
            "mae_ratio": round(mae_ratio, 2),
            "mfe_ratio": round(mfe_ratio, 2),
            "insight": insight
        }


post_mortem = PostMortemAnalyzer()
