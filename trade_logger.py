"""
trade_logger.py
-----------------
שלב 5: לוגים ובקרה - הדפסה מסודרת למסוף (ואופציונלית לקובץ) לכל עסקה.
"""

from __future__ import annotations
import logging
import sys
from datetime import datetime
from risk_manager import TradePlan


def setup_logging(log_file: str = "gap_trend_bot.log", level=logging.INFO):
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)-28s | %(levelname)-7s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


trade_logger = logging.getLogger("gap_trend_bot.trades")


def log_new_trade(plan: TradePlan):
    trade_logger.info(
        "NEW TRADE | %s | %s | entry=%.2f | stop=%.2f | target=%.2f | shares=%d | risk=$%.2f | reward=$%.2f | time=%s",
        plan.symbol,
        plan.direction.upper(),
        plan.entry_price,
        plan.stop_loss,
        plan.take_profit,
        plan.shares,
        plan.risk_usd,
        plan.reward_usd,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def log_breakeven_move(plan: TradePlan):
    trade_logger.info(
        "BREAKEVEN | %s | stop moved to entry price %.2f | time=%s",
        plan.symbol,
        plan.stop_loss,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def log_trade_closed(symbol: str, reason: str, exit_price: float, pnl_usd: float):
    trade_logger.info(
        "TRADE CLOSED | %s | reason=%s | exit=%.2f | PnL=$%.2f | time=%s",
        symbol, reason, exit_price, pnl_usd,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


def log_scan_summary(total_scanned: int, passed_universe: int, entries_found: int):
    trade_logger.info(
        "SCAN SUMMARY | scanned=%d | passed_universe_filter=%d | entry_signals=%d",
        total_scanned, passed_universe, entries_found,
    )
