import pytest
from app.risk.formulas import calculate_indian_fo_taxes, calculate_slippage, calculate_kelly_position_size


def test_indian_fo_taxes():
    # Test buying 50 units (2 lots) of Nifty at 120 and selling at 160
    taxes = calculate_indian_fo_taxes(entry_price=120.0, exit_price=160.0, quantity=50, is_option=True)

    assert taxes["brokerage"] == 40.0  # ₹20 buy + ₹20 sell
    assert taxes["stt"] > 0.0          # 0.1% of sell premium (160 * 50 * 0.001 = 8.0)
    assert taxes["exchange_charges"] > 0.0
    assert taxes["gst"] > 0.0
    assert taxes["stamp_duty"] > 0.0
    assert taxes["total_friction"] > 45.0


def test_slippage_calculation():
    # Market buy order
    fill_buy = calculate_slippage(
        order_price=150.0,
        quantity=50,
        bid=149.5,
        ask=150.5,
        order_side="BUY",
        depth_vol=500
    )
    # Fill price should be at or slightly higher than ask due to spread & impact
    assert fill_buy >= 150.5

    # Market sell order
    fill_sell = calculate_slippage(
        order_price=150.0,
        quantity=50,
        bid=149.5,
        ask=150.5,
        order_side="SELL",
        depth_vol=500
    )
    assert fill_sell <= 149.5


def test_kelly_position_sizing_discipline():
    # Capital: ₹5,00,000, Option price: ₹150, Stop: ₹120 (Risk = ₹30), Target: ₹220 (Reward = ₹70), Lot: 25
    qty, alloc_cap, rationale = calculate_kelly_position_size(
        available_capital=500000.0,
        entry_price=150.0,
        stop_loss_price=120.0,
        calibrated_win_prob=0.58,
        target_price=220.0,
        lot_size=25,
        max_trade_risk_pct=1.0
    )

    assert qty > 0
    assert qty % 25 == 0  # Must be an exact multiple of the lot size!
    # Max loss on position should not exceed 1% of 500,000 (₹5,000) by much
    max_loss = qty * 30.0
    assert max_loss <= 500000.0 * 0.015


def test_kelly_zero_on_negative_expectancy():
    # If win probability is too low (e.g. 25%), Kelly must reject the trade
    qty, alloc_cap, rationale = calculate_kelly_position_size(
        available_capital=500000.0,
        entry_price=150.0,
        stop_loss_price=120.0,
        calibrated_win_prob=0.25,
        target_price=180.0,
        lot_size=25
    )
    assert qty == 0
    assert "Negative Kelly" in rationale or "Reward-to-risk" in rationale
