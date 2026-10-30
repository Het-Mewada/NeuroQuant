import pytest
from app.data.greeks import black_scholes_price, calculate_greeks, calculate_implied_volatility


def test_black_scholes_call_put_parity():
    spot = 24500.0
    strike = 24500.0
    t_years = 30.0 / 365.0
    vol = 0.15
    rate = 0.07

    call_price = black_scholes_price(spot, strike, t_years, vol, rate, is_call=True)
    put_price = black_scholes_price(spot, strike, t_years, vol, rate, is_call=False)

    assert call_price > 0.0
    assert put_price > 0.0
    # At-the-money call is typically slightly higher than put due to positive interest rate
    assert call_price > put_price


def test_greeks_bounds():
    spot = 24500.0
    strike = 24500.0
    t_years = 7.0 / 365.0
    vol = 0.14

    call_greeks = calculate_greeks(spot, strike, t_years, vol, is_call=True)
    put_greeks = calculate_greeks(spot, strike, t_years, vol, is_call=False)

    # ATM Call Delta should be approximately 0.50
    assert 0.45 <= call_greeks["delta"] <= 0.60
    # ATM Put Delta should be approximately -0.50
    assert -0.60 <= put_greeks["delta"] <= -0.45
    # Gamma should be strictly positive
    assert call_greeks["gamma"] > 0.0
    # Theta should be negative (time decay hurts long options)
    assert call_greeks["theta"] < 0.0
    # Vega should be positive
    assert call_greeks["vega"] > 0.0


def test_implied_volatility_solver():
    spot = 24500.0
    strike = 24500.0
    t_years = 7.0 / 365.0
    known_vol = 0.16

    mkt_price = black_scholes_price(spot, strike, t_years, known_vol, is_call=True)
    solved_iv = calculate_implied_volatility(mkt_price, spot, strike, t_years, is_call=True)

    assert abs(solved_iv - known_vol) < 0.01
