"""
Anti-Gravity — Data Engine
Fetches market data from yfinance. Clean, consistent OHLCV DataFrames.
"""

import yfinance as yf
import pandas as pd
import logging

logger = logging.getLogger("anti_gravity.data")


def fetch_historical(
    symbol: str,
    period: str = "6mo",
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Download historical OHLCV data.

    Args:
        symbol:   Ticker symbol, e.g. "RELIANCE.NS"
        period:   yfinance period string (1d, 5d, 1mo, 3mo, 6mo, 1y, …)
        interval: Candle interval (1m, 5m, 15m, 1h, 1d, 1wk, …)

    Returns:
        DataFrame with columns: Open, High, Low, Close, Volume
    """
    logger.info(f"Fetching {symbol} | period={period} interval={interval}")
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)

    if df.empty:
        logger.warning(f"No data returned for {symbol}")
        return pd.DataFrame()

    # Keep only the columns we need and ensure clean types
    cols = ["Open", "High", "Low", "Close", "Volume"]
    df = df[cols].copy()
    df.index.name = "Datetime"
    df.dropna(inplace=True)

    logger.info(f"Fetched {len(df)} candles for {symbol}")
    return df


def fetch_live(
    symbol: str,
    interval: str = "5m",
    lookback: str = "3mo",
) -> pd.DataFrame:
    """
    Fetch recent candles for live analysis.
    Default lookback is 3mo to ensure enough data for indicator warm-up
    (EMA50 needs 50+ candles, ATR needs 14+).

    Args:
        symbol:   Ticker symbol
        interval: Candle interval
        lookback: How far back to pull (default 3mo for daily candles)

    Returns:
        DataFrame with latest candles
    """
    logger.info(f"Live fetch {symbol} | interval={interval} lookback={lookback}")
    df = fetch_historical(symbol, period=lookback, interval=interval)
    return df


def get_latest_price(symbol: str) -> float:
    """Return the latest closing price for a symbol."""
    ticker = yf.Ticker(symbol)
    info = ticker.fast_info
    return float(info.get("lastPrice", 0.0))


# ─── Quick smoke test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    df = fetch_historical("RELIANCE.NS", "1mo", "1d")
    print(df.tail(10))
    print(f"\nLatest price: ₹{get_latest_price('RELIANCE.NS'):,.2f}")
