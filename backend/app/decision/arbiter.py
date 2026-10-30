from datetime import datetime
from typing import List, Optional, Tuple
from app.models.domain import Candle, DecisionAction, DecisionRecord
from app.decision.regime import MarketRegime, RegimeDetector
from app.decision.calibration import calibrator


class DecisionArbiter:
    """
    Evaluates market structure, regime, and indicator alignment.
    Emits disciplined, evidence-based trade intents with explicit invalidation stops.
    Defaults to NO_TRADE when statistical edge is not clear.
    """

    def __init__(self):
        self.regime_detector = RegimeDetector()

    def evaluate_opportunity(
        self,
        instrument: str,
        candles: List[Candle],
        vwap: float,
        session_high: float,
        session_low: float,
        vix: float = 14.5
    ) -> DecisionRecord:
        if len(candles) < 20:
            return DecisionRecord(
                instrument=instrument,
                action=DecisionAction.NO_TRADE,
                raw_confidence=0.0,
                calibrated_probability=0.50,
                expected_value_r=0.0,
                regime=MarketRegime.LOW_VOL_CHOP,
                veto_reason="Insufficient historical bars for structural evaluation (< 20 candles)",
                rationale="Defaulting to NO_TRADE: warming up candle buffers."
            )

        current_candle = candles[-1]
        current_price = current_candle.close
        regime = self.regime_detector.classify(candles, vix)

        # 1. Filter: Never take trend breakout trades during LOW_VOL_CHOP
        if regime == MarketRegime.LOW_VOL_CHOP:
            return DecisionRecord(
                instrument=instrument,
                action=DecisionAction.NO_TRADE,
                raw_confidence=0.35,
                calibrated_probability=calibrator.calibrate(0.35),
                expected_value_r=-0.20,
                regime=regime,
                veto_reason="Unfavorable regime: Market is in low-volatility chop. Edge is zero.",
                rationale="Preserving capital: Choppy sideways markets consume options premiums via theta decay."
            )

        # 2. Strategy: VWAP Pullback Trend Following
        # BULLISH: Bull trend + price pulled back near VWAP, holding above it
        ema20 = sum(c.close for c in candles[-20:]) / 20.0
        atr = max(c.high - c.low for c in candles[-14:])

        is_bullish_pullback = (
            regime == MarketRegime.TRENDING_BULL and
            current_price >= vwap and
            (current_price - vwap) <= (atr * 0.5) and
            current_price > ema20
        )

        is_bearish_pullback = (
            regime == MarketRegime.TRENDING_BEAR and
            current_price <= vwap and
            (vwap - current_price) <= (atr * 0.5) and
            current_price < ema20
        )

        if is_bullish_pullback:
            raw_conf = 0.68
            cal_prob = calibrator.calibrate(raw_conf)
            stop_loss = round(min(vwap - (atr * 0.4), current_candle.low - 2.0), 2)
            risk = current_price - stop_loss
            target = round(current_price + (risk * 2.0), 2)
            exp_r = calibrator.calculate_net_expectancy(cal_prob, current_price, target, stop_loss)

            if exp_r >= 0.35:
                return DecisionRecord(
                    instrument=instrument,
                    action=DecisionAction.ENTER_LONG,
                    raw_confidence=raw_conf,
                    calibrated_probability=cal_prob,
                    expected_value_r=exp_r,
                    regime=regime,
                    features={
                        "vwap": vwap,
                        "atr": round(atr, 2),
                        "ema20": round(ema20, 2),
                        "stop_loss": stop_loss,
                        "target": target
                    },
                    rationale=f"Bullish VWAP Reclaim: Price holding above VWAP ({vwap:.2f}) with expected value +{exp_r:.2f}R."
                )

        if is_bearish_pullback:
            raw_conf = 0.66
            cal_prob = calibrator.calibrate(raw_conf)
            stop_loss = round(max(vwap + (atr * 0.4), current_candle.high + 2.0), 2)
            risk = stop_loss - current_price
            target = round(current_price - (risk * 2.0), 2)
            exp_r = calibrator.calculate_net_expectancy(cal_prob, current_price, target, stop_loss)

            if exp_r >= 0.35:
                return DecisionRecord(
                    instrument=instrument,
                    action=DecisionAction.ENTER_SHORT,
                    raw_confidence=raw_conf,
                    calibrated_probability=cal_prob,
                    expected_value_r=exp_r,
                    regime=regime,
                    features={
                        "vwap": vwap,
                        "atr": round(atr, 2),
                        "ema20": round(ema20, 2),
                        "stop_loss": stop_loss,
                        "target": target
                    },
                    rationale=f"Bearish VWAP Rejection: Price falling below VWAP ({vwap:.2f}) with expected value +{exp_r:.2f}R."
                )

        # Default fallback
        return DecisionRecord(
            instrument=instrument,
            action=DecisionAction.NO_TRADE,
            raw_confidence=0.45,
            calibrated_probability=calibrator.calibrate(0.45),
            expected_value_r=-0.10,
            regime=regime,
            veto_reason="No structural edge: Setup criteria not met.",
            rationale="NO TRADE: Conditions lack asymmetric reward-to-risk."
        )


arbiter = DecisionArbiter()
