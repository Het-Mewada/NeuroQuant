import math
from app.core.config import settings


def calculate_indian_fo_taxes(
    entry_price: float,
    exit_price: float,
    quantity: int,
    is_option: bool = True
) -> dict[str, float]:
    """
    Computes statutory Indian market transaction charges for F&O:
    Brokerage, STT, Exchange turnover fees, GST, SEBI charges, Stamp duty.
    """
    buy_turnover = entry_price * quantity
    sell_turnover = exit_price * quantity
    total_turnover = buy_turnover + sell_turnover

    # 1. Brokerage: Flat ₹20 per executed order (Entry + Exit = ₹40)
    brokerage = settings.BROKERAGE_PER_ORDER * 2.0

    # 2. STT (Securities Transaction Tax):
    # On options: 0.1% on sell premium turnover
    # On futures: 0.02% on sell turnover
    if is_option:
        stt = sell_turnover * (settings.STT_OPTIONS_SELL_PCT / 100.0)
    else:
        stt = sell_turnover * 0.0002

    # 3. Exchange Turnover Charges:
    # NSE Options: 0.0505% on premium turnover
    exchange_charges = total_turnover * (settings.EXCHANGE_TURNOVER_PCT / 100.0)

    # 4. GST: 18% on (Brokerage + Exchange turnover charges)
    gst = (brokerage + exchange_charges) * (settings.GST_PCT / 100.0)

    # 5. SEBI Charges: ₹10 per crore (10 / 10,000,000)
    sebi_charges = total_turnover * (settings.SEBI_CHARGES_PER_CRORE / 10000000.0)

    # 6. Stamp Duty: 0.003% on buy premium turnover
    stamp_duty = buy_turnover * (settings.STAMP_DUTY_BUY_PCT / 100.0)

    total_friction = brokerage + stt + exchange_charges + gst + sebi_charges + stamp_duty

    return {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exchange_charges": round(exchange_charges, 2),
        "gst": round(gst, 2),
        "sebi_charges": round(sebi_charges, 2),
        "stamp_duty": round(stamp_duty, 2),
        "total_friction": round(total_friction, 2)
    }


def calculate_slippage(
    order_price: float,
    quantity: int,
    bid: float,
    ask: float,
    order_side: str,
    depth_vol: int = 500
) -> float:
    """
    Computes realistic fill price including bid-ask spread penalty and size impact.
    """
    spread = max(0.05, abs(ask - bid))
    size_impact = min(2.0, max(0.0, quantity / max(1, depth_vol)))
    slippage_points = (spread * 0.5) * (1.0 + size_impact * 0.5)

    if order_side.upper() == "BUY":
        return round(ask + slippage_points, 2)
    else:
        return round(max(0.05, bid - slippage_points), 2)


def calculate_kelly_position_size(
    available_capital: float,
    entry_price: float,
    stop_loss_price: float,
    calibrated_win_prob: float,
    target_price: float,
    lot_size: int,
    max_trade_risk_pct: float = 1.0
) -> tuple[int, float, str]:
    """
    Calculates contract lot quantity via Quarter-Kelly formula constrained by lot size.
    Returns: (allocated_quantity, allocated_capital, sizing_rationale)
    """
    per_unit_risk = abs(entry_price - stop_loss_price)
    per_unit_reward = abs(target_price - entry_price)

    if per_unit_risk <= 0.01:
        return 0, 0.0, "Invalid risk: Entry and stop loss are virtually identical."

    win_loss_ratio = per_unit_reward / per_unit_risk
    if win_loss_ratio < settings.MIN_REWARD_RISK_RATIO:
        return 0, 0.0, f"Reward-to-risk {win_loss_ratio:.2f} is below minimum {settings.MIN_REWARD_RISK_RATIO}:1"

    # Full Kelly: f = p - (1 - p)/b
    b = win_loss_ratio
    p = calibrated_win_prob
    full_kelly = p - ((1.0 - p) / b)

    if full_kelly <= 0:
        return 0, 0.0, f"Negative Kelly expectancy ({full_kelly:.4f}) with win prob {p:.2f}."

    # Quarter Kelly for defensive risk management
    quarter_kelly = max(0.0, full_kelly * 0.25)
    max_risk_cap = max_trade_risk_pct / 100.0
    effective_risk_pct = min(quarter_kelly, max_risk_cap)

    # Maximum rupee amount we can lose on this trade
    max_loss_rupees = available_capital * effective_risk_pct

    # Max units allowed based on stop distance
    max_units_by_risk = math.floor(max_loss_rupees / per_unit_risk)

    # Round down to complete lot size
    lots = math.floor(max_units_by_risk / lot_size)
    if lots < 1:
        # Check if 1 lot risk is acceptable
        single_lot_risk = per_unit_risk * lot_size
        if single_lot_risk <= available_capital * (max_trade_risk_pct * 1.5 / 100.0):
            lots = 1
        else:
            return 0, 0.0, f"Account capital insufficient for 1 lot (Risk ₹{single_lot_risk:.2f} > limit ₹{max_loss_rupees:.2f})."

    # Maximum 10 lots for retail safety cap
    lots = min(lots, 10)
    final_quantity = lots * lot_size
    allocated_capital = round(final_quantity * entry_price, 2)

    rationale = (
        f"Kelly: {effective_risk_pct*100:.2f}% risk allocation -> {lots} lots "
        f"({final_quantity} qty). Max loss: ₹{final_quantity * per_unit_risk:.2f}"
    )
    return final_quantity, allocated_capital, rationale
