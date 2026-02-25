"""
Anti-Gravity — Training Data Logger
Records every signal, indicator snapshot, and trade outcome for ML training.
Accumulates data over weeks to build a dataset for strategy optimization.
"""

import csv
import os
import logging
from datetime import datetime

logger = logging.getLogger("anti_gravity.training")


class TrainingLogger:
    """
    Logs every analysis cycle with full indicator state + signal + outcome.
    After weeks of data, this can train a model to predict profitable setups.
    """

    SIGNAL_COLUMNS = [
        "timestamp", "symbol", "interval",
        "close", "ema_fast", "ema_slow", "ema_spread_pct",
        "rsi", "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_pct",
        "atr", "volume", "vol_sma",
        "decision", "confidence", "reason",
        "stop_loss", "take_profit",
    ]

    OUTCOME_COLUMNS = [
        "timestamp", "symbol", "action", "entry_price", "exit_price",
        "pnl", "pnl_pct", "hold_bars", "exit_reason",
    ]

    def __init__(self, log_dir: str):
        self.log_dir = log_dir
        self.signal_path = os.path.join(log_dir, "training_signals.csv")
        self.outcome_path = os.path.join(log_dir, "training_outcomes.csv")
        os.makedirs(log_dir, exist_ok=True)
        self._ensure_file(self.signal_path, self.SIGNAL_COLUMNS)
        self._ensure_file(self.outcome_path, self.OUTCOME_COLUMNS)
        self._entry_tracker = {}  # symbol -> {time, price, bar_count}

    def _ensure_file(self, path, columns):
        if not os.path.exists(path):
            with open(path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(columns)

    def log_signal(self, symbol: str, row, signal: dict, interval: str = "5m"):
        """Log every indicator snapshot + signal decision."""
        try:
            close = row.get("Close", 0)
            ema_f = row.get("EMA_fast", 0)
            ema_s = row.get("EMA_slow", 0)
            spread = (ema_f - ema_s) / ema_s * 100 if ema_s else 0

            record = [
                datetime.now().isoformat(),
                symbol, interval,
                round(close, 4),
                round(ema_f, 4), round(ema_s, 4), round(spread, 4),
                round(row.get("RSI", 0), 2),
                round(row.get("MACD", 0), 4),
                round(row.get("MACD_signal", 0), 4),
                round(row.get("MACD_hist", 0), 4),
                round(row.get("BB_upper", 0), 4),
                round(row.get("BB_lower", 0), 4),
                round(row.get("BB_pct", 0), 4),
                round(row.get("ATR", 0), 4),
                int(row.get("Volume", 0)),
                int(row.get("Vol_SMA", 0)),
                signal.get("decision", ""),
                signal.get("confidence", 0),
                signal.get("reason", "")[:100],
                signal.get("stop_loss", 0),
                signal.get("take_profit", 0),
            ]

            with open(self.signal_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(record)

        except Exception as e:
            logger.error(f"Signal log error: {e}")

    def log_entry(self, symbol: str, price: float):
        """Track when a position was entered."""
        self._entry_tracker[symbol] = {
            "time": datetime.now().isoformat(),
            "price": price,
            "bars": 0,
        }

    def tick_bar(self, symbol: str):
        """Count bars while position is held."""
        if symbol in self._entry_tracker:
            self._entry_tracker[symbol]["bars"] += 1

    def log_exit(self, symbol: str, exit_price: float, pnl: float, reason: str):
        """Log a completed trade with outcome for training."""
        try:
            entry = self._entry_tracker.pop(symbol, None)
            entry_price = entry["price"] if entry else 0
            hold_bars = entry["bars"] if entry else 0
            pnl_pct = (pnl / entry_price * 100) if entry_price else 0

            record = [
                datetime.now().isoformat(),
                symbol, "SELL", round(entry_price, 4), round(exit_price, 4),
                round(pnl, 2), round(pnl_pct, 4), hold_bars, reason,
            ]

            with open(self.outcome_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(record)

            logger.info(f"Training outcome: {symbol} P&L={pnl:.2f} ({pnl_pct:.2f}%) held {hold_bars} bars")
        except Exception as e:
            logger.error(f"Outcome log error: {e}")

    def get_stats(self) -> dict:
        """Return training data stats."""
        sig_count = self._count_rows(self.signal_path)
        out_count = self._count_rows(self.outcome_path)
        return {
            "signal_samples": sig_count,
            "outcome_samples": out_count,
            "signal_file": self.signal_path,
            "outcome_file": self.outcome_path,
        }

    def _count_rows(self, path):
        if not os.path.exists(path):
            return 0
        with open(path, "r", encoding="utf-8") as f:
            return max(0, sum(1 for _ in f) - 1)  # minus header
