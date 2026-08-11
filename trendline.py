"""
trendline.py
-------------
זיהוי קווי מגמה מקומיים (עולים/יורדים) בגרף תוך-יומי, וזיהוי פריצה שלהם.

שיטה: מוצאים את נקודות ה-swing high / swing low האחרונות בחלון הנתון,
מתאימים קו רגרסיה ליניארי דרכן (trendline), ובודקים אם המחיר הנוכחי
פרץ את הקו.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Optional


@dataclass
class TrendlineResult:
    slope: float
    intercept: float
    direction: str          # "up" or "down"
    line_value_at_last_bar: float
    is_broken: bool
    break_direction: Optional[str]  # "long" (פריצת התנגדות יורדת) / "short" (שבירת תמיכה עולה)


def _find_swing_points(series: pd.Series, order: int = 2, kind: str = "high") -> pd.Series:
    """מוצא נקודות swing high/low מקומיות (פשוט: גבוה/נמוך מ-`order` נרות משני הצדדים)."""
    result = pd.Series(False, index=series.index)
    values = series.values
    for i in range(order, len(values) - order):
        window = values[i - order: i + order + 1]
        if kind == "high" and values[i] == window.max():
            result.iloc[i] = True
        elif kind == "low" and values[i] == window.min():
            result.iloc[i] = True
    return result


def detect_trendline(df: pd.DataFrame, lookback_bars: int = 20, swing_order: int = 2) -> Optional[TrendlineResult]:
    """
    df: OHLCV אינדקסי-זמן, עמודות high/low/close.
    בוחר את הכיוון (עולה/יורד) לפי מגמת ה-close הכללית בחלון, ואז מתאים קו
    לנקודות ה-swing הרלוונטיות (highs לקו התנגדות יורד, lows לקו תמיכה עולה).
    """
    window = df.tail(lookback_bars).copy()
    if len(window) < swing_order * 2 + 3:
        return None

    overall_slope = np.polyfit(range(len(window)), window["close"].values, 1)[0]
    direction = "down" if overall_slope < 0 else "up"

    if direction == "down":
        swings = _find_swing_points(window["high"], order=swing_order, kind="high")
        pts = window.loc[swings, "high"]
    else:
        swings = _find_swing_points(window["low"], order=swing_order, kind="low")
        pts = window.loc[swings, "low"]

    if len(pts) < 2:
        return None

    x = np.array([window.index.get_loc(idx) for idx in pts.index])
    y = pts.values
    slope, intercept = np.polyfit(x, y, 1)

    last_bar_x = len(window) - 1
    line_value = slope * last_bar_x + intercept
    last_close = window["close"].iloc[-1]

    is_broken = False
    break_direction = None
    if direction == "down" and last_close > line_value:
        is_broken = True
        break_direction = "long"       # פריצת קו התנגדות יורד -> סיגנל לונג
    elif direction == "up" and last_close < line_value:
        is_broken = True
        break_direction = "short"      # שבירת קו תמיכה עולה -> סיגנל שורט

    return TrendlineResult(
        slope=slope,
        intercept=intercept,
        direction=direction,
        line_value_at_last_bar=line_value,
        is_broken=is_broken,
        break_direction=break_direction,
    )
