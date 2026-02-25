"""
Anti-Gravity — Execution Engine
Handles order placement.  Paper-trade mode logs to CSV; live mode is a skeleton
for Angel One SmartAPI integration.
"""

import csv
import os
import logging
from datetime import datetime

logger = logging.getLogger("anti_gravity.execution")


class BrokerAPI:
    """
    Unified order interface.

    Modes:
        paper=True  → orders logged to CSV (no real money)
        paper=False → (future) routes to Angel One SmartAPI
    """

    def __init__(self, paper: bool = True, trade_log_path: str = "logs/trades.csv"):
        self.paper = paper
        self.trade_log_path = trade_log_path
        self.positions: dict = {}  # symbol → {qty, entry_price, side}
        self._ensure_log_file()

    # ── Internal helpers ─────────────────────────────────────────────────
    def _ensure_log_file(self):
        os.makedirs(os.path.dirname(self.trade_log_path), exist_ok=True)
        if not os.path.exists(self.trade_log_path):
            with open(self.trade_log_path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow([
                    "timestamp", "symbol", "side", "qty", "price",
                    "order_type", "status", "pnl", "mode",
                ])

    def _log_trade(self, symbol, side, qty, price, order_type, status, pnl=0.0):
        with open(self.trade_log_path, "a", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                datetime.now().isoformat(),
                symbol, side, qty, round(price, 2),
                order_type, status, round(pnl, 2),
                "PAPER" if self.paper else "LIVE",
            ])

    # ── Paper trade execution ────────────────────────────────────────────
    def _paper_order(self, symbol: str, side: str, qty: int, price: float, order_type: str = "MARKET") -> dict:
        """Simulate an order and log it."""
        pnl = 0.0

        if side == "BUY":
            self.positions[symbol] = {"qty": qty, "entry_price": price, "side": "LONG"}
            logger.info(f"📗 PAPER BUY  {qty} x {symbol} @ ₹{price:,.2f}")

        elif side == "SELL":
            if symbol in self.positions:
                entry = self.positions[symbol]["entry_price"]
                pnl = (price - entry) * self.positions[symbol]["qty"]
                logger.info(
                    f"📕 PAPER SELL {self.positions[symbol]['qty']} x {symbol} "
                    f"@ ₹{price:,.2f} | PnL ₹{pnl:,.2f}"
                )
                del self.positions[symbol]
            else:
                logger.warning(f"No open position for {symbol} — SELL ignored")
                return {"status": "REJECTED", "reason": "No position"}

        self._log_trade(symbol, side, qty, price, order_type, "FILLED", pnl)

        return {
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "price": price,
            "pnl": round(pnl, 2),
        }

    # ── Live trade execution (skeleton) ──────────────────────────────────
    def _live_order(self, symbol: str, side: str, qty: int, price: float, order_type: str = "MARKET") -> dict:
        """
        Placeholder for Angel One SmartAPI integration.
        Replace this with actual API calls when ready for live trading.
        """
        logger.warning("LIVE trading not yet implemented — falling back to paper")
        return self._paper_order(symbol, side, qty, price, order_type)

    # ── Public interface ─────────────────────────────────────────────────
    def place_order(
        self,
        symbol: str,
        side: str,
        qty: int,
        price: float,
        order_type: str = "MARKET",
    ) -> dict:
        """
        Place a BUY or SELL order.

        Args:
            symbol:     Ticker symbol
            side:       "BUY" or "SELL"
            qty:        Number of shares
            price:      Current price / limit price
            order_type: "MARKET" or "LIMIT"

        Returns:
            dict with status, pnl, etc.
        """
        if qty <= 0:
            logger.warning("Quantity is 0 — order skipped")
            return {"status": "SKIPPED", "reason": "qty=0"}

        if self.paper:
            return self._paper_order(symbol, side, qty, price, order_type)
        else:
            return self._live_order(symbol, side, qty, price, order_type)

    def get_open_positions(self) -> dict:
        return self.positions.copy()

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions


# ─── Quick smoke test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    broker = BrokerAPI(paper=True, trade_log_path="logs/trades.csv")
    broker.place_order("RELIANCE.NS", "BUY", 5, 2500)
    broker.place_order("RELIANCE.NS", "SELL", 5, 2550)
    print(f"Open positions: {broker.get_open_positions()}")
