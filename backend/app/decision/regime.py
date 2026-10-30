import math
from typing import List
from app.models.domain import Candle


class MarketRegime:
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    HIGH_VOL_RANGE = "HIGH_VOL_RANGE"
    LOW_VOL_CHOP = "LOW_VOL_CHOP"


class RegimeDetector:
    """
    Classifies market regime into discrete states using trend slope,
    volatility dispersion, and ATR expansion.
    """

    @staticmethod
    def classify(candles: List[Candle], current_vix: float = 14.5) -> str:
        if len(candles) < 20:
            return MarketRegime.LOW_VOL_CHOP

        closes = [c.close for c in candles[-20:]]
        highs = [c.high for c in candles[-20:]]
        lows = [c.low for c in candles[-20:]]

        # 1. 20-period Simple Moving Average
        sma20 = sum(closes) / 20.0
        current_close = closes[-1]

        # 2. Linear regression slope of close prices
        n = len(closes)
        x_mean = (n - 1) / 2.0
        y_mean = sum(closes) / n
        numerator = sum((i - x_mean) * (closes[i] - y_mean) for i in range(n))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        slope = numerator / max(1e-5, denominator)

        # 3. Normalized ATR
        true_ranges = []
        for i in range(1, len(candles[-20:])):
            c_curr = candles[i]
            c_prev = candles[i-1]
            tr = max(
                c_curr.high - c_curr.low,
                abs(c_curr.high - c_prev.close),
                abs(c_curr.low - c_prev.close)
            )
            true_ranges.append(tr)
        atr = sum(true_ranges) / len(true_ranges) if true_ranges else 10.0
        natr = (atr / current_close) * 100.0

        # High volatility threshold
        is_high_vol = current_vix > 18.0 or natr > 0.35

        # Trend thresholds
        slope_pct = (slope / current_close) * 100.0

        if slope_pct > 0.04 and current_close > sma20:
            return MarketRegime.TRENDING_BULL
        elif slope_pct < -0.04 and current_close < sma20:
            return MarketRegime.TRENDING_BEAR
        elif is_high_vol:
            return MarketRegime.HIGH_VOL_RANGE
        else:
            return MarketRegime.LOW_VOL_CHOP
