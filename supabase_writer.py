"""
supabase_writer.py
--------------------
כותב את תוצאות הסריקה היומית ישירות ל-Supabase, כדי שהאפליקציה תמשוך אותן
לבד - בלי הדבקה ידנית של JSON.

משתמש במפתח ה-Secret של Supabase (לא ה-Publishable/anon key!) כי זו הרצה
שרתית לא-מחוברת (unattended) - המפתח הזה עוקף RLS, ולכן הוא הדרך הנכונה
לכתוב בשם משתמש ספציפי בלי שהוא "מחובר" בפועל. המפתח הזה חייב להישמר
כ-GitHub Actions secret, לעולם לא בקוד או ב-repository בעצמו.

דורש: pip install requests --break-system-packages
משתני סביבה נדרשים (מוגדרים כ-GitHub Actions secrets):
  SUPABASE_URL         - כתובת הפרויקט, למשל https://xxxxx.supabase.co
  SUPABASE_SECRET_KEY   - מפתח ה-Secret (sb_secret_...) מ-Project Settings > API Keys
  SUPABASE_USER_ID       - ה-UUID שלך מ-Authentication > Users בדשבורד של Supabase
"""

from __future__ import annotations
import os
import logging
import requests

logger = logging.getLogger("gap_trend_bot.supabase")


def _get_config():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SECRET_KEY")
    user_id = os.environ.get("SUPABASE_USER_ID")
    if not (url and key and user_id):
        return None
    return {"url": url.rstrip("/"), "key": key, "user_id": user_id}


def push_scan_results(results: list[dict]) -> bool:
    """
    כותב (upsert) את כל תוצאות הסריקה של היום לטבלת daily_scan_results.
    מחזיר True אם הצליח, False אם הדילוג היה מכוון (אין קונפיגורציה) או שגיאה.
    """
    cfg = _get_config()
    if cfg is None:
        logger.info("Supabase env vars not set - skipping cloud push (local JSON history/ still saved).")
        return False

    endpoint = f"{cfg['url']}/rest/v1/daily_scan_results"
    headers = {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    rows = []
    for r in results:
        rows.append({
            "user_id": cfg["user_id"],
            "scan_date": r["scan_date"],
            "symbol": r["symbol"],
            "direction": r["direction"],
            "entry": r.get("entry"),
            "stop": r.get("stop"),
            "target": r.get("target"),
            "shares": r.get("shares"),
            "risk_usd": r.get("risk_usd"),
            "reward_usd": r.get("reward_usd"),
            "suggested_hold_days": r.get("suggested_hold_days"),
            "estimated_success_pct": r.get("estimated_success_pct"),
            "backtest_sample_size": r.get("backtest_sample_size"),
            "outcome": r.get("outcome", "open"),
            "outcome_date": r.get("outcome_date"),
        })

    if not rows:
        logger.info("No scan results today - nothing to push.")
        return True

    try:
        resp = requests.post(endpoint, headers=headers, json=rows, timeout=30)
        if resp.status_code not in (200, 201, 204):
            logger.error(f"Supabase push failed: {resp.status_code} {resp.text}")
            return False
        logger.info(f"Pushed {len(rows)} scan results to Supabase.")
        return True
    except Exception as e:
        logger.exception(f"Supabase push error: {e}")
        return False


def push_outcome_updates(updated_records: list[dict]) -> bool:
    """
    לאחר update_outcomes() המקומי - מעדכן ב-Supabase רק רשומות שהוכרעו
    (outcome != 'open'), לפי המפתח הייחודי (user_id, scan_date, symbol).
    """
    cfg = _get_config()
    if cfg is None:
        return False

    endpoint = f"{cfg['url']}/rest/v1/daily_scan_results"
    headers = {
        "apikey": cfg["key"],
        "Authorization": f"Bearer {cfg['key']}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }

    rows = [r for r in updated_records if r.get("outcome") not in (None, "open")]
    if not rows:
        return True

    payload = [{
        "user_id": cfg["user_id"],
        "scan_date": r["scan_date"],
        "symbol": r["symbol"],
        "direction": r["direction"],
        "outcome": r["outcome"],
        "outcome_date": r.get("outcome_date"),
    } for r in rows]

    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=30)
        if resp.status_code not in (200, 201, 204):
            logger.error(f"Supabase outcome update failed: {resp.status_code} {resp.text}")
            return False
        logger.info(f"Updated {len(payload)} outcomes in Supabase.")
        return True
    except Exception as e:
        logger.exception(f"Supabase outcome update error: {e}")
        return False
