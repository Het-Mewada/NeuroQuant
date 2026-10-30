import httpx
import logging
from typing import Optional
from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """
    Asynchronous Telegram notification dispatcher for real-time trade signals,
    execution events, and risk alerts.
    """

    def __init__(self):
        self.enabled = settings.TELEGRAM_ENABLED
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.chat_id = settings.TELEGRAM_CHAT_ID
        self.base_url = f"https://api.telegram.org/bot{self.token}/sendMessage"

    async def send_message(self, text: str) -> bool:
        if not self.enabled or not self.token or not self.chat_id:
            # Fallback: log to console
            logger.info(f"[NOTIFIER SIMULATED] {text}")
            return True

        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": "Markdown"
        }
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(self.base_url, json=payload)
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Failed to deliver Telegram notification: {e}")
            return False

    async def notify_trade_opened(
        self,
        instrument: str,
        side: str,
        quantity: int,
        entry_price: float,
        stop_loss: float,
        target: float,
        rationale: str
    ):
        msg = (
            f"🚀 *TRADE ENTERED (SIMULATED)*\n"
            f"• *Instrument:* `{instrument}`\n"
            f"• *Side:* `{side}` | *Qty:* `{quantity}`\n"
            f"• *Entry:* ₹{entry_price:,.2f}\n"
            f"• *Stop-Loss:* ₹{stop_loss:,.2f}\n"
            f"• *Target:* ₹{target:,.2f}\n"
            f"• *Rationale:* _{rationale}_"
        )
        await self.send_message(msg)

    async def notify_trade_closed(
        self,
        instrument: str,
        realized_pnl: float,
        fees: float,
        exit_reason: str
    ):
        emoji = "✅" if realized_pnl > 0 else "🛑"
        msg = (
            f"{emoji} *TRADE CLOSED*\n"
            f"• *Instrument:* `{instrument}`\n"
            f"• *Net Realized P&L:* ₹{realized_pnl:+,.2f}\n"
            f"• *Taxes & Fees:* ₹{fees:,.2f}\n"
            f"• *Exit Reason:* _{exit_reason}_"
        )
        await self.send_message(msg)

    async def notify_circuit_breaker(self, reason: str):
        msg = (
            f"⚠️ *CIRCUIT BREAKER TRIPPED*\n"
            f"• *Status:* TRADING HALTED FOR THE DAY\n"
            f"• *Reason:* {reason}\n"
            f"• *Action:* Preserving capital. No new positions permitted."
        )
        await self.send_message(msg)


notifier = TelegramNotifier()
