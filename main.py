"""
main.py
--------
נקודת הכניסה להרצת הסריקה היומית המלאה:
1. סורק את היקום (עד ~1000 מניות - ראה watchlist.py)
2. עבור כל מניה שעוברת את כל התנאים - מחשב תוכנית עסקה, אומדן ימי אחזקה,
   ואחוז הצלחה משוער (backtest היסטורי)
3. שומר את תוצאות היום מקומית ל-history/scan_YYYY-MM-DD.json (גיבוי/ארכיון)
4. מעדכן את ההיסטוריה הקודמת - בודק אם המלצות ישנות הגיעו ליעד/לסטופ
5. אם מוגדרים משתני הסביבה של Supabase - כותב הכל ישירות ל-DB, כך שהאפליקציה
   מציגה את זה לבד בלי הדבקה ידנית. אם לא מוגדרים - ממשיך לעבוד כמו קודם
   (רק קובצי JSON מקומיים, עדיין ניתנים להדבקה ידנית).

הרצה ידנית:
    python main.py

הרצה אוטומטית יומית: ראה .github/workflows/daily_scan.yml
לפני הרצה: pip install yfinance pandas numpy requests --break-system-packages
"""

import logging
from datetime import date
from trade_logger import setup_logging
from data_provider import YFinanceProvider
from broker import PaperBroker
from scanner import GapTrendScanner
from history_tracker import save_scan_results, update_outcomes, load_all_history
from watchlist import WATCHLIST
from supabase_writer import push_scan_results, push_outcome_updates


def main():
    setup_logging(log_file="gap_trend_bot.log", level=logging.INFO)
    logger = logging.getLogger("gap_trend_bot.main")

    provider = YFinanceProvider()
    broker = PaperBroker()  # לא שולח פקודות אמיתיות - זו מערכת המלצות בלבד

    scanner = GapTrendScanner(provider, broker, WATCHLIST)

    logger.info(f"Running daily scan across {len(WATCHLIST)} symbols...")
    # place_orders=False בכוונה: המערכת מייצרת רשימת המלצות בלבד, לא מבצעת מסחר
    results = scanner.run_daily_scan(place_orders=False, max_hold_days=10)
    logger.info(f"Found {len(results)} qualifying setups today.")

    save_scan_results(str(date.today()), results)

    pushed_today = push_scan_results(results)
    if pushed_today:
        logger.info("Today's results are live in Supabase - no manual paste needed.")
    else:
        logger.info("Supabase not configured - results saved locally only (manual paste still works).")

    logger.info("Updating outcomes for past recommendations...")
    update_outcomes(provider)

    # דוחפים גם עדכוני outcome (target_hit/stop_hit/expired) על המלצות ישנות
    all_history = load_all_history()
    all_records = []
    for day in all_history:
        for rec in day["results"]:
            all_records.append(rec)
    push_outcome_updates(all_records)

    logger.info("Done. Results saved under history/ (backup) and pushed to Supabase if configured.")


if __name__ == "__main__":
    main()
