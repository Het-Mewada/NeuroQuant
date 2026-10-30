from datetime import time
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Project metadata
    PROJECT_NAME: str = "NeuroQuant Autonomous Paper Trading Engine"
    VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Mode: 'paper' or 'backtest' (real-money is intentionally blocked in code)
    OPERATIONAL_MODE: str = "paper"

    # Virtual Capital & Currency
    INITIAL_VIRTUAL_CAPITAL: float = 500000.0  # ₹5,00,000 INR
    CURRENCY: str = "INR"

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./neuroquant.db"

    # Market Schedule (Indian Standard Time: UTC+5:30)
    MARKET_TZ: str = "Asia/Kolkata"
    TIME_PRE_MARKET: time = time(9, 0)
    TIME_MARKET_OPEN: time = time(9, 15)
    TIME_NO_TRADE_OPEN: time = time(9, 20)      # Avoid the first 5 minutes opening volatility
    TIME_WIND_DOWN: time = time(15, 0)          # Stop opening new positions
    TIME_AUTO_SQUARE_OFF: time = time(15, 15)   # Force-close intraday positions before market close
    TIME_MARKET_CLOSE: time = time(15, 30)

    # Risk Management Boundaries (Hard constraints)
    MAX_DAILY_LOSS_PCT: float = 2.0             # Kill switch tripped if daily loss >= 2% of total capital
    MAX_TRADE_RISK_PCT: float = 1.0             # Maximum capital risked on any single trade
    MAX_PORTFOLIO_DRAWDOWN_PCT: float = 5.0     # Maximum peak-to-trough drawdown before halt
    MAX_CONCURRENT_POSITIONS: int = 3           # Focus capital, prevent over-diversification
    MIN_REWARD_RISK_RATIO: float = 1.5          # Net RR threshold after slippage and taxes

    # Target Instruments & Lot Sizes (NSE Derivatives)
    TARGET_INDICES: List[str] = ["NIFTY", "BANKNIFTY"]
    LOT_SIZE_NIFTY: int = 25
    LOT_SIZE_BANKNIFTY: int = 15

    # Realistic Execution & Friction (Basis Points / Rupee Rates)
    SLIPPAGE_BPS: float = 8.0                   # Base slippage in basis points
    BROKERAGE_PER_ORDER: float = 20.0           # ₹20 flat discount broker simulation
    STT_OPTIONS_SELL_PCT: float = 0.10          # 0.1% on premium turnover on sell
    EXCHANGE_TURNOVER_PCT: float = 0.0505       # 0.0505% on options premium (NSE)
    GST_PCT: float = 18.0                       # 18% on (Brokerage + Exchange turnover)
    SEBI_CHARGES_PER_CRORE: float = 10.0        # ₹10 per crore turnover
    STAMP_DUTY_BUY_PCT: float = 0.003           # 0.003% on buy premium

    # Data Provider Options ('mock', 'upstox', 'angelone')
    DATA_PROVIDER: str = "mock"
    UPSTOX_API_KEY: str = ""
    UPSTOX_API_SECRET: str = ""
    UPSTOX_REDIRECT_URI: str = "http://localhost:8000/api/v1/auth/upstox/callback"
    ANGEL_API_KEY: str = ""
    ANGEL_CLIENT_CODE: str = ""
    ANGEL_PIN: str = ""
    ANGEL_TOTP_SECRET: str = ""

    # Telegram Bot Alerts (Optional)
    TELEGRAM_ENABLED: bool = True
    TELEGRAM_BOT_TOKEN: str = "8720002475:AAHggQS0rqbcT4Sod3fQP_0LSpu_gUN4AYg"
    TELEGRAM_CHAT_ID: str = "2118366251"

    # Server settings
    HOST: str = "0.0.0.0"
    PORT: int = 8000


settings = Settings()
