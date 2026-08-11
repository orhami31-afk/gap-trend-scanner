"""
history_tracker.py
--------------------
עוקב אחרי המלצות שהמערכת נתנה בעבר, ומעדכן האם המניה הגיעה ליעד הרווח,
לסטופ, עדיין פתוחה, או פג תוקף (עברה את חלון האחזקה המקסימלי בלי להכריע).

קורא קבצי scan_YYYY-MM-DD.json מתיקיית history/, מושך נתונים עדכניים לכל
סימול פתוח, ומעדכן את שדה "outcome" בקובץ המקורי במקום.
"""

from __future__ import annotations
import json
import os
import glob
import logging
from datetime import datetime, timedelta

from data_provider import DataProvider

logger = logging.getLogger("gap_trend_bot.history")

HISTORY_DIR = "history"


def save_scan_results(scan_date: str, results: list[dict]):
    os.makedirs(HISTORY_DIR, exist_ok=True)
    path = os.path.join(HISTORY_DIR, f"scan_{scan_date}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved {len(results)} results to {path}")


def load_all_history() -> list[dict]:
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "scan_*.json")))
    all_days = []
    for fpath in files:
        with open(fpath, encoding="utf-8") as f:
            day_results = json.load(f)
        date_str = os.path.basename(fpath).replace("scan_", "").replace(".json", "")
        all_days.append({"date": date_str, "results": day_results})
    return all_days


def update_outcomes(provider: DataProvider):
    """
    עובר על כל ההיסטוריה, ולכל המלצה שעדיין "open" (לא הוכרעה) בודק אם
    בינתיים המחיר נגע ביעד או בסטופ, או שעבר זמן האחזקה המקסימלי (expired).
    """
    files = sorted(glob.glob(os.path.join(HISTORY_DIR, "scan_*.json")))
    price_cache: dict[str, "pd.DataFrame"] = {}

    for fpath in files:
        with open(fpath, encoding="utf-8") as f:
            results = json.load(f)

        scan_date_str = os.path.basename(fpath).replace("scan_", "").replace(".json", "")
        scan_date = datetime.strptime(scan_date_str, "%Y-%m-%d")
        changed = False

        for rec in results:
            if rec.get("outcome") not in (None, "open"):
                continue  # כבר הוכרע - אין צורך לבדוק שוב

            symbol = rec["symbol"]
            if symbol not in price_cache:
                try:
                    price_cache[symbol] = provider.get_daily_bars(symbol, lookback_days=30)
                except Exception as e:
                    logger.warning(f"Could not fetch data for {symbol}: {e}")
                    continue

            bars = price_cache[symbol]
            bars_since = bars[bars.index > scan_date]
            if bars_since.empty:
                continue

            direction = rec["direction"]
            target = rec["target"]
            stop = rec["stop"]
            max_hold = rec.get("suggested_hold_days", 10)

            outcome = "open"
            outcome_date = None
            for date, bar in bars_since.iterrows():
                days_elapsed = (date - scan_date).days
                if direction == "long":
                    hit_target = bar["high"] >= target
                    hit_stop = bar["low"] <= stop
                else:
                    hit_target = bar["low"] <= target
                    hit_stop = bar["high"] >= stop

                if hit_target and hit_stop:
                    outcome = "stop_hit"  # שמרני
                    outcome_date = str(date.date())
                    break
                if hit_target:
                    outcome = "target_hit"
                    outcome_date = str(date.date())
                    break
                if hit_stop:
                    outcome = "stop_hit"
                    outcome_date = str(date.date())
                    break
                if days_elapsed >= max_hold:
                    outcome = "expired"
                    outcome_date = str(date.date())
                    break

            if outcome != rec.get("outcome", "open"):
                rec["outcome"] = outcome
                rec["outcome_date"] = outcome_date
                changed = True

        if changed:
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"Updated outcomes in {fpath}")
