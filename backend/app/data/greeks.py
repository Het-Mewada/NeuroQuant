import math
from scipy.stats import norm
from scipy.optimize import brentq


def black_scholes_price(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    risk_free_rate: float = 0.07,  # Approximate RBI repo rate
    is_call: bool = True
) -> float:
    """
    Standard Black-Scholes pricing for European index options.
    """
    if time_to_expiry_years <= 0 or volatility <= 0:
        if is_call:
            return max(0.0, spot - strike)
        else:
            return max(0.0, strike - spot)

    t = max(1e-4, time_to_expiry_years)
    s = spot
    k = strike
    r = risk_free_rate
    v = max(1e-3, volatility)

    d1 = (math.log(s / k) + (r + 0.5 * v * v) * t) / (v * math.sqrt(t))
    d2 = d1 - v * math.sqrt(t)

    if is_call:
        price = s * norm.cdf(d1) - k * math.exp(-r * t) * norm.cdf(d2)
    else:
        price = k * math.exp(-r * t) * norm.cdf(-d2) - s * norm.cdf(-d1)

    return max(0.05, float(price))


def calculate_implied_volatility(
    market_price: float,
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    risk_free_rate: float = 0.07,
    is_call: bool = True
) -> float:
    """
    Solves for Implied Volatility (IV) using Brent's root-finding algorithm.
    """
    if time_to_expiry_years <= 0:
        return 0.15

    # Intrinsic value check
    intrinsic = max(0.0, spot - strike) if is_call else max(0.0, strike - spot)
    if market_price <= intrinsic:
        return 0.10

    def objective(v):
        return black_scholes_price(spot, strike, time_to_expiry_years, v, risk_free_rate, is_call) - market_price

    try:
        iv = brentq(objective, a=0.01, b=3.0, xtol=1e-4, maxiter=50)
        return round(float(iv), 4)
    except Exception:
        # Fallback to standard baseline 15% IV
        return 0.15


def calculate_greeks(
    spot: float,
    strike: float,
    time_to_expiry_years: float,
    volatility: float,
    risk_free_rate: float = 0.07,
    is_call: bool = True
) -> dict[str, float]:
    """
    Calculates Delta, Gamma, Theta (per day), and Vega (per 1% IV change).
    """
    t = max(1e-4, time_to_expiry_years)
    s = spot
    k = strike
    r = risk_free_rate
    v = max(1e-3, volatility)
    sqrt_t = math.sqrt(t)

    d1 = (math.log(s / k) + (r + 0.5 * v * v) * t) / (v * sqrt_t)
    d2 = d1 - v * sqrt_t

    pdf_d1 = norm.pdf(d1)
    cdf_d1 = norm.cdf(d1)

    # 1. Delta
    if is_call:
        delta = cdf_d1
    else:
        delta = cdf_d1 - 1.0

    # 2. Gamma
    gamma = pdf_d1 / (s * v * sqrt_t)

    # 3. Vega (change per 1% move in IV)
    vega = (s * pdf_d1 * sqrt_t) / 100.0

    # 4. Theta (daily decay in rupees)
    term1 = -(s * pdf_d1 * v) / (2.0 * sqrt_t)
    if is_call:
        term2 = -r * k * math.exp(-r * t) * norm.cdf(d2)
    else:
        term2 = r * k * math.exp(-r * t) * norm.cdf(-d2)
    theta_annual = term1 + term2
    theta_daily = theta_annual / 365.0

    return {
        "delta": round(float(delta), 4),
        "gamma": round(float(gamma), 6),
        "theta": round(float(theta_daily), 2),
        "vega": round(float(vega), 2)
    }
