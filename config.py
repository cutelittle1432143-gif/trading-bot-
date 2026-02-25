"""
Anti-Gravity — Central Configuration
All tunables live here. 24/7 global markets for continuous paper trading.
"""

import os

# ─── Trading Symbols (24/7 Global Markets) ────────────────────────────────────
SYMBOL = "BTC-USD"                          # Default: Bitcoin (trades 24/7)

WATCHLIST = [
    # Crypto (24/7 — always active)
    "BTC-USD",       # Bitcoin
    "ETH-USD",       # Ethereum
    "SOL-USD",       # Solana

    # US Stocks (NYSE/NASDAQ — 9:30-16:00 ET)
    "AAPL",          # Apple
    "TSLA",          # Tesla
    "NVDA",          # NVIDIA
    "MSFT",          # Microsoft
    "AMZN",          # Amazon

    # Forex (24/5 via yfinance)
    "EURUSD=X",      # Euro / USD
    "GBPUSD=X",      # British Pound / USD

    # Indian NSE (9:15-15:30 IST)
    "RELIANCE.NS",   # Reliance Industries
    "TCS.NS",        # Tata Consultancy Services
    "INFY.NS",       # Infosys
]

# ─── Capital & Risk ──────────────────────────────────────────────────────────
CAPITAL = 800                               # ★ Starting virtual capital (₹800)
RISK_PER_TRADE = 0.02                       # 2% of capital per trade
MAX_DAILY_LOSS = 0.05                       # 5% max daily drawdown
MAX_OPEN_POSITIONS = 3                      # Concurrent positions cap
COOLDOWN_AFTER_LOSSES = 3                   # Pause after N consecutive losses

# ─── Indicator Parameters ────────────────────────────────────────────────────
EMA_FAST = 9                                # ★ Fast EMA for 5m candles
EMA_SLOW = 21                               # ★ Slow EMA for quick crossovers
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
BB_PERIOD = 20
BB_STD = 2
ATR_PERIOD = 14

# ─── Strategy Thresholds ─────────────────────────────────────────────────────
RSI_OVERBOUGHT = 80
RSI_OVERSOLD = 30
RSI_BUY_CEILING = 70
MIN_CONFIDENCE = 75                         # ★ 75%+ confidence for quality trades
RR_RATIO = 1.5                              # Minimum risk-reward ratio

# ─── Data Settings ────────────────────────────────────────────────────────────
DEFAULT_PERIOD = "1mo"                       # 1 month lookback for 5m candles
DEFAULT_INTERVAL = "5m"                      # ★ 5-minute candles for active trading
LIVE_INTERVAL = "5m"

# ─── Execution Mode ──────────────────────────────────────────────────────────
PAPER_TRADE = True                          # True = paper, False = live

# ─── Broker Credentials (load from env) ───────────────────────────────────────
ANGEL_API_KEY = os.getenv("ANGEL_API_KEY", "")
ANGEL_CLIENT_ID = os.getenv("ANGEL_CLIENT_ID", "")
ANGEL_PASSWORD = os.getenv("ANGEL_PASSWORD", "")
ANGEL_TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET", "")

# ─── Paths ────────────────────────────────────────────────────────────────────
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
TRADE_LOG = os.path.join(LOG_DIR, "trades.csv")
RUNTIME_LOG = os.path.join(LOG_DIR, "runtime.log")

os.makedirs(LOG_DIR, exist_ok=True)
