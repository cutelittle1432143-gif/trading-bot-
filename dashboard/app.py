"""
Anti-Gravity — Dashboard with Virtual Paper Trading
Uses PaperBroker (no real broker). Tracks capital, P&L, trades.
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime
from flask import Flask, render_template, jsonify, request

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import config
from data.data_fetcher import fetch_live
from features.indicators import compute_indicators
from strategy.ema_strategy import generate_signal
from strategy.training_logger import TrainingLogger
from execution.paper_broker import PaperBroker

app = Flask(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("app")


# ═════════════════════════════════════════════════════════════════════════════
#  TRADING ENGINE — uses PaperBroker (no real broker)
# ═════════════════════════════════════════════════════════════════════════════

class TradingEngine:
    """Scans watchlist, executes paper trades with real capital tracking."""

    def __init__(self):
        self.running = False
        self.thread = None
        self.watchlist = config.WATCHLIST
        self.poll_interval = 30       # 30s for 5m candles
        self.scan_log = []            # latest scan per symbol
        self.session_start = None
        self.cycles = 0
        self.total_scans = 0
        self.active_symbol = None

        # ★ PaperBroker replaces old BrokerAPI
        self.broker = PaperBroker(
            starting_capital=config.CAPITAL,
            log_dir=config.LOG_DIR,
        )
        self.trainer = TrainingLogger(config.LOG_DIR)

    def start(self, poll_interval: int = 30):
        if self.running:
            return {"status": "already_running"}

        self.poll_interval = poll_interval
        self.running = True
        self.scan_log = []
        self.session_start = datetime.now().isoformat()
        self.cycles = 0
        self.total_scans = 0

        self.thread = threading.Thread(target=self._run_loop, daemon=True)
        self.thread.start()
        logger.info(f"Engine STARTED — ₹{self.broker.capital} capital — scanning {len(self.watchlist)} symbols every {self.poll_interval}s")
        return {"status": "started", "capital": self.broker.capital}

    def stop(self):
        if not self.running:
            return {"status": "not_running"}
        self.running = False
        logger.info(f"Engine STOPPED — Capital: ₹{self.broker.capital:.2f} | P&L: ₹{self.broker.total_pnl:.2f}")
        return {"status": "stopped"}

    def _run_loop(self):
        while self.running:
            self.cycles += 1
            for symbol in self.watchlist:
                if not self.running:
                    break
                self.active_symbol = symbol
                self._scan_symbol(symbol)
            self.active_symbol = None
            if self.running:
                time.sleep(self.poll_interval)

    def _scan_symbol(self, symbol: str):
        try:
            self.total_scans += 1
            ts = datetime.now().strftime("%H:%M:%S")

            # Fetch data
            df = fetch_live(symbol, interval=config.DEFAULT_INTERVAL, lookback="1mo")
            if df.empty or len(df) < 30:
                self._update_scan(symbol, ts, "SKIP", 0, 0, "Insufficient data")
                return

            # Compute indicators
            df = compute_indicators(
                df,
                ema_fast=config.EMA_FAST, ema_slow=config.EMA_SLOW,
                rsi_period=config.RSI_PERIOD,
                macd_fast=config.MACD_FAST, macd_slow=config.MACD_SLOW,
                macd_signal=config.MACD_SIGNAL,
                bb_period=config.BB_PERIOD, bb_std=config.BB_STD,
                atr_period=config.ATR_PERIOD,
            )

            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else None
            signal = generate_signal(latest, prev)
            price = float(latest["Close"])

            # ★ Mark-to-market: update current price for equity calc
            self.broker.update_price(symbol, price)

            # Log for ML training
            self.trainer.log_signal(symbol, latest, signal, config.DEFAULT_INTERVAL)

            # Update scanner display
            self._update_scan(symbol, ts, signal["decision"], round(price, 2),
                            signal["confidence"], signal["reason"][:80])

            # ── EXECUTE TRADES ──────────────────────────────────────
            if signal["decision"] == "BUY" and signal["confidence"] >= config.MIN_CONFIDENCE:
                if not self.broker.has_position(symbol):
                    result = self.broker.buy(symbol, price)
                    if result["status"] == "FILLED":
                        self.trainer.log_entry(symbol, price)
                        logger.info(f"✅ BUY {symbol} @ ₹{price:.2f} | Equity: ₹{self.broker.equity():.2f}")

            elif signal["decision"] == "SELL" and signal["confidence"] >= 50:
                if self.broker.has_position(symbol):
                    result = self.broker.sell(symbol, price)
                    if result["status"] == "FILLED":
                        self.trainer.log_exit(symbol, price, result["pnl"], signal["reason"][:60])
                        logger.info(f"✅ SELL {symbol} @ ₹{price:.2f} | P&L: ₹{result['pnl']:.2f} | Equity: ₹{self.broker.equity():.2f}")

            # ── CHECK STOP-LOSS / TAKE-PROFIT on open positions ─────
            elif self.broker.has_position(symbol):
                pos = self.broker.get_position(symbol)
                entry = pos["entry_price"]
                atr_val = float(latest.get("ATR", 0))
                if atr_val <= 0:
                    atr_val = price * 0.01

                stop_price = entry - 1.5 * atr_val
                tp_price = entry + 2.5 * atr_val

                if price <= stop_price:
                    result = self.broker.sell(symbol, price)
                    if result["status"] == "FILLED":
                        self.trainer.log_exit(symbol, price, result["pnl"], "Stop-loss hit")
                        logger.info(f"🛑 STOP {symbol} @ ₹{price:.2f} | P&L: ₹{result['pnl']:.2f}")

                elif price >= tp_price:
                    result = self.broker.sell(symbol, price)
                    if result["status"] == "FILLED":
                        self.trainer.log_exit(symbol, price, result["pnl"], "Take-profit hit")
                        logger.info(f"💰 TP {symbol} @ ₹{price:.2f} | P&L: ₹{result['pnl']:.2f}")

        except Exception as e:
            logger.error(f"Scan error {symbol}: {e}", exc_info=True)
            self._update_scan(symbol, datetime.now().strftime("%H:%M:%S"),
                            "ERROR", 0, 0, str(e)[:60])

    def _update_scan(self, symbol, ts, decision, price, confidence, reason):
        self.scan_log = [s for s in self.scan_log if s["symbol"] != symbol]
        self.scan_log.append({
            "symbol": symbol, "time": ts, "decision": decision,
            "price": price, "confidence": confidence, "reason": reason,
        })

    def get_status(self):
        broker = self.broker.get_status()
        return {
            "running": self.running,
            "active_symbol": self.active_symbol,
            "cycles": self.cycles,
            "total_scans": self.total_scans,
            "session_start": self.session_start,
            "scan_log": self.scan_log,
            "watchlist_count": len(self.watchlist),
            "min_confidence": config.MIN_CONFIDENCE,
            "training": self.trainer.get_stats(),
            # ★ Proper accounting (5 core variables)
            "cash": broker["cash"],
            "position_value": broker["position_value"],
            "equity": broker["equity"],
            "unrealized_pnl": broker["unrealized_pnl"],
            "realized_pnl": broker["realized_pnl"],
            "total_pnl": broker["total_pnl"],
            "total_pnl_pct": broker["total_pnl_pct"],
            "starting_capital": broker["starting_capital"],
            # Stats
            "wins": broker["wins"],
            "losses": broker["losses"],
            "win_rate": broker["win_rate"],
            "trade_count": broker["trade_count"],
            "open_positions": broker["open_positions"],
            "session_trades": broker["trades"],
        }


# ═════════════════════════════════════════════════════════════════════════════

engine = TradingEngine()


@app.route("/")
def index():
    status = engine.get_status()
    return render_template(
        "index.html",
        trading_status=engine,
        min_confidence=config.MIN_CONFIDENCE,
        watchlist=config.WATCHLIST,
        capital=config.CAPITAL,
    )


@app.route("/api/start", methods=["POST"])
def api_start():
    data = request.get_json(silent=True) or {}
    poll = data.get("poll_interval", 30)
    result = engine.start(poll_interval=int(poll))
    return jsonify(result)


@app.route("/api/stop", methods=["POST"])
def api_stop():
    return jsonify(engine.stop())


@app.route("/api/trading_status")
def api_status():
    return jsonify(engine.get_status())


if __name__ == "__main__":
    print(f"\n  Anti-Gravity Dashboard")
    print(f"  → http://127.0.0.1:5000")
    print(f"  Capital: ₹{config.CAPITAL}")
    print(f"  Confidence: {config.MIN_CONFIDENCE}%")
    print(f"  Watchlist: {len(config.WATCHLIST)} symbols")
    print(f"  Interval: {config.DEFAULT_INTERVAL}\n")
    app.run(host="127.0.0.1", port=5000, debug=False, threaded=True)
