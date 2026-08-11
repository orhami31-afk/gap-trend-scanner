"""
indicators.py
--------------
חישובי אינדיקטורים טכניים: EMA, SMA, RSI, MACD, ו-Volume Profile / POC.
מחושב עם pandas/numpy בלבד - ללא תלות בספריות טכניות חיצוניות.
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))
    return rsi_val.fillna(50)


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    histogram = macd_line - signal_line
    return pd.DataFrame({
        "macd": macd_line,
        "signal": signal_line,
        "histogram": histogram,
    })


def macd_histogram_accelerating(hist: pd.Series, lookback: int = 3) -> bool:
    """בודק שההיסטוגרמה של ה-MACD עולה בהאצה (כל ערך גבוה מקודמו) ב-lookback הנרות האחרונים."""
    if len(hist) < lookback + 1:
        return False
    recent = hist.tail(lookback + 1).values
    return all(recent[i] < recent[i + 1] for i in range(len(recent) - 1))


def volume_profile(df: pd.DataFrame, num_bins: int = 50) -> pd.DataFrame:
    """
    בונה Volume Profile פשוט: מחלק את טווח המחירים ל-bins ומצטבר נפח בכל bin.
    df חייב לכלול עמודות high, low, close, volume.
    מחזיר DataFrame עם price_level ו-volume, ממוין מה-POC (הכי גבוה) ומטה.
    """
    price_min = df["low"].min()
    price_max = df["high"].max()
    bins = np.linspace(price_min, price_max, num_bins + 1)
    bin_volumes = np.zeros(num_bins)

    for _, row in df.iterrows():
        # מחלקים את הנפח של הנר על פני הבינים שהוא חצה (high-low)
        low, high, vol = row["low"], row["high"], row["volume"]
        if high == low:
            idx = np.searchsorted(bins, low) - 1
            idx = min(max(idx, 0), num_bins - 1)
            bin_volumes[idx] += vol
            continue
        touched = np.where((bins[:-1] < high) & (bins[1:] > low))[0]
        if len(touched) == 0:
            continue
        vol_per_bin = vol / len(touched)
        bin_volumes[touched] += vol_per_bin

    centers = (bins[:-1] + bins[1:]) / 2
    profile = pd.DataFrame({"price_level": centers, "volume": bin_volumes})
    return profile.sort_values("volume", ascending=False).reset_index(drop=True)


def get_poc(df: pd.DataFrame, num_bins: int = 50) -> float:
    """Point of Control - רמת המחיר עם הנפח המצטבר הגבוה ביותר."""
    profile = volume_profile(df, num_bins)
    if profile.empty:
        return float("nan")
    return float(profile.iloc[0]["price_level"])


def is_near_poc(price: float, poc: float, proximity_pct: float = 1.0) -> bool:
    if poc == 0 or np.isnan(poc):
        return False
    return abs(price - poc) / poc * 100 <= proximity_pct
