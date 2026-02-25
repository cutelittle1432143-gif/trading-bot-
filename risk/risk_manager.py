"""
Anti-Gravity — Risk Manager
Controls position sizing, stop-losses, drawdown limits, and trade cooldowns.
"""

import logging
from datetime import datetime, date

logger = logging.getLogger("anti_gravity.risk")


class RiskManager:
    """
    Capital protector.

    Rules enforced:
        1. Never risk more than `risk_pct` of capital per trade.
        2. Stop trading if daily loss exceeds `max_daily_loss_pct`.
        3. Cool down after `cooldown_threshold` consecutive losses.
    """

    def __init__(
        self,
        capital: float = 10_000,
        risk_pct: float = 0.01,
        max_daily_loss_pct: float = 0.03,
        cooldown_threshold: int = 3,
        max_open_positions: int = 3,
    ):
        self.initial_capital = capital
        self.capital = capital
        self.risk_pct = risk_pct
        self.max_daily_loss_pct = max_daily_loss_pct
        self.cooldown_threshold = cooldown_threshold
        self.max_open_positions = max_open_positions

        # Running state
        self.daily_pnl = 0.0
        self.consecutive_losses = 0
        self.open_positions = 0
        self.today = date.today()
        self.trades_today = 0

    # ── Daily reset ──────────────────────────────────────────────────────
    def _check_day_reset(self):
        if date.today() != self.today:
            logger.info("New trading day — resetting daily counters")
            self.daily_pnl = 0.0
            self.trades_today = 0
            self.today = date.today()

    # ── Position sizing ──────────────────────────────────────────────────
    def calculate_position_size(self, entry_price: float, stop_loss: float) -> int:
        """
        Calculate the number of shares to buy such that a stop-loss exit
        loses at most `risk_pct` of current capital.

        Returns:
            Number of shares (integer).  0 means "do not trade".
        """
        self._check_day_reset()
        risk_amount = self.capital * self.risk_pct          # e.g. ₹100
        price_risk = abs(entry_price - stop_loss)           # per-share risk

        if price_risk <= 0:
            logger.warning("Invalid stop-loss — price_risk <= 0")
            return 0

        qty = int(risk_amount / price_risk)
        # Ensure we can actually afford the position
        max_affordable = int(self.capital / entry_price)
        qty = min(qty, max_affordable)
        qty = max(qty, 0)

        logger.info(
            f"Position size: {qty} shares | "
            f"risk ₹{risk_amount:.2f} | per-share risk ₹{price_risk:.2f}"
        )
        return qty

    # ── Pre-trade gate ───────────────────────────────────────────────────
    def can_trade(self) -> tuple[bool, str]:
        """
        Returns (allowed, reason).  Check this BEFORE placing any order.
        """
        self._check_day_reset()

        max_daily = self.capital * self.max_daily_loss_pct
        if self.daily_pnl <= -max_daily:
            msg = f"Daily loss limit hit (₹{self.daily_pnl:,.2f} / -₹{max_daily:,.2f})"
            logger.warning(msg)
            return False, msg

        if self.consecutive_losses >= self.cooldown_threshold:
            msg = f"Cooldown active — {self.consecutive_losses} consecutive losses"
            logger.warning(msg)
            return False, msg

        if self.open_positions >= self.max_open_positions:
            msg = f"Max open positions reached ({self.open_positions}/{self.max_open_positions})"
            logger.warning(msg)
            return False, msg

        return True, "OK"

    # ── Record trade result ──────────────────────────────────────────────
    def record_trade(self, pnl: float):
        """Update internal state after a trade closes."""
        self.daily_pnl += pnl
        self.capital += pnl
        self.trades_today += 1

        if pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0

        logger.info(
            f"Trade recorded | PnL ₹{pnl:,.2f} | "
            f"Capital ₹{self.capital:,.2f} | "
            f"Daily PnL ₹{self.daily_pnl:,.2f} | "
            f"Consec losses {self.consecutive_losses}"
        )

    def open_position(self):
        self.open_positions += 1

    def close_position(self):
        self.open_positions = max(0, self.open_positions - 1)

    # ── Summary ──────────────────────────────────────────────────────────
    def status(self) -> dict:
        return {
            "capital": round(self.capital, 2),
            "daily_pnl": round(self.daily_pnl, 2),
            "consecutive_losses": self.consecutive_losses,
            "open_positions": self.open_positions,
            "trades_today": self.trades_today,
            "can_trade": self.can_trade()[0],
        }


# ─── Quick smoke test ────────────────────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    rm = RiskManager(capital=800, risk_pct=0.01)
    qty = rm.calculate_position_size(entry_price=2500, stop_loss=2470)
    print(f"Position size: {qty} shares")
    print(f"Can trade: {rm.can_trade()}")
    rm.record_trade(-8)
    rm.record_trade(-5)
    rm.record_trade(-3)
    print(f"After 3 losses: {rm.status()}")
