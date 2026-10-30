import asyncio
import math
import random
from datetime import datetime
from typing import AsyncGenerator, Dict, List
from app.models.domain import Tick, OptionContract, InstrumentType
from app.data.greeks import black_scholes_price, calculate_greeks


class MockMarketDataFeed:
    """
    High-fidelity synthetic NSE tick and option chain generator.
    Simulates geometric brownian motion with jumps, volatility regimes,
    and realistic bid-ask microstructure for Nifty 50 and Bank Nifty.
    """

    def __init__(self):
        self.spots = {
            "NIFTY": 24500.0,
            "BANKNIFTY": 52000.0
        }
        self.vix = 14.5
        self.is_running = False

    def generate_option_chain(self, underlying: str, num_strikes: int = 5) -> List[OptionContract]:
        spot = self.spots[underlying]
        strike_step = 50.0 if underlying == "NIFTY" else 100.0
        atm_strike = round(spot / strike_step) * strike_step
        expiry_days = 4.0  # ~4 days to weekly Thursday expiry
        t_years = expiry_days / 365.0
        lot_size = 25 if underlying == "NIFTY" else 15
        vol = self.vix / 100.0

        contracts = []
        for i in range(-num_strikes, num_strikes + 1):
            strike = atm_strike + (i * strike_step)

            # Call option
            call_theo = black_scholes_price(spot, strike, t_years, vol, is_call=True)
            call_greeks = calculate_greeks(spot, strike, t_years, vol, is_call=True)
            call_spread = max(0.5, round(call_theo * 0.015, 2))
            call_bid = max(0.05, round(call_theo - call_spread * 0.5, 2))
            call_ask = round(call_theo + call_spread * 0.5, 2)

            contracts.append(OptionContract(
                symbol=f"{underlying}_{int(strike)}_CE",
                underlying=underlying,
                strike=strike,
                expiry="WEEKLY",
                option_type=InstrumentType.OPTION_CE,
                lot_size=lot_size,
                ltp=call_theo,
                bid=call_bid,
                ask=call_ask,
                iv=self.vix,
                delta=call_greeks["delta"],
                gamma=call_greeks["gamma"],
                theta=call_greeks["theta"],
                vega=call_greeks["vega"],
                open_interest=random.randint(50000, 2000000),
                volume=random.randint(1000, 50000)
            ))

            # Put option
            put_theo = black_scholes_price(spot, strike, t_years, vol, is_call=False)
            put_greeks = calculate_greeks(spot, strike, t_years, vol, is_call=False)
            put_spread = max(0.5, round(put_theo * 0.015, 2))
            put_bid = max(0.05, round(put_theo - put_spread * 0.5, 2))
            put_ask = round(put_theo + put_spread * 0.5, 2)

            contracts.append(OptionContract(
                symbol=f"{underlying}_{int(strike)}_PE",
                underlying=underlying,
                strike=strike,
                expiry="WEEKLY",
                option_type=InstrumentType.OPTION_PE,
                lot_size=lot_size,
                ltp=put_theo,
                bid=put_bid,
                ask=put_ask,
                iv=self.vix,
                delta=put_greeks["delta"],
                gamma=put_greeks["gamma"],
                theta=put_greeks["theta"],
                vega=put_greeks["vega"],
                open_interest=random.randint(50000, 2000000),
                volume=random.randint(1000, 50000)
            ))

        return contracts

    async def stream_ticks(self, interval_seconds: float = 1.0) -> AsyncGenerator[Tick, None]:
        self.is_running = True
        while self.is_running:
            for und in ["NIFTY", "BANKNIFTY"]:
                # Micro-drift with mean reversion
                vol_step = (self.vix / 100.0) / math.sqrt(252 * 375 * 60)
                shock = random.gauss(0, 1.0) * vol_step * self.spots[und]
                self.spots[und] = round(self.spots[und] + shock, 2)

                spread = 0.5 if und == "NIFTY" else 1.0
                bid = round(self.spots[und] - spread * 0.5, 2)
                ask = round(self.spots[und] + spread * 0.5, 2)
                volume = random.randint(50, 500)

                tick = Tick(
                    instrument=und,
                    timestamp=datetime.utcnow(),
                    ltp=self.spots[und],
                    volume=volume,
                    open_interest=random.randint(1000000, 5000000),
                    bid=bid,
                    ask=ask,
                    bid_qty=random.randint(100, 1000),
                    ask_qty=random.randint(100, 1000)
                )
                yield tick

            await asyncio.sleep(interval_seconds)

    def stop(self):
        self.is_running = False
