from datetime import datetime
import zoneinfo
import pytest
from app.core.state_machine import MarketLifecycleManager, MarketState


def test_market_state_transitions():
    mgr = MarketLifecycleManager()
    tz = mgr.tz

    # 1. 09:05 AM Wednesday -> PRE_MARKET
    dt_pre = datetime(2026, 10, 28, 9, 5, tzinfo=tz)
    assert mgr.determine_state(dt_pre) == MarketState.PRE_MARKET
    can_trade, reason = mgr.can_open_new_position(dt_pre)
    assert not can_trade

    # 2. 09:16 AM Wednesday -> OPENING_VOLATILITY (No trade)
    dt_open_vol = datetime(2026, 10, 28, 9, 16, tzinfo=tz)
    assert mgr.determine_state(dt_open_vol) == MarketState.OPENING_VOLATILITY
    can_trade, reason = mgr.can_open_new_position(dt_open_vol)
    assert not can_trade
    assert "09:15" in reason

    # 3. 10:30 AM Wednesday -> ACTIVE_TRADING
    dt_active = datetime(2026, 10, 28, 10, 30, tzinfo=tz)
    assert mgr.determine_state(dt_active) == MarketState.ACTIVE_TRADING
    can_trade, _ = mgr.can_open_new_position(dt_active)
    assert can_trade

    # 4. 15:05 PM Wednesday -> WIND_DOWN (No new entries)
    dt_wind = datetime(2026, 10, 28, 15, 5, tzinfo=tz)
    assert mgr.determine_state(dt_wind) == MarketState.WIND_DOWN
    can_trade, _ = mgr.can_open_new_position(dt_wind)
    assert not can_trade

    # 5. 15:20 PM Wednesday -> SQUARE_OFF (Force exit)
    dt_sq = datetime(2026, 10, 28, 15, 20, tzinfo=tz)
    assert mgr.determine_state(dt_sq) == MarketState.SQUARE_OFF
    assert mgr.should_force_exit_intraday(dt_sq) is True

    # 6. Saturday 11:00 AM -> CLOSED
    dt_sat = datetime(2026, 10, 31, 11, 0, tzinfo=tz)
    assert mgr.determine_state(dt_sat) == MarketState.CLOSED
