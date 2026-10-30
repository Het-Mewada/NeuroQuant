from datetime import datetime, time
from enum import Enum
import zoneinfo
from app.core.config import settings


class MarketState(str, Enum):
    CLOSED = "CLOSED"
    PRE_MARKET = "PRE_MARKET"                       # 09:00 - 09:15
    OPENING_VOLATILITY = "OPENING_VOLATILITY"       # 09:15 - 09:20 (No new entries)
    ACTIVE_TRADING = "ACTIVE_TRADING"               # 09:20 - 15:00 (Full engine active)
    WIND_DOWN = "WIND_DOWN"                         # 15:00 - 15:15 (No new entries, tighten stops)
    SQUARE_OFF = "SQUARE_OFF"                       # 15:15 - 15:30 (Force exit intraday positions)
    POST_MARKET = "POST_MARKET"                     # 15:30 - 16:00 (Journaling, ledger reconciliation)


class MarketLifecycleManager:
    """
    Authoritative state machine governing market phases according to Indian Standard Time (IST).
    Prevents entries during open volatility or end-of-day square off.
    """

    def __init__(self):
        try:
            self.tz = zoneinfo.ZoneInfo(settings.MARKET_TZ)
        except Exception:
            # Fallback for systems where tzdata might be localized
            self.tz = zoneinfo.ZoneInfo("UTC")

    def get_current_ist_time(self) -> datetime:
        return datetime.now(self.tz)

    def determine_state(self, current_dt: datetime | None = None) -> MarketState:
        if current_dt is None:
            current_dt = self.get_current_ist_time()

        # Check for weekend (Saturday = 5, Sunday = 6)
        if current_dt.weekday() in (5, 6):
            return MarketState.CLOSED

        t = current_dt.time()

        if time(9, 0) <= t < time(9, 15):
            return MarketState.PRE_MARKET
        elif time(9, 15) <= t < time(9, 20):
            return MarketState.OPENING_VOLATILITY
        elif time(9, 20) <= t < time(15, 0):
            return MarketState.ACTIVE_TRADING
        elif time(15, 0) <= t < time(15, 15):
            return MarketState.WIND_DOWN
        elif time(15, 15) <= t < time(15, 30):
            return MarketState.SQUARE_OFF
        elif time(15, 30) <= t < time(16, 0):
            return MarketState.POST_MARKET
        else:
            return MarketState.CLOSED

    def can_open_new_position(self, current_dt: datetime | None = None) -> tuple[bool, str]:
        state = self.determine_state(current_dt)
        if state == MarketState.ACTIVE_TRADING:
            return True, "Active trading window"
        elif state == MarketState.OPENING_VOLATILITY:
            return False, "Market opened at 09:15: Waiting for opening volatility to settle (until 09:20)"
        elif state == MarketState.WIND_DOWN:
            return False, "Wind-down phase (15:00-15:15): Market close approaching; no new entries permitted"
        elif state == MarketState.SQUARE_OFF:
            return False, "Square-off phase (15:15-15:30): Intraday positions are being closed"
        elif state == MarketState.PRE_MARKET:
            return False, "Pre-market session (09:00-09:15): Market not yet open"
        else:
            return False, f"Market is currently {state.value}. Trading is inactive."

    def should_force_exit_intraday(self, current_dt: datetime | None = None) -> bool:
        state = self.determine_state(current_dt)
        return state in (MarketState.SQUARE_OFF, MarketState.POST_MARKET, MarketState.CLOSED)


market_lifecycle = MarketLifecycleManager()
