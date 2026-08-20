"""
entry_signals.py
------------------
שלב 2: מודל שערי חובה + ניקוד איכות עבור אסטרטגיית Pullback Continuation.

שערי חובה (כולם חייבים): יקום (מחיר/נפח/RVOL/גאפ) + סנטימנט שוק רחב (ללונג).
ניקוד איכות: 5 תנאים, נדרש min_quality_score (ברירת מחדל 4) כדי לעבור.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import logging

from config import StrategyConfig
from indicators import ema, sma, rsi, macd, get_poc
from sentiment_filter import MarketSentiment

logger = logging.getLogger("gap_trend_bot.entry")


@dataclass
class QualityCheck:
    label: str
    passed: bool


@dataclass
class EntrySignal:
    symbol: str
    direction: str
    entry_price: float
    gates_passed: bool
    quality_checks: list
    quality_score: int
    passed: bool
    fail_reason: Optional[str] = None


def _rolling_vwap(df: pd.DataFrame, window: int) -> pd.Series:
    """קירוב VWAP מגליל - אין לנו נתוני תוך-יומי, אז זה ממוצע משוקלל-נפח נגלל
    על נתוני יומי, לא VWAP תוך-יומי אמיתי. מספיק כאינדיקציה יחסית."""
    typical = (df["high"] + df["low"] + df["close"]) / 3
    pv = typical * df["volume"]
    return pv.rolling(window).sum() / df["volume"].rolling(window).sum()


def evaluate_entry(
    symbol: str,
    daily_df: pd.DataFrame,
    gap_direction: str,
    cfg: StrategyConfig,
    sentiment: MarketSentiment,
) -> EntrySignal:
    """
    daily_df: לפחות ~90 ימי מסחר של נתוני יומי (open/high/low/close/volume).
    gap_direction: "long" או "short", מגיע מתוצאת סינון היקום (universe.py).
    """
    direction = gap_direction
    close = daily_df["close"]
    last_close = float(close.iloc[-1])

    # --- שערי חובה ---
    gates_passed = True
    gate_fail = None
    if direction == "long" and not sentiment.is_market_healthy_for_longs():
        gates_passed = False
        gate_fail = "broad market sentiment gate failed (SPY/QQQ below SMA20)"

    if not gates_passed:
        return EntrySignal(symbol, direction, last_close, False, [], 0, False, gate_fail)

    # --- ניקוד איכות ---
    ema20 = ema(close, cfg.quality.ema_pullback)
    poc = get_poc(daily_df.tail(cfg.quality.poc_lookback_days), num_bins=cfg.quality.poc_num_bins)
    vwap = _rolling_vwap(daily_df, cfg.quality.vwap_lookback_days)
    rsi_series = rsi(close, cfg.quality.rsi_period)
    macd_df = macd(close, cfg.quality.macd_fast, cfg.quality.macd_slow, cfg.quality.macd_signal)
    hist = macd_df["histogram"]
    sma_trend = sma(close, cfg.quality.daily_trend_sma)
    avg_vol = daily_df["volume"].tail(cfg.quality.vwap_volume_confirm_days).mean()
    last_vol = daily_df["volume"].iloc[-1]

    pullback_ok = (
        (ema20.iloc[-1] and abs(last_close - ema20.iloc[-1]) / ema20.iloc[-1] <= cfg.quality.pullback_tolerance_pct / 100)
        or (poc and abs(last_close - poc) / poc <= cfg.quality.pullback_tolerance_pct / 100)
    )

    if direction == "long":
        vwap_ok = bool(vwap.iloc[-1]) and last_close > vwap.iloc[-1] and last_vol > avg_vol
        rsi_ok = cfg.quality.rsi_long_min <= rsi_series.iloc[-1] <= cfg.quality.rsi_long_max and rsi_series.iloc[-1] > rsi_series.iloc[-2]
        macd_flip_ok = hist.iloc[-1] > hist.iloc[-2] and hist.iloc[-2] <= hist.iloc[-3]
        trend_ok = sma_trend.iloc[-1] is not None and sma_trend.iloc[-6] is not None and \
            last_close > sma_trend.iloc[-1] and sma_trend.iloc[-1] > sma_trend.iloc[-6]
    else:
        vwap_ok = bool(vwap.iloc[-1]) and last_close < vwap.iloc[-1] and last_vol > avg_vol
        rsi_ok = cfg.quality.rsi_short_min <= rsi_series.iloc[-1] <= cfg.quality.rsi_short_max and rsi_series.iloc[-1] < rsi_series.iloc[-2]
        macd_flip_ok = hist.iloc[-1] < hist.iloc[-2] and hist.iloc[-2] >= hist.iloc[-3]
        trend_ok = sma_trend.iloc[-1] is not None and sma_trend.iloc[-6] is not None and \
            last_close < sma_trend.iloc[-1] and sma_trend.iloc[-1] < sma_trend.iloc[-6]

    quality_checks = [
        QualityCheck("נסיגה רגועה ל-EMA20/POC", bool(pullback_ok)),
        QualityCheck("חציית VWAP באישור נפח (קירוב מנתוני יומי)", bool(vwap_ok)),
        QualityCheck(f"RSI {'40-50 מתאושש' if direction=='long' else '50-60 יורד'}", bool(rsi_ok)),
        QualityCheck("MACD היסטוגרמה מתהפכת", bool(macd_flip_ok)),
        QualityCheck("מגמה יומית חיובית (מעל SMA50 עולה)", bool(trend_ok)),
    ]
    quality_score = sum(1 for q in quality_checks if q.passed)
    passed = quality_score >= cfg.quality.min_quality_score

    fail_reason = None if passed else f"quality score {quality_score}/{cfg.quality.quality_pool_size} below required {cfg.quality.min_quality_score}"

    return EntrySignal(symbol, direction, last_close, True, quality_checks, quality_score, passed, fail_reason)
