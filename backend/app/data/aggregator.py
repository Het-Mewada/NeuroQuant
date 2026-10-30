from datetime import datetime, timedelta
from typing import Dict, List, Optional
from app.models.domain import Tick, Candle


class CandleAggregator:
    """
    Constructs accurate time-bucketed OHLCV candles from raw incoming tick streams.
    Tracks session high/low and calculates volume-weighted average price (VWAP).
    """

    def __init__(self, timeframe_minutes: int = 1):
        self.timeframe_minutes = timeframe_minutes
        self.current_candles: Dict[str, Candle] = {}
        self.session_highs: Dict[str, float] = {}
        self.session_lows: Dict[str, float] = {}
        self.vwap_cum_pv: Dict[str, float] = {}
        self.vwap_cum_vol: Dict[str, int] = {}

    def get_candle_bucket_time(self, tick_time: datetime) -> datetime:
        minute = (tick_time.minute // self.timeframe_minutes) * self.timeframe_minutes
        return tick_time.replace(minute=minute, second=0, microsecond=0)

    def process_tick(self, tick: Tick) -> Optional[Candle]:
        """
        Updates running candle with incoming tick.
        If a new candle boundary is crossed, returns the completed previous candle.
        """
        inst = tick.instrument
        bucket_time = self.get_candle_bucket_time(tick.timestamp)

        # Track session statistics
        if inst not in self.session_highs or tick.ltp > self.session_highs[inst]:
            self.session_highs[inst] = tick.ltp
        if inst not in self.session_lows or tick.ltp < self.session_lows[inst]:
            self.session_lows[inst] = tick.ltp

        # Track intraday VWAP
        vol = max(1, tick.volume)
        self.vwap_cum_pv[inst] = self.vwap_cum_pv.get(inst, 0.0) + (tick.ltp * vol)
        self.vwap_cum_vol[inst] = self.vwap_cum_vol.get(inst, 0) + vol

        completed_candle = None

        if inst not in self.current_candles:
            # First tick for instrument
            self.current_candles[inst] = Candle(
                instrument=inst,
                timeframe=f"{self.timeframe_minutes}m",
                timestamp=bucket_time,
                open=tick.ltp,
                high=tick.ltp,
                low=tick.ltp,
                close=tick.ltp,
                volume=tick.volume,
                open_interest=tick.open_interest
            )
        else:
            current = self.current_candles[inst]
            if bucket_time > current.timestamp:
                # Candle completed!
                completed_candle = current
                # Start new candle
                self.current_candles[inst] = Candle(
                    instrument=inst,
                    timeframe=f"{self.timeframe_minutes}m",
                    timestamp=bucket_time,
                    open=tick.ltp,
                    high=tick.ltp,
                    low=tick.ltp,
                    close=tick.ltp,
                    volume=tick.volume,
                    open_interest=tick.open_interest
                )
            else:
                # Update current active candle
                current.high = max(current.high, tick.ltp)
                current.low = min(current.low, tick.ltp)
                current.close = tick.ltp
                current.volume += tick.volume
                current.open_interest = tick.open_interest

        return completed_candle

    def get_session_vwap(self, instrument: str) -> float:
        vol = self.vwap_cum_vol.get(instrument, 0)
        if vol <= 0:
            return 0.0
        return round(self.vwap_cum_pv.get(instrument, 0.0) / vol, 2)
