from datetime import datetime, time
from enum import Enum
import zoneinfo
import urllib.request
import json
import logging
from app.core.config import settings

logger = logging.getLogger("neuroquant.state_machine")


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
    Checks live NSE market status directly to dynamically support special trading sessions
    (such as Diwali Muhurat trading on weekends/holidays) alongside standard schedule.
    """

    def __init__(self):
        try:
            self.tz = zoneinfo.ZoneInfo(settings.MARKET_TZ)
        except Exception:
            self.tz = zoneinfo.ZoneInfo("UTC")
        self._last_live_check_time: float = 0.0
        self._cached_live_status: bool | None = None

    def get_current_ist_time(self) -> datetime:
        return datetime.now(self.tz)

    def check_live_nse_exchange_open(self) -> bool | None:
        """
        Polls live NSE marketStatus API. Returns True if Capital Market is Open, False if Closed.
        """
        import time as pytime
        now = pytime.time()
        # Cache for 15 seconds to prevent overwhelming the endpoint
        if self._cached_live_status is not None and (now - self._last_live_check_time) < 15.0:
            return self._cached_live_status

        try:
            url = "https://www.nseindia.com/api/marketStatus"
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json"
            })
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read().decode())
                for item in data.get("marketState", []):
                    if item.get("market") == "Capital Market":
                        status = item.get("marketStatus", "").strip().lower()
                        is_open = status == "open"
                        self._cached_live_status = is_open
                        self._last_live_check_time = now
                        return is_open
        except Exception as e:
            logger.debug(f"NSE marketStatus check fallback: {e}")

        # Fallback to Yahoo Finance regularMarketTime freshness check
        try:
            yurl = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m"
            yreq = urllib.request.Request(yurl, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(yreq, timeout=3) as yresp:
                ydata = json.loads(yresp.read().decode())
                meta = ydata["chart"]["result"][0]["meta"]
                rmt = meta.get("regularMarketTime", 0)
                # If market time was updated within the last 90 seconds, live trading is happening
                is_live = (now - rmt) < 90.0
                self._cached_live_status = is_live
                self._last_live_check_time = now
                return is_live
        except Exception as e:
            logger.debug(f"Yahoo live check fallback: {e}")

        return None

    def determine_state(self, current_dt: datetime | None = None) -> MarketState:
        # If no explicit simulated datetime is provided, we check genuine real-world live exchange status
        if current_dt is None:
            live_is_open = self.check_live_nse_exchange_open()
            if live_is_open is True:
                return MarketState.ACTIVE_TRADING
            current_dt = self.get_current_ist_time()

        # Standard schedule fallback (Monday - Friday)
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
