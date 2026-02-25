"""
Anti-Gravity — Feature Engine
Converts raw OHLCV data into actionable technical indicators.
"""

import pandas as pd
import ta
import logging

logger = logging.getLogger("anti_gravity.features")


def compute_indicators(
    df: pd.DataFrame,
    ema_fast: int = 20,
    ema_slow: int = 50,
    rsi_period: int = 14,
    macd_fast: int = 12,
    macd_slow: int = 26,
    macd_signal: int = 9,
    bb_period: int = 20,
    bb_std: int = 2,
    atr_period: int = 14,
) -> pd.DataFrame:
    """
    Compute all technical indicators and append them as new columns.

    Indicators added:
        EMA_fast, EMA_slow, RSI, MACD, MACD_signal, MACD_hist,
        BB_upper, BB_middle, BB_lower, ATR, VWAP

    Args:
        df: DataFrame with Open, High, Low, Close, Volume columns.

    Returns:
        Same DataFrame with indicator columns appended.
    """
    if df.empty:
        logger.warning("Empty DataFrame — skipping indicator computation")
        return df

    df = df.copy()

    # ── Exponential Moving Averages ──────────────────────────────────────
    df["EMA_fast"] = ta.trend.ema_indicator(df["Close"], window=ema_fast)
    df["EMA_slow"] = ta.trend.ema_indicator(df["Close"], window=ema_slow)

    # ── RSI ──────────────────────────────────────────────────────────────
    df["RSI"] = ta.momentum.rsi(df["Close"], window=rsi_period)

    # ── MACD ─────────────────────────────────────────────────────────────
    macd = ta.trend.MACD(
        df["Close"],
        window_slow=macd_slow,
        window_fast=macd_fast,
        window_sign=macd_signal,
    )
    df["MACD"] = macd.macd()
    df["MACD_signal"] = macd.macd_signal()
    df["MACD_hist"] = macd.macd_diff()

    # ── Bollinger Bands ──────────────────────────────────────────────────
    bb = ta.volatility.BollingerBands(
        df["Close"], window=bb_period, window_dev=bb_std
    )
    df["BB_upper"] = bb.bollinger_hband()
    df["BB_middle"] = bb.bollinger_mavg()
    df["BB_lower"] = bb.bollinger_lband()

    # ── ATR (Average True Range) ─────────────────────────────────────────
    df["ATR"] = ta.volatility.average_true_range(
        df["High"], df["Low"], df["Close"], window=atr_period
    )

    # ── VWAP (simple cumulative) ─────────────────────────────────────────
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    cum_vol = df["Volume"].cumsum()
    cum_tp_vol = (typical_price * df["Volume"]).cumsum()
    df["VWAP"] = cum_tp_vol / cum_vol

    logger.info(f"Computed indicators — {len(df)} rows")
    return df


# ─── Quick smoke test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys, os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data.data_fetcher import fetch_historical

    logging.basicConfig(level=logging.INFO)
    raw = fetch_historical("RELIANCE.NS", "3mo", "1d")
    enriched = compute_indicators(raw)
    print(enriched[["Close", "EMA_fast", "EMA_slow", "RSI", "MACD", "ATR", "VWAP"]].tail(10))
