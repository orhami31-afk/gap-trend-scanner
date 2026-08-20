"""
backtest.py
------------
מעריך "אחוז הצלחה משוער" לכל מניה - על סמך בדיקה היסטורית אמיתית של כמה
פעמים בעבר הופיע setup דומה (לפי מודל שערי חובה + ניקוד איכות של
entry_signals.py) על אותה מניה, ומה קרה אחריו.

הערה חשובה: זהו אחוז מבוסס-היסטוריה על אותה מניה בלבד (לא הבטחה, לא
ייעוץ השקעות). ככל שיש פחות "הישנויות" של ה-setup בעבר, כך האומדן פחות
מהימן סטטיסטית - המערכת גם מחזירה sample_size כדי שתדע כמה לסמוך על המספר.
לעולם אין כאן מספר קבוע-מראש (כמו "70%") - הכל מחושב בפועל.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Optional

from indicators import ema, sma, rsi, macd, get_poc
from config import StrategyConfig


@dataclass
class BacktestResult:
    win_rate_pct: Optional[float]
    sample_size: int
    avg_days_to_outcome: Optional[float]


def _rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def _simulate_forward(df: pd.DataFrame, entry_idx: int, direction: str,
                       entry: float, stop: float, target: float, max_hold_days: int) -> Optional[tuple]:
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
            return (False, days_elapsed)  # שני התנאים באותו נר - שמרני, מניחים סטופ קודם
        if hit_target:
            return (True, days_elapsed)
        if hit_stop:
            return (False, days_elapsed)
    return None


def backtest_symbol(
    daily_df: pd.DataFrame,
    direction: str,
    cfg: StrategyConfig,
    risk_reward_ratio: float = 2.0,
    max_hold_days: int = 10,
) -> BacktestResult:
    """
    daily_df: לפחות ~300 ימי מסחר של נתוני יומי.
    direction: "long" או "short".
    """
    if len(daily_df) < 90:
        return BacktestResult(None, 0, None)

    close = daily_df["close"]
    ema20 = ema(close, cfg.quality.ema_pullback)
    sma_trend = sma(close, cfg.quality.daily_trend_sma)
    rsi_series = rsi(close, cfg.quality.rsi_period)
    macd_df = macd(close, cfg.quality.macd_fast, cfg.quality.macd_slow, cfg.quality.macd_signal)
    hist = macd_df["histogram"]
    vwap = _rolling_vwap(daily_df, cfg.quality.vwap_lookback_days)
    avg_vol20 = daily_df["volume"].rolling(cfg.quality.vwap_volume_confirm_days).mean()

    outcomes = []
    days_list = []
    start = cfg.quality.daily_trend_sma + cfg.quality.daily_trend_slope_lookback + 5
    end = len(daily_df) - 1

    for i in range(start, end):
        gap_pct = (daily_df["open"].iloc[i] - close.iloc[i - 1]) / close.iloc[i - 1] * 100
        gap_dir = "long" if gap_pct > 0 else "short"
        if gap_dir != direction:
            continue
        if not (cfg.universe.min_gap_pct <= abs(gap_pct) <= cfg.universe.max_gap_pct):
            continue

        if pd.isna(avg_vol20.iloc[i]) or daily_df["volume"].iloc[i] < avg_vol20.iloc[i] * cfg.universe.min_rvol:
            continue

        price = close.iloc[i]
        poc = get_poc(daily_df.iloc[max(0, i - cfg.quality.poc_lookback_days):i + 1], num_bins=cfg.quality.poc_num_bins)

        pullback_ok = (
            (ema20.iloc[i] and abs(price - ema20.iloc[i]) / ema20.iloc[i] <= cfg.quality.pullback_tolerance_pct / 100)
            or (poc and not pd.isna(poc) and abs(price - poc) / poc <= cfg.quality.pullback_tolerance_pct / 100)
        )

        if direction == "long":
            vwap_ok = not pd.isna(vwap.iloc[i]) and price > vwap.iloc[i] and daily_df["volume"].iloc[i] > avg_vol20.iloc[i]
            rsi_ok = cfg.quality.rsi_long_min <= rsi_series.iloc[i] <= cfg.quality.rsi_long_max and rsi_series.iloc[i] > rsi_series.iloc[i - 1]
            macd_flip_ok = hist.iloc[i] > hist.iloc[i - 1] and hist.iloc[i - 1] <= hist.iloc[i - 2]
            trend_ok = not pd.isna(sma_trend.iloc[i]) and not pd.isna(sma_trend.iloc[i - cfg.quality.daily_trend_slope_lookback]) and \
                price > sma_trend.iloc[i] and sma_trend.iloc[i] > sma_trend.iloc[i - cfg.quality.daily_trend_slope_lookback]
        else:
            vwap_ok = not pd.isna(vwap.iloc[i]) and price < vwap.iloc[i] and daily_df["volume"].iloc[i] > avg_vol20.iloc[i]
            rsi_ok = cfg.quality.rsi_short_min <= rsi_series.iloc[i] <= cfg.quality.rsi_short_max and rsi_series.iloc[i] < rsi_series.iloc[i - 1]
            macd_flip_ok = hist.iloc[i] < hist.iloc[i - 1] and hist.iloc[i - 1] >= hist.iloc[i - 2]
            trend_ok = not pd.isna(sma_trend.iloc[i]) and not pd.isna(sma_trend.iloc[i - cfg.quality.daily_trend_slope_lookback]) and \
                price < sma_trend.iloc[i] and sma_trend.iloc[i] < sma_trend.iloc[i - cfg.quality.daily_trend_slope_lookback]

        quality_score = sum([bool(pullback_ok), bool(vwap_ok), bool(rsi_ok), bool(macd_flip_ok), bool(trend_ok)])
        if quality_score < cfg.quality.min_quality_score:
            continue

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
