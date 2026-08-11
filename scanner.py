"""
scanner.py
-----------
המנוע המרכזי: מריץ את כל שלבי הסריקה (1->5) על רשימת מניות,
ומייצר/מנהל עסקאות דרך ה-broker.
"""

from __future__ import annotations
import logging
from typing import List

from datetime import date
from config import CONFIG
from data_provider import DataProvider
from universe import filter_universe
from sentiment_filter import MarketSentiment
from entry_signals import evaluate_entry
from risk_manager import build_trade_plan, update_breakeven, estimate_holding_days
from trade_logger import log_new_trade, log_breakeven_move, log_scan_summary
from broker import BrokerInterface
from backtest import backtest_symbol

logger = logging.getLogger("gap_trend_bot.scanner")


class GapTrendScanner:
    def __init__(self, provider: DataProvider, broker: BrokerInterface, watchlist: List[str]):
        self.provider = provider
        self.broker = broker
        self.watchlist = watchlist
        self.sentiment = MarketSentiment(provider, CONFIG.sentiment)
        self.active_plans = {}  # symbol -> TradePlan
        self.last_results: list[dict] = []  # תוצאות הסריקה האחרונה, מוכן לפלט JSON

    def run_daily_scan(self, place_orders: bool = False, max_hold_days: int = 10) -> list[dict]:
        """
        רץ פעם ביום: מסנן יקום ראשוני, בודק תנאי כניסה על כל מועמד, ומחשב עבור
        כל מניה שעברה: תוכנית עסקה, אומדן ימי אחזקה, ואחוז הצלחה משוער (backtest).

        place_orders=False (ברירת מחדל): לא שולח שום פקודה לברוקר - רק מייצר
        את רשימת ההמלצות. זה המצב הרלוונטי לשימוש כ"תמונת מצב יומית" בלי ביצוע אוטומטי.
        """
        logger.info("=" * 70)
        logger.info(f"Starting daily scan | watchlist size = {len(self.watchlist)}")

        self.sentiment.refresh()

        snapshot = self.provider.get_universe_snapshot(self.watchlist)
        candidates = filter_universe(snapshot, CONFIG.universe)

        results = []
        for _, row in candidates.iterrows():
            symbol = row["symbol"]
            try:
                daily_df = self.provider.get_daily_bars(symbol, lookback_days=400)
                intraday_df = self.provider.get_intraday_bars(
                    symbol, interval=CONFIG.entry.intraday_timeframe, lookback_days=5
                )
                if daily_df.empty or intraday_df.empty:
                    continue

                signal = evaluate_entry(
                    symbol, daily_df, intraday_df, row["gap_direction"], CONFIG, self.sentiment
                )
                if not signal.passed:
                    logger.debug(f"{symbol}: rejected - {signal.fail_reason}")
                    continue

                plan = build_trade_plan(
                    symbol, signal.direction, signal.entry_price, intraday_df, CONFIG.risk
                )
                hold_days = estimate_holding_days(
                    daily_df, plan.entry_price, plan.take_profit, min_days=1, max_days=max_hold_days
                )
                bt = backtest_symbol(daily_df, signal.direction, CONFIG,
                                      risk_reward_ratio=CONFIG.risk.risk_reward_ratio,
                                      max_hold_days=max_hold_days)

                record = {
                    "symbol": symbol,
                    "direction": signal.direction,
                    "entry": round(plan.entry_price, 2),
                    "stop": round(plan.stop_loss, 2),
                    "target": round(plan.take_profit, 2),
                    "shares": plan.shares,
                    "risk_usd": plan.risk_usd,
                    "reward_usd": plan.reward_usd,
                    "suggested_hold_days": hold_days,
                    "estimated_success_pct": bt.win_rate_pct,
                    "backtest_sample_size": bt.sample_size,
                    "scan_date": str(date.today()),
                    "outcome": "open",
                    "outcome_date": None,
                }
                results.append(record)

                if place_orders:
                    self.broker.place_entry_order(plan)
                    self.active_plans[symbol] = plan
                    log_new_trade(plan)

            except Exception as e:
                logger.exception(f"Error processing {symbol}: {e}")

        self.last_results = results
        log_scan_summary(len(self.watchlist), len(candidates), len(results))
        return results

    def monitor_open_positions(self):
        """
        רץ בתדירות גבוהה יותר (למשל כל כמה דקות תוך יום המסחר): בודק אם עסקאות
        פתוחות הגיעו ל-1:1 כדי לגרור סטופ ל-breakeven, ואם הגיעו לתוקף
        ההחזקה המקסימלי (max_holding_days) לצורך סגירה.
        """
        for symbol, plan in list(self.active_plans.items()):
            try:
                latest = self.provider.get_intraday_bars(symbol, interval="15m", lookback_days=1)
                if latest.empty:
                    continue
                current_price = float(latest["close"].iloc[-1])

                updated_plan = update_breakeven(plan, current_price, CONFIG.risk)
                if updated_plan.breakeven_triggered and updated_plan.stop_loss != plan.stop_loss:
                    self.broker.update_stop_loss(symbol, updated_plan.stop_loss)
                    log_breakeven_move(updated_plan)
                self.active_plans[symbol] = updated_plan

            except Exception as e:
                logger.exception(f"Error monitoring {symbol}: {e}")
