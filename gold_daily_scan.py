"""
gold_daily_scan.py
--------------------
בדיקה אוטומטית יומית של הזדמנות "Smart Opening Range Breakout" לזהב (XAUUSD),
כולל תנאי Liquidity Sweep חדש. רץ פעם ביום (ראה gold_scan.yml), אחרי סגירת
חלון המסחר (16:30-17:30 שעון ישראל), וכותב את התוצאה ישירות ל-Supabase -
האפליקציה מציגה אותה לבד, בלי צורך בלחיצה.

גם מעדכן תוצאות (הצליח/נכשל) של המלצות ישנות שעדיין 'open', ע"י בדיקה אם
המחיר הגיע ליעד או לסטופ באחד הימים שאחרי - כך נצבר נתון אמיתי לאורך זמן,
לא רק "המלצה של היום".

עצמאי לגמרי - לא תלוי בתשתית MT5/yfinance של הבוט הסטוקים, כי אלה דורשים
נתוני תוך-יומי שרק Twelve Data נותן לנו בחינם דרך REST רגיל.

דורש: pip install requests pandas pytz --break-system-packages
משתני סביבה: TWELVE_DATA_KEY, SUPABASE_URL, SUPABASE_SECRET_KEY, SUPABASE_USER_ID
"""

from __future__ import annotations
import os
import logging
import requests
import pandas as pd
from datetime import datetime, date, timedelta
import pytz
from notifier import send_push_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)-18s | %(levelname)-7s | %(message)s")
logger = logging.getLogger("gold_scan")

IL_TZ = pytz.timezone("Asia/Jerusalem")
SYMBOL = "XAU/USD"

# ---- strategy config (mirrors the app's live check + adds the liquidity sweep) ----
CFG = {
    "session_start": (16, 30), "or_end": (16, 45), "session_end": (17, 30),
    "volume_multiplier": 2.0, "volume_lookback": 20,
    "ema_fast": 9, "ema_slow": 21,
    "max_spread_usd": 0.60,  # not verifiable from free daily/intraday close data - flagged unverified
    "min_body_ratio": 0.60,
    "sweep_tolerance_usd": 0.10,   # wick must pierce by at least this much to count as a sweep
    "sweep_lookback_minutes": 15,   # how far back (from the breakout bar) to look for a sweep
    "risk_reward_ratio": 2.0,
    "max_loss_usd": 75.0,
    "atr_period": 14,
    "atr_stop_multiple": 1.5,  # stop = entry -/+ atr_stop_multiple * ATR (replaces the old OR-boundary stop)
    "contract_size": 100,  # oz/lot - verify against your own broker before live use
    "max_hold_days_for_outcome": 5,
    "min_quality_score": 4,   # mandatory gate = OR breakout; 6 quality checks below, need this many
    "quality_pool_size": 6,
}


def get_env(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return val


def fetch_intraday_bars(api_key: str, outputsize: int = 300) -> pd.DataFrame:
    url = (f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1min"
           f"&outputsize={outputsize}&timezone=Asia/Jerusalem&apikey={api_key}")
    r = requests.get(url, timeout=30)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(data.get("message", "Twelve Data error fetching intraday bars"))
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    df["volume"] = df["volume"].astype(float) if "volume" in df.columns else 0.0
    return df


def fetch_daily_bars(api_key: str, outputsize: int = 30) -> pd.DataFrame:
    url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1day&outputsize={outputsize}&apikey={api_key}"
    r = requests.get(url, timeout=30)
    data = r.json()
    if data.get("status") == "error" or "values" not in data:
        raise RuntimeError(data.get("message", "Twelve Data error fetching daily bars"))
    df = pd.DataFrame(data["values"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.set_index("datetime").sort_index()
    for c in ["open", "high", "low", "close"]:
        df[c] = df[c].astype(float)
    return df


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def atr(df: pd.DataFrame, period: int) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(span=period, adjust=False).mean()


def compute_opening_range(df: pd.DataFrame, today: date):
    # df.index is already naive local Israel time (Twelve Data returns it pre-converted
    # via the timezone=Asia/Jerusalem query param) - do NOT localize again here.
    start = datetime.combine(today, datetime.min.time().replace(hour=CFG["session_start"][0], minute=CFG["session_start"][1]))
    end = datetime.combine(today, datetime.min.time().replace(hour=CFG["or_end"][0], minute=CFG["or_end"][1]))
    window = df[(df.index >= start) & (df.index < end)]
    if window.empty:
        return None
    return {"high": float(window["high"].max()), "low": float(window["low"].min()), "start": start, "end": end}


def session_vwap(df: pd.DataFrame, session_start: datetime) -> pd.Series:
    session = df[df.index >= session_start]
    tp = (session["high"] + session["low"] + session["close"]) / 3
    return (tp * session["volume"]).cumsum() / session["volume"].cumsum().replace(0, pd.NA)


def check_liquidity_sweep(df: pd.DataFrame, opening_range: dict, direction: str, breakout_time) -> bool:
    """
    בדיקה מדויקת ומדידה של 'Liquidity Sweep': בטווח הדקות שלפני נר הפריצה,
    האם המחיר חדר קצרות מעבר לצד ההפוך של טווח הפתיחה (מלכודת לסוחרים
    שנכנסו לכיוון הלא נכון) ואז נסגר חזרה בתוך הטווח - לפני התנועה האמיתית.
    long: sweep = low < opening_range.low - tolerance, אך close > opening_range.low
    short: sweep = high > opening_range.high + tolerance, אך close < opening_range.high
    """
    lookback_start = breakout_time - timedelta(minutes=CFG["sweep_lookback_minutes"])
    window = df[(df.index >= lookback_start) & (df.index < breakout_time)]
    if window.empty:
        return False
    tol = CFG["sweep_tolerance_usd"]
    if direction == "long":
        swept = window[(window["low"] < opening_range["low"] - tol) & (window["close"] > opening_range["low"])]
    else:
        swept = window[(window["high"] > opening_range["high"] + tol) & (window["close"] < opening_range["high"])]
    return not swept.empty


def evaluate_gold_setup(intraday_df: pd.DataFrame, daily_df: pd.DataFrame, today: date) -> dict:
    opening_range = compute_opening_range(intraday_df, today)
    if opening_range is None:
        return {"passed": False, "fail_reason": "no M1 data in the opening-range window today"}

    last = intraday_df.iloc[-1]
    last_close = float(last["close"])
    broke_up = last_close > opening_range["high"]
    broke_down = last_close < opening_range["low"]
    if not (broke_up or broke_down):
        return {"passed": False, "fail_reason": "no opening-range breakout yet by end of window",
                "opening_range": opening_range, "last_price": last_close}
    direction = "long" if broke_up else "short"

    closes = intraday_df["close"]
    avg_vol = intraday_df["volume"].tail(CFG["volume_lookback"]).mean()
    checklist = []

    vol_ok = bool(avg_vol and last["volume"] >= avg_vol * CFG["volume_multiplier"])
    checklist.append({"label": "פריצה בנפח גבוה (2x+ מהממוצע)", "ok": vol_ok})

    body_range = last["high"] - last["low"]
    body_ratio = abs(last["close"] - last["open"]) / body_range if body_range > 0 else 0
    body_ok = body_ratio >= CFG["min_body_ratio"]
    checklist.append({"label": "גוף נר מומנטום (60%+)", "ok": bool(body_ok)})

    vwap_series = session_vwap(intraday_df[intraday_df.index >= opening_range["start"]], opening_range["start"])
    current_vwap = float(vwap_series.iloc[-1]) if not vwap_series.empty else None
    vwap_ok = current_vwap is not None and ((last_close > current_vwap) if direction == "long" else (last_close < current_vwap))
    checklist.append({"label": "מעל/מתחת VWAP", "ok": bool(vwap_ok)})

    ema_fast = ema(closes, CFG["ema_fast"]).iloc[-1]
    ema_slow = ema(closes, CFG["ema_slow"]).iloc[-1]
    ema_ok = (ema_fast > ema_slow) if direction == "long" else (ema_fast < ema_slow)
    checklist.append({"label": "EMA9/EMA21 Ribbon", "ok": bool(ema_ok)})

    h1_closes = daily_df["close"] if len(daily_df) >= 2 else None
    h1_trend_ok = True
    if h1_closes is not None and len(h1_closes) >= 5:
        trend = "up" if h1_closes.iloc[-1] > h1_closes.iloc[-5] else "down"
        h1_trend_ok = not ((direction == "long" and trend == "down") or (direction == "short" and trend == "up"))
    checklist.append({"label": "מגמה לא מתנגשת", "ok": bool(h1_trend_ok)})

    sweep_ok = check_liquidity_sweep(intraday_df, opening_range, direction, last.name)
    checklist.append({"label": "Liquidity Sweep לפני הפריצה", "ok": bool(sweep_ok)})

    quality_score = sum(1 for c in checklist if c["ok"])
    all_passed = quality_score >= CFG["min_quality_score"]

    # ATR-based stop (replaces the old OR-boundary/min-distance stop) - adapts cleanly to actual
    # volatility instead of being arbitrarily tight or wide depending on how big the OR happened to be.
    atr_val = float(atr(intraday_df, CFG["atr_period"]).iloc[-1])
    stop = last_close - CFG["atr_stop_multiple"] * atr_val if direction == "long" \
        else last_close + CFG["atr_stop_multiple"] * atr_val

    risk_per_unit = abs(last_close - stop)
    lot_size = round(CFG["max_loss_usd"] / (risk_per_unit * CFG["contract_size"]), 2) if risk_per_unit > 0 else None
    lot_size = max(lot_size, 0.01) if lot_size else None
    reward_per_unit = risk_per_unit * CFG["risk_reward_ratio"]
    target = last_close + reward_per_unit if direction == "long" else last_close - reward_per_unit

    return {
        "passed": all_passed, "direction": direction, "entry": round(last_close, 2),
        "stop": round(stop, 2), "target": round(target, 2), "lot_size": lot_size,
        "checklist": checklist, "opening_range": opening_range, "quality_score": quality_score,
        "fail_reason": None if all_passed else f"quality score {quality_score}/{CFG['quality_pool_size']} below required {CFG['min_quality_score']}",
    }


def push_result_to_supabase(result: dict, scan_date: date, url: str, key: str, user_id: str):
    endpoint = f"{url.rstrip('/')}/rest/v1/gold_daily_results"
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json", "Prefer": "resolution=merge-duplicates"}
    row = {
        "user_id": user_id, "scan_date": str(scan_date), "passed": result["passed"],
        "direction": result.get("direction"), "entry": result.get("entry"), "stop": result.get("stop"),
        "target": result.get("target"), "lot_size": result.get("lot_size"),
        "checklist": result.get("checklist"), "fail_reason": result.get("fail_reason"),
        "outcome": "open" if result["passed"] else "no_setup",
    }
    resp = requests.post(endpoint, headers=headers, json=[row], timeout=30)
    if resp.status_code not in (200, 201, 204):
        raise RuntimeError(f"Supabase push failed: {resp.status_code} {resp.text}")
    logger.info("Pushed today's gold result to Supabase.")


def update_open_outcomes(api_key: str, url: str, key: str, user_id: str):
    """בודק המלצות פתוחות מהימים האחרונים ומעדכן אם הגיעו ליעד/לסטופ."""
    headers = {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    cutoff = str(date.today() - timedelta(days=CFG["max_hold_days_for_outcome"] + 2))
    query_url = (f"{url.rstrip('/')}/rest/v1/gold_daily_results"
                 f"?user_id=eq.{user_id}&outcome=eq.open&scan_date=gte.{cutoff}&select=*")
    resp = requests.get(query_url, headers=headers, timeout=30)
    if resp.status_code != 200:
        logger.error(f"Failed to fetch open gold results: {resp.status_code} {resp.text}")
        return
    open_rows = resp.json()
    if not open_rows:
        logger.info("No open gold recommendations to update.")
        return

    daily_df = fetch_daily_bars(api_key, outputsize=CFG["max_hold_days_for_outcome"] + 5)

    for row in open_rows:
        scan_date = pd.to_datetime(row["scan_date"]).date()
        subsequent = daily_df[daily_df.index.date > scan_date]
        if subsequent.empty:
            continue
        direction = row["direction"]
        entry, stop, target = row["entry"], row["stop"], row["target"]
        outcome, outcome_price, outcome_date = None, None, None
        for ts, bar in subsequent.iterrows():
            hit_target = bar["high"] >= target if direction == "long" else bar["low"] <= target
            hit_stop = bar["low"] <= stop if direction == "long" else bar["high"] >= stop
            if hit_target and hit_stop:
                outcome, outcome_price, outcome_date = "stop_hit", stop, ts.date()  # שמרני
                break
            if hit_target:
                outcome, outcome_price, outcome_date = "target_hit", target, ts.date()
                break
            if hit_stop:
                outcome, outcome_price, outcome_date = "stop_hit", stop, ts.date()
                break
        if outcome is None and (date.today() - scan_date).days > CFG["max_hold_days_for_outcome"]:
            outcome, outcome_price, outcome_date = "expired", None, date.today()
        if outcome:
            patch_url = f"{url.rstrip('/')}/rest/v1/gold_daily_results?id=eq.{row['id']}"
            patch = {"outcome": outcome, "outcome_price": outcome_price, "outcome_date": str(outcome_date) if outcome_date else None}
            p = requests.patch(patch_url, headers=headers, json=patch, timeout=30)
            if p.status_code not in (200, 204):
                logger.error(f"Failed to update outcome for row {row['id']}: {p.status_code} {p.text}")
            else:
                logger.info(f"Updated outcome for {scan_date}: {outcome}")


def main():
    api_key = get_env("TWELVE_DATA_KEY")
    sb_url = get_env("SUPABASE_URL")
    sb_key = get_env("SUPABASE_SECRET_KEY")
    sb_user = get_env("SUPABASE_USER_ID")

    today = datetime.now(IL_TZ).date()
    logger.info(f"Running gold ORB daily scan for {today}...")

    intraday_df = fetch_intraday_bars(api_key)
    daily_df = fetch_daily_bars(api_key)

    result = evaluate_gold_setup(intraday_df, daily_df, today)
    logger.info(f"Result: passed={result['passed']} reason={result.get('fail_reason')}")

    push_result_to_supabase(result, today, sb_url, sb_key, sb_user)

    if result["passed"]:
        send_push_notification(
            title=f"🥇 הזדמנות זהב {result['direction'].upper()}",
            message=f"כניסה: ${result['entry']:.2f} · סטופ: ${result['stop']:.2f} · יעד: ${result['target']:.2f} · Lot: {result.get('lot_size','—')}",
            priority="urgent", tags="rotating_light",
        )

    logger.info("Updating outcomes for past open recommendations...")
    update_open_outcomes(api_key, sb_url, sb_key, sb_user)

    logger.info("Done.")


if __name__ == "__main__":
    main()
