"""
Anti-Gravity — Strategy Engine v3.0 (Pine Script Style)

Aggressive EMA crossover strategy that ACTUALLY TRADES.
Scoring is calibrated so good setups reach 78%+ confidence.

Signal logic:
  BUY  = EMA crossover bullish + RSI confirms + MACD confirms
  SELL = EMA crossover bearish OR stop-loss/take-profit hit
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger("anti_gravity.strategy")


def generate_signal(row: pd.Series, prev_row: pd.Series = None) -> dict:
    """
    Pine Script style signal generator.
    Returns: {decision, confidence, reason, stop_loss, take_profit}
    """
    decision = "HOLD"
    confidence = 0
    reasons = []

    # Extract indicators
    ema_fast = row.get("EMA_fast")
    ema_slow = row.get("EMA_slow")
    rsi = row.get("RSI")
    macd = row.get("MACD")
    macd_signal = row.get("MACD_signal")
    macd_hist = row.get("MACD_hist")
    close = row.get("Close")
    atr = row.get("ATR", 0)
    volume = row.get("Volume", 0)
    bb_upper = row.get("BB_upper")
    bb_lower = row.get("BB_lower")

    # Skip if indicators not ready
    if pd.isna(ema_fast) or pd.isna(ema_slow) or pd.isna(rsi):
        return _hold("Indicators warming up")

    atr_val = atr if not pd.isna(atr) else 0
    if atr_val <= 0:
        atr_val = close * 0.01  # fallback: 1% of price

    # ── Previous row data ────────────────────────────────────────
    prev_ema_fast = None
    prev_ema_slow = None
    if prev_row is not None:
        prev_ema_fast = prev_row.get("EMA_fast")
        prev_ema_slow = prev_row.get("EMA_slow")

    # ── CORE: EMA Crossover Detection ────────────────────────────
    ema_bullish = ema_fast > ema_slow
    ema_bearish = ema_fast < ema_slow
    ema_spread = (ema_fast - ema_slow) / ema_slow * 100 if ema_slow else 0

    # Fresh crossover (just happened)
    fresh_bull_cross = False
    fresh_bear_cross = False
    if prev_ema_fast is not None and prev_ema_slow is not None:
        if not pd.isna(prev_ema_fast) and not pd.isna(prev_ema_slow):
            was_bearish = prev_ema_fast <= prev_ema_slow
            was_bullish = prev_ema_fast >= prev_ema_slow
            fresh_bull_cross = was_bearish and ema_bullish
            fresh_bear_cross = was_bullish and ema_bearish

    # ══════════════════════════════════════════════════════════════
    #  BUY SCORING (calibrated: typical aligned setup = 78-90%)
    # ══════════════════════════════════════════════════════════════
    buy_score = 0

    # 1. EMA alignment (35 pts)
    if ema_bullish:
        buy_score += 30
        reasons.append(f"EMA bullish ({ema_spread:+.2f}%)")
        if abs(ema_spread) > 0.05:
            buy_score += 5
            reasons.append("Trend confirmed")

    # 2. Fresh crossover bonus (15 pts)
    if fresh_bull_cross:
        buy_score += 15
        reasons.append("⚡ Fresh crossover!")

    # 3. RSI in buy zone (25 pts)
    if not pd.isna(rsi):
        if rsi < 35:
            buy_score += 25
            reasons.append(f"RSI {rsi:.0f} oversold")
        elif rsi < 50:
            buy_score += 20
            reasons.append(f"RSI {rsi:.0f} buy zone")
        elif rsi < 65:
            buy_score += 15
            reasons.append(f"RSI {rsi:.0f} room to run")
        elif rsi < 75:
            buy_score += 10
            reasons.append(f"RSI {rsi:.0f} moderate")

    # 4. MACD confirmation (25 pts)
    if not pd.isna(macd) and not pd.isna(macd_signal):
        if macd > macd_signal:
            buy_score += 20
            reasons.append("MACD bullish")
            if not pd.isna(macd_hist) and macd_hist > 0:
                buy_score += 5

    # 5. Bollinger position (15 pts)
    if bb_lower and bb_upper and not pd.isna(bb_lower) and not pd.isna(bb_upper):
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_pct = (close - bb_lower) / bb_range
            if bb_pct < 0.25:
                buy_score += 15
                reasons.append(f"Near lower BB ({bb_pct:.0%})")
            elif bb_pct < 0.5:
                buy_score += 10
            elif bb_pct < 0.7:
                buy_score += 5

    # ══════════════════════════════════════════════════════════════
    #  SELL SCORING (out of 100)
    # ══════════════════════════════════════════════════════════════
    sell_score = 0
    sell_reasons = []

    if ema_bearish:
        sell_score += 30
        sell_reasons.append(f"EMA bearish ({ema_spread:+.2f}%)")
        if abs(ema_spread) > 0.05:
            sell_score += 5

    if fresh_bear_cross:
        sell_score += 15
        sell_reasons.append("⚡ Fresh bearish crossover!")

    if not pd.isna(rsi):
        if rsi > 75:
            sell_score += 25
            sell_reasons.append(f"RSI {rsi:.0f} overbought")
        elif rsi > 60:
            sell_score += 15
            sell_reasons.append(f"RSI {rsi:.0f} weakening")
        elif rsi > 50:
            sell_score += 10

    if not pd.isna(macd) and not pd.isna(macd_signal):
        if macd < macd_signal:
            sell_score += 20
            sell_reasons.append("MACD bearish")
            if not pd.isna(macd_hist) and macd_hist < 0:
                sell_score += 5

    if bb_upper and not pd.isna(bb_upper) and bb_lower and not pd.isna(bb_lower):
        bb_range = bb_upper - bb_lower
        if bb_range > 0:
            bb_pct = (close - bb_lower) / bb_range
            if bb_pct > 0.85:
                sell_score += 15
                sell_reasons.append(f"Near upper BB ({bb_pct:.0%})")
            elif bb_pct > 0.6:
                sell_score += 5

    # ══════════════════════════════════════════════════════════════
    #  DECISION
    # ══════════════════════════════════════════════════════════════
    stop_loss = 0.0
    take_profit = 0.0

    if buy_score >= 45 and buy_score > sell_score + 10:
        stop_loss = round(close - 1.5 * atr_val, 2)
        take_profit = round(close + 2.5 * atr_val, 2)
        decision = "BUY"
        confidence = min(buy_score, 100)

    elif sell_score >= 45 and sell_score > buy_score + 10:
        stop_loss = round(close + 1.5 * atr_val, 2)
        take_profit = round(close - 2.5 * atr_val, 2)
        decision = "SELL"
        confidence = min(sell_score, 100)
        reasons = sell_reasons

    else:
        decision = "HOLD"
        confidence = max(buy_score, sell_score)
        reasons = ["No clear signal"]

    signal = {
        "decision": decision,
        "confidence": confidence,
        "reason": " | ".join(reasons[:3]),  # top 3 reasons
        "stop_loss": stop_loss,
        "take_profit": take_profit,
    }

    if decision != "HOLD":
        logger.info(f"Signal: {decision} ({confidence}%) — {signal['reason']}")

    return signal


def _hold(reason: str) -> dict:
    return {"decision": "HOLD", "confidence": 0, "reason": reason, "stop_loss": 0, "take_profit": 0}


# ═════════════════════════════════════════════════════════════════════════════
#  BACKTESTER
# ═════════════════════════════════════════════════════════════════════════════

def backtest(df: pd.DataFrame) -> pd.DataFrame:
    trades = []
    position = None
    prev_row = None

    for idx, row in df.iterrows():
        signal = generate_signal(row, prev_row)

        if position is not None:
            current_price = row["Close"]
            atr_val = row.get("ATR", 0)
            atr_val = atr_val if not pd.isna(atr_val) else current_price * 0.01

            # Trailing stop
            if atr_val > 0:
                new_trail = current_price - 1.5 * atr_val
                if new_trail > position["trailing_stop"]:
                    position["trailing_stop"] = new_trail

            if current_price <= position["trailing_stop"]:
                pnl = (current_price - position["entry_price"]) * position["qty"]
                trades.append({"datetime": idx, "action": "STOP", "price": round(current_price, 2), "confidence": 0, "reason": "Trailing stop hit", "pnl": round(pnl, 2), "qty": position["qty"]})
                position = None
                prev_row = row
                continue

            if current_price >= position["take_profit"]:
                pnl = (current_price - position["entry_price"]) * position["qty"]
                trades.append({"datetime": idx, "action": "TAKE_PROFIT", "price": round(current_price, 2), "confidence": 100, "reason": "Target hit", "pnl": round(pnl, 2), "qty": position["qty"]})
                position = None
                prev_row = row
                continue

            if signal["decision"] == "SELL":
                pnl = (current_price - position["entry_price"]) * position["qty"]
                trades.append({"datetime": idx, "action": "SELL", "price": round(current_price, 2), "confidence": signal["confidence"], "reason": signal["reason"], "pnl": round(pnl, 2), "qty": position["qty"]})
                position = None
                prev_row = row
                continue

        if position is None and signal["decision"] == "BUY":
            entry_price = row["Close"]
            atr_val = row.get("ATR", 0)
            atr_val = atr_val if not pd.isna(atr_val) else entry_price * 0.01
            risk = entry_price - signal["stop_loss"]
            qty = max(1, int(100 / risk)) if risk > 0 else 1

            position = {
                "entry_price": entry_price,
                "stop_loss": signal["stop_loss"],
                "take_profit": signal["take_profit"],
                "trailing_stop": signal["stop_loss"],
                "qty": qty,
            }
            trades.append({"datetime": idx, "action": "BUY", "price": round(entry_price, 2), "confidence": signal["confidence"], "reason": signal["reason"], "pnl": 0, "qty": qty})

        prev_row = row

    if position is not None:
        last_price = df.iloc[-1]["Close"]
        pnl = (last_price - position["entry_price"]) * position["qty"]
        trades.append({"datetime": df.index[-1], "action": "CLOSE_EOD", "price": round(last_price, 2), "confidence": 0, "reason": "Session end", "pnl": round(pnl, 2), "qty": position["qty"]})

    return pd.DataFrame(trades)
