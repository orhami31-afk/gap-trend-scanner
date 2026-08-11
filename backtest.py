"""
backtest.py
------------
מעריך "אחוז הצלחה משוער" לכל מניה/סיגנל - על סמך בדיקה היסטורית (Backtest)
של כמה פעמים בעבר הופיע setup דומה על אותה מניה, ומה קרה אחריו (הגיע ליעד
לפני שהגיע לסטופ, או ההפך).

הערה חשובה למי שקורא את הפלט: זהו אחוז מבוסס-היסטוריה על אותה מניה
בלבד (לא הבטחה, לא ייעוץ השקעות). ככל שיש פחות "הישנויות" של ה-setup
בעבר, כך האומדן פחות מהימן סטטיסטית - המערכת גם מחזירה כמה פעמים
ה-setup קרה (sample_size) כדי שתדע כמה לסמוך על המספר.

מגבלה טכנית: הבדיקה ההיסטורית משתמשת בנתוני יומי בלבד (לא תוך-יומי),
ולכן מדמה את תנאי הכניסה בקירוב (גאפ + פילטר ממוצעים + RSI + MACD),
בלי שחזור מלא של פריצת קו המגמה התוך-יומית.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

from indicators import ema, sma, rsi, macd, macd_histogram_accelerating
from config import StrategyConfig


@dataclass
class BacktestResult:
    win_rate_pct: Optional[float]
    sample_size: int
    avg_days_to_outcome: Optional[float]


def _simulate_forward(df: pd.DataFrame, entry_idx: int, direction: str,
                       entry: float, stop: float, target: float, max_hold_days: int) -> Optional[tuple]:
    """מדמה קדימה מ-entry_idx: בודק אם high/low נוגעים ביעד או בסטופ קודם. מחזיר (won: bool, days) או None אם לא הוכרע בטווח."""
    end_idx = min(entry_idx + max_hold_days, len(df) - 1)
    for i in range(entry_idx + 1, end_idx + 1):
        bar = df.iloc[i]
        days_elapsed = i - entry_idx
        if direction == "long":
            hit_target = bar["high"] >= target
            hit_stop = bar["low"] <= stop
        else:
            hit_target = bar["low"] <= target
            hit_stop = bar["high"] >= stop
        if hit_target and hit_stop:
            # שני התנאים באותו נר - שמרני: מניחים שהסטופ נפגע קודם (תרחיש גרוע)
            return (False, days_elapsed)
        if hit_target:
            return (True, days_elapsed)
        if hit_stop:
            return (False, days_elapsed)
    return None  # לא הוכרע בטווח הזמן - מדלגים על הדוגמה הזו


def backtest_symbol(
    daily_df: pd.DataFrame,
    direction: str,
    cfg: StrategyConfig,
    risk_reward_ratio: float = 2.0,
    max_hold_days: int = 10,
) -> BacktestResult:
    """
    daily_df: לפחות ~300 ימי מסחר של נתוני יומי (open/high/low/close/volume).
    direction: "long" או "short" - הכיוון שבודקים לו setups דומים בעבר.
    """
    if len(daily_df) < 80:
        return BacktestResult(None, 0, None)

    close = daily_df["close"]
    ema_fast = ema(close, cfg.entry.ema_fast)
    ema_med = ema(close, cfg.entry.ema_medium)
    sma_slow = sma(close, cfg.entry.sma_slow)
    rsi_series = rsi(close, cfg.entry.rsi_period)
    macd_df = macd(close, cfg.entry.macd_fast, cfg.entry.macd_slow, cfg.entry.macd_signal)

    outcomes = []
    days_list = []

    # מתחילים אחרי שיש מספיק היסטוריה לכל האינדיקטורים (SMA50 + buffer)
    start = cfg.entry.sma_slow + 5
    end = len(daily_df) - 1  # צריך "עתיד" לבדוק תוצאה

    for i in range(start, end):
        gap_pct = (daily_df["open"].iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1] * 100
        gap_dir = "long" if gap_pct > 0 else "short"
        if gap_dir != direction:
            continue
        if not (cfg.universe.min_gap_pct <= abs(gap_pct) <= cfg.universe.max_gap_pct):
            continue

        price = close.iloc[i]
        if direction == "long":
            ma_ok = price > ema_fast.iloc[i] and price > ema_med.iloc[i] and price > sma_slow.iloc[i]
            rsi_ok = cfg.entry.rsi_long_min <= rsi_series.iloc[i] <= cfg.entry.rsi_long_max
        else:
            ma_ok = price < ema_fast.iloc[i] and price < ema_med.iloc[i] and price < sma_slow.iloc[i]
            rsi_ok = cfg.entry.rsi_short_min <= rsi_series.iloc[i] <= cfg.entry.rsi_short_max

        if not (ma_ok and rsi_ok):
            continue

        hist_window = macd_df["histogram"].iloc[max(0, i - 3): i + 1]
        if not macd_histogram_accelerating(hist_window, lookback=min(3, len(hist_window) - 1)):
            continue

        # setup "עבר" את הקירוב ההיסטורי -> נדמה עסקה
        entry_price = price
        recent_low = daily_df["low"].iloc[max(0, i - 10): i + 1].min()
        recent_high = daily_df["high"].iloc[max(0, i - 10): i + 1].max()
        stop = recent_low if direction == "long" else recent_high
        risk_per_share = (entry_price - stop) if direction == "long" else (stop - entry_price)
        if risk_per_share <= 0:
            continue
        target = entry_price + risk_per_share * risk_reward_ratio if direction == "long" \
            else entry_price - risk_per_share * risk_reward_ratio

        result = _simulate_forward(daily_df, i, direction, entry_price, stop, target, max_hold_days)
        if result is None:
            continue
        won, days = result
        outcomes.append(won)
        days_list.append(days)

    if not outcomes:
        return BacktestResult(None, 0, None)

    win_rate = round(100 * sum(outcomes) / len(outcomes), 1)
    avg_days = round(float(np.mean(days_list)), 1)
    return BacktestResult(win_rate, len(outcomes), avg_days)
