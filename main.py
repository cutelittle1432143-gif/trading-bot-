"""
Anti-Gravity — Main Orchestrator
Wires all layers: Data → Features → Strategy → Risk → Execution.
Supports backtest mode and live (paper) trading loop.
"""

import argparse
import logging
import time
import sys
import os

# Ensure the package root is on path
sys.path.insert(0, os.path.dirname(__file__))

import config
from data.data_fetcher import fetch_historical, fetch_live, get_latest_price
from features.indicators import compute_indicators
from strategy.ema_strategy import generate_signal, backtest
from risk.risk_manager import RiskManager
from execution.broker_api import BrokerAPI

# ── Logging setup ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(name)-30s │ %(levelname)-7s │ %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(config.RUNTIME_LOG, encoding="utf-8"),
    ],
)
logger = logging.getLogger("anti_gravity.main")


# ═════════════════════════════════════════════════════════════════════════════
#  BACKTEST MODE
# ═════════════════════════════════════════════════════════════════════════════
def run_backtest(symbol: str, period: str, interval: str):
    """Run a historical backtest and print a summary."""
    logger.info(f"═══ BACKTEST  {symbol}  period={period}  interval={interval} ═══")

    # 1. Data
    df = fetch_historical(symbol, period, interval)
    if df.empty:
        logger.error("No data — aborting backtest")
        return

    # 2. Features
    df = compute_indicators(
        df,
        ema_fast=config.EMA_FAST,
        ema_slow=config.EMA_SLOW,
        rsi_period=config.RSI_PERIOD,
        macd_fast=config.MACD_FAST,
        macd_slow=config.MACD_SLOW,
        macd_signal=config.MACD_SIGNAL,
        bb_period=config.BB_PERIOD,
        bb_std=config.BB_STD,
        atr_period=config.ATR_PERIOD,
    )

    # 3. Strategy backtest
    trade_log = backtest(df)

    if trade_log.empty:
        logger.info("No trades generated during backtest period.")
        print("\n  No trades generated.\n")
        return

    # 4. Summary
    total_pnl = trade_log["pnl"].sum()
    wins = (trade_log["pnl"] > 0).sum()
    losses = (trade_log["pnl"] < 0).sum()
    total_trades = len(trade_log[trade_log["action"] != "BUY"])  # exits only
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    print("\n" + "═" * 70)
    print(f"  ANTI-GRAVITY BACKTEST RESULTS — {symbol}")
    print("═" * 70)
    print(f"  Period        : {period}")
    print(f"  Interval      : {interval}")
    print(f"  Total trades  : {total_trades}")
    print(f"  Wins          : {wins}")
    print(f"  Losses        : {losses}")
    print(f"  Win rate      : {win_rate:.1f}%")
    print(f"  Total P&L     : ₹{total_pnl:,.2f}")
    print("═" * 70)
    print("\n── Trade Log ──")
    print(trade_log.to_string(index=False))
    print()

    # Save trade log
    log_path = os.path.join(config.LOG_DIR, f"backtest_{symbol.replace('.', '_')}.csv")
    trade_log.to_csv(log_path, index=False)
    logger.info(f"Trade log saved → {log_path}")


# ═════════════════════════════════════════════════════════════════════════════
#  LIVE (PAPER) TRADING LOOP
# ═════════════════════════════════════════════════════════════════════════════
def run_live(symbol: str, interval: str = "5m", poll_seconds: int = 60):
    """Continuous paper-trading loop."""
    logger.info(f"═══ LIVE PAPER TRADING  {symbol}  interval={interval} ═══")

    risk = RiskManager(
        capital=config.CAPITAL,
        risk_pct=config.RISK_PER_TRADE,
        max_daily_loss_pct=config.MAX_DAILY_LOSS,
        cooldown_threshold=config.COOLDOWN_AFTER_LOSSES,
        max_open_positions=config.MAX_OPEN_POSITIONS,
    )
    broker = BrokerAPI(paper=config.PAPER_TRADE, trade_log_path=config.TRADE_LOG)

    print(f"\n  Anti-Gravity live trading started")
    print(f"  Symbol   : {symbol}")
    print(f"  Capital  : ₹{config.CAPITAL:,}")
    print(f"  Mode     : {'PAPER' if config.PAPER_TRADE else 'LIVE'}")
    print(f"  Polling  : every {poll_seconds}s\n")

    while True:
        try:
            # 1. Fetch latest data (3mo lookback for indicator warm-up)
            df = fetch_live(symbol, interval=interval, lookback="3mo")
            if df.empty:
                logger.warning("Empty data — retrying next cycle")
                time.sleep(poll_seconds)
                continue

            # 2. Compute indicators
            df = compute_indicators(
                df,
                ema_fast=config.EMA_FAST,
                ema_slow=config.EMA_SLOW,
                rsi_period=config.RSI_PERIOD,
                macd_fast=config.MACD_FAST,
                macd_slow=config.MACD_SLOW,
                macd_signal=config.MACD_SIGNAL,
                bb_period=config.BB_PERIOD,
                bb_std=config.BB_STD,
                atr_period=config.ATR_PERIOD,
            )

            # 3. Generate signal from latest candle (with prev for confirmation)
            latest = df.iloc[-1]
            prev = df.iloc[-2] if len(df) >= 2 else None
            signal = generate_signal(latest, prev)

            # 4. Risk gate
            can, reason = risk.can_trade()
            if not can:
                logger.info(f"Risk block: {reason}")
                time.sleep(poll_seconds)
                continue

            # 5. Execute
            price = latest["Close"]

            if signal["decision"] == "BUY" and not broker.has_position(symbol):
                if signal["confidence"] >= config.MIN_CONFIDENCE:
                    qty = risk.calculate_position_size(price, signal["stop_loss"])
                    result = broker.place_order(symbol, "BUY", qty, price)
                    if result["status"] == "FILLED":
                        risk.open_position()

            elif signal["decision"] == "SELL" and broker.has_position(symbol):
                result = broker.place_order(symbol, "SELL", 0, price)
                if result["status"] == "FILLED":
                    risk.record_trade(result["pnl"])
                    risk.close_position()

            # Status
            status = risk.status()
            logger.info(
                f"Cycle complete | Signal={signal['decision']} "
                f"({signal['confidence']}%) | Capital=₹{status['capital']:,.2f} | "
                f"Daily PnL=₹{status['daily_pnl']:,.2f}"
            )

            time.sleep(poll_seconds)

        except KeyboardInterrupt:
            logger.info("Shutting down Anti-Gravity…")
            print("\n  Anti-Gravity stopped.\n")
            break
        except Exception as e:
            logger.error(f"Error in trading loop: {e}", exc_info=True)
            time.sleep(poll_seconds)


# ═════════════════════════════════════════════════════════════════════════════
#  CLI
# ═════════════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Anti-Gravity — Elite Algorithmic Trading Bot",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument(
        "--backtest", action="store_true",
        help="Run historical backtest instead of live trading",
    )
    parser.add_argument("--symbol", default=config.SYMBOL, help=f"Ticker symbol (default: {config.SYMBOL})")
    parser.add_argument("--period", default=config.DEFAULT_PERIOD, help=f"Backtest period (default: {config.DEFAULT_PERIOD})")
    parser.add_argument("--interval", default=config.DEFAULT_INTERVAL, help=f"Candle interval (default: {config.DEFAULT_INTERVAL})")
    parser.add_argument("--poll", type=int, default=60, help="Live poll interval in seconds (default: 60)")

    args = parser.parse_args()

    print()
    print("  ╔═══════════════════════════════════════════════╗")
    print("  ║       A N T I - G R A V I T Y   v1.0         ║")
    print("  ║    Elite Algorithmic Trading System           ║")
    print("  ╚═══════════════════════════════════════════════╝")
    print()

    if args.backtest:
        run_backtest(args.symbol, args.period, args.interval)
    else:
        run_live(args.symbol, interval=args.interval, poll_seconds=args.poll)


if __name__ == "__main__":
    main()
