"""
Anti-Gravity — Virtual Execution Engine (Professional Ledger Model)

Proper accounting:
  cash           = liquid money available
  position_value = mark-to-market value of holdings (qty × current_price)
  equity         = cash + position_value
  unrealized_pnl = position_value − entry_cost (per position)
  realized_pnl   = cumulative profit from closed trades

Position sizing uses EQUITY, not cash.
"""

import csv
import os
import logging
from datetime import datetime

logger = logging.getLogger("anti_gravity.paper_broker")


class PaperBroker:
    """
    Professional-grade virtual broker with proper accounting.

    Ledger model:
        ledger = {
            "cash": 251.42,
            "positions": {
                "AAPL": {"qty": 2, "entry_price": 274.29, "entry_cost": 548.58}
            }
        }

    Equity is computed dynamically from ledger + current market prices.
    """

    def __init__(self, starting_capital: float = 800, log_dir: str = "logs"):
        self.starting_capital = starting_capital
        self.cash = starting_capital          # ★ liquid money only
        self.positions = {}                   # symbol → {qty, entry_price, entry_cost}
        self.current_prices = {}              # symbol → latest market price
        self.realized_pnl = 0.0               # cumulative closed-trade P&L
        self.wins = 0
        self.losses = 0
        self.trade_history = []
        self.log_dir = log_dir
        self.log_path = os.path.join(log_dir, "paper_trades.csv")
        os.makedirs(log_dir, exist_ok=True)
        self._ensure_log()

    # ── Core accounting ──────────────────────────────────────────────

    def update_price(self, symbol: str, price: float):
        """Mark-to-market: update the latest price for a symbol."""
        self.current_prices[symbol] = price

    def position_value(self) -> float:
        """Total market value of all open positions at current prices."""
        total = 0.0
        for sym, pos in self.positions.items():
            price = self.current_prices.get(sym, pos["entry_price"])
            total += pos["qty"] * price
        return round(total, 2)

    def entry_cost(self) -> float:
        """Total cost basis of all open positions."""
        return round(sum(p["entry_cost"] for p in self.positions.values()), 2)

    def equity(self) -> float:
        """cash + position_value — the true portfolio worth."""
        return round(self.cash + self.position_value(), 2)

    def unrealized_pnl(self) -> float:
        """position_value − entry_cost."""
        return round(self.position_value() - self.entry_cost(), 2)

    def total_pnl(self) -> float:
        """realized + unrealized."""
        return round(self.realized_pnl + self.unrealized_pnl(), 2)

    def unrealized_per_position(self) -> dict:
        """Unrealized P&L per symbol."""
        result = {}
        for sym, pos in self.positions.items():
            price = self.current_prices.get(sym, pos["entry_price"])
            result[sym] = round((price - pos["entry_price"]) * pos["qty"], 2)
        return result

    # ── Trade execution ──────────────────────────────────────────────

    def buy(self, symbol: str, price: float, qty: int = 0) -> dict:
        """
        Buy shares. Auto-calculates qty from EQUITY-based position sizing.
        Deducts from cash.
        """
        if price <= 0:
            return {"status": "REJECTED", "reason": "Invalid price"}

        self.update_price(symbol, price)

        # Auto qty: risk 2% of EQUITY (not cash!)
        if qty <= 0:
            risk_amount = self.equity() * 0.02
            qty = max(1, int(risk_amount / price))
            # But can't spend more cash than we have
            max_affordable = int(self.cash / price)
            qty = min(qty, max_affordable)
            if qty <= 0:
                return {"status": "REJECTED", "reason": f"Insufficient cash (₹{self.cash:.2f})"}

        cost = price * qty
        if cost > self.cash:
            qty = int(self.cash / price)
            if qty <= 0:
                return {"status": "REJECTED", "reason": "Insufficient cash"}
            cost = price * qty

        # Deduct cash
        self.cash -= cost

        # Update position (average in if already holding)
        if symbol in self.positions:
            old = self.positions[symbol]
            total_qty = old["qty"] + qty
            total_cost = old["entry_cost"] + cost
            self.positions[symbol] = {
                "qty": total_qty,
                "entry_price": round(total_cost / total_qty, 4),
                "entry_cost": round(total_cost, 2),
            }
        else:
            self.positions[symbol] = {
                "qty": qty,
                "entry_price": round(price, 4),
                "entry_cost": round(cost, 2),
            }

        trade = self._make_trade(symbol, "BUY", price, qty, 0)
        self.trade_history.append(trade)
        self._log_csv(trade)

        logger.info(
            f"📗 BUY {qty}x {symbol} @ ₹{price:.2f} | "
            f"Cash: ₹{self.cash:.2f} | Equity: ₹{self.equity():.2f}"
        )
        return {"status": "FILLED", "qty": qty, "cost": cost, "pnl": 0}

    def sell(self, symbol: str, price: float, qty: int = 0) -> dict:
        """
        Sell shares. Adds to cash, calculates realized P&L.
        """
        if symbol not in self.positions:
            return {"status": "REJECTED", "reason": "No position"}

        self.update_price(symbol, price)
        pos = self.positions[symbol]
        if qty <= 0:
            qty = pos["qty"]
        qty = min(qty, pos["qty"])

        revenue = price * qty
        cost_basis = pos["entry_price"] * qty
        pnl = round(revenue - cost_basis, 2)

        # Add revenue to cash
        self.cash += revenue
        self.realized_pnl += pnl

        if pnl > 0:
            self.wins += 1
        elif pnl < 0:
            self.losses += 1

        # Update or remove position
        remaining = pos["qty"] - qty
        if remaining > 0:
            self.positions[symbol] = {
                "qty": remaining,
                "entry_price": pos["entry_price"],
                "entry_cost": round(pos["entry_price"] * remaining, 2),
            }
        else:
            del self.positions[symbol]

        trade = self._make_trade(symbol, "SELL", price, qty, pnl)
        self.trade_history.append(trade)
        self._log_csv(trade)

        emoji = "💰" if pnl >= 0 else "📉"
        logger.info(
            f"{emoji} SELL {qty}x {symbol} @ ₹{price:.2f} | "
            f"P&L: ₹{pnl:.2f} | Cash: ₹{self.cash:.2f} | Equity: ₹{self.equity():.2f}"
        )
        return {"status": "FILLED", "qty": qty, "pnl": pnl}

    # ── Query methods ────────────────────────────────────────────────

    def has_position(self, symbol: str) -> bool:
        return symbol in self.positions

    def get_position(self, symbol: str) -> dict:
        return self.positions.get(symbol, {})

    def get_status(self) -> dict:
        """Full accounting snapshot for the dashboard."""
        pos_value = self.position_value()
        eq = self.equity()
        unr_pnl = self.unrealized_pnl()
        unr_per = self.unrealized_per_position()

        return {
            # ★ Core accounting (all 5 variables)
            "cash": round(self.cash, 2),
            "position_value": pos_value,
            "equity": eq,
            "unrealized_pnl": unr_pnl,
            "realized_pnl": round(self.realized_pnl, 2),
            "total_pnl": round(self.realized_pnl + unr_pnl, 2),
            "total_pnl_pct": round((eq - self.starting_capital) / self.starting_capital * 100, 2),
            "starting_capital": self.starting_capital,
            # Stats
            "wins": self.wins,
            "losses": self.losses,
            "win_rate": round(self.wins / (self.wins + self.losses) * 100, 1) if (self.wins + self.losses) > 0 else 0,
            "trade_count": len(self.trade_history),
            # Positions with unrealized P&L
            "open_positions": {
                s: {
                    "qty": p["qty"],
                    "entry": round(p["entry_price"], 2),
                    "current": round(self.current_prices.get(s, p["entry_price"]), 2),
                    "value": round(self.current_prices.get(s, p["entry_price"]) * p["qty"], 2),
                    "unrealized": unr_per.get(s, 0),
                }
                for s, p in self.positions.items()
            },
            "trades": self.trade_history[-30:],
        }

    # ── Internal helpers ─────────────────────────────────────────────

    def _make_trade(self, symbol, action, price, qty, pnl):
        return {
            "time": datetime.now().strftime("%H:%M:%S"),
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "action": action,
            "price": round(price, 2),
            "qty": qty,
            "pnl": round(pnl, 2),
            "cash_after": round(self.cash, 2),
            "equity_after": round(self.equity(), 2),
        }

    def _ensure_log(self):
        if not os.path.exists(self.log_path):
            with open(self.log_path, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    "timestamp", "symbol", "action", "price", "qty",
                    "pnl", "cash_after", "equity_after", "position_value",
                ])

    def _log_csv(self, trade):
        try:
            with open(self.log_path, "a", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow([
                    trade["timestamp"], trade["symbol"], trade["action"],
                    trade["price"], trade["qty"], trade["pnl"],
                    trade["cash_after"], trade["equity_after"],
                    self.position_value(),
                ])
        except Exception as e:
            logger.error(f"CSV log error: {e}")
