"""
entry_signals.py
------------------
שלב 2+3: הרכבת כל תנאי הכניסה יחד לכדי סיגנל אחד סופי.
כל התנאים חייבים להתקיים (AND לוגי) כדי שתיווצר עסקה.
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
import pandas as pd
import logging

from config import StrategyConfig
from indicators import ema, sma, rsi, macd, macd_histogram_accelerating, get_poc, is_near_poc
from trendline import detect_trendline
from sentiment_filter import MarketSentiment

logger = logging.getLogger("gap_trend_bot.entry")


@dataclass
class EntrySignal:
    symbol: str
    direction: str            # "long" or "short"
    entry_price: float
    reasons: list             # רשימת התנאים שהתקיימו (לוג/דיבוג)
    passed: bool
    fail_reason: Optional[str] = None


def evaluate_entry(
    symbol: str,
    daily_df: pd.DataFrame,
    intraday_df: pd.DataFrame,
    gap_direction: str,
    cfg: StrategyConfig,
    sentiment: MarketSentiment,
) -> EntrySignal:
    """
    daily_df: נתוני יומי (לפחות 60 ימים) - לחישוב EMA/SMA/RSI/MACD/Volume Profile
    intraday_df: נתוני 15m/60m - לזיהוי פריצת קו מגמה
    gap_direction: "up" או "down" מתוצאת סינון היקום
    """
    reasons = []

    # --- כיוון מועמד לפי הגאפ ---
    candidate_direction = "long" if gap_direction == "up" else "short"

    # --- תנאי 1: פריצת קו מגמה תוך-יומי ---
    tl = detect_trendline(intraday_df, lookback_bars=cfg.entry.trendline_lookback_bars)
    if tl is None or not tl.is_broken:
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "no trendline breakout")
    if tl.break_direction != candidate_direction:
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False,
                            f"breakout direction ({tl.break_direction}) mismatches gap direction ({candidate_direction})")
    reasons.append("trendline breakout confirmed")

    # --- תנאי 2: אישור נפח בנר הפריצה ---
    avg_vol = intraday_df["volume"].tail(cfg.entry.breakout_volume_lookback).mean()
    breakout_vol = intraday_df["volume"].iloc[-1]
    if avg_vol == 0 or breakout_vol < avg_vol * cfg.entry.breakout_volume_multiplier:
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "breakout volume too low")
    reasons.append(f"breakout volume {breakout_vol:.0f} >= {cfg.entry.breakout_volume_multiplier}x avg")

    # --- תנאי 3: פילטר ממוצעים נעים (יומי) ---
    close = daily_df["close"]
    ema_fast = ema(close, cfg.entry.ema_fast).iloc[-1]
    ema_med = ema(close, cfg.entry.ema_medium).iloc[-1]
    sma_slow = sma(close, cfg.entry.sma_slow).iloc[-1]
    last_close = close.iloc[-1]

    if candidate_direction == "long":
        if not (last_close > ema_fast > ema_med and last_close > sma_slow):
            # דרישה מקורית: מעל שלושת הממוצעים
            if not (last_close > ema_fast and last_close > ema_med and last_close > sma_slow):
                return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "price not above EMA9/EMA20/SMA50")
    else:
        if not (last_close < ema_fast and last_close < ema_med and last_close < sma_slow):
            return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "price not below EMA9/EMA20/SMA50")
    reasons.append("MA filter passed (EMA9/EMA20/SMA50)")

    # --- תנאי 4: פילטר סנטימנט שוק רחב (רק ללונג) ---
    if candidate_direction == "long" and not sentiment.is_market_healthy_for_longs():
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "broad market below SMA20 - longs blocked")
    reasons.append("market sentiment OK")

    # --- תנאי 5: אזור ערך מוסדי (POC / Volume Profile) ---
    poc = get_poc(daily_df.tail(cfg.volume_profile.lookback_days), num_bins=cfg.volume_profile.num_bins)
    if not is_near_poc(last_close, poc, cfg.volume_profile.poc_proximity_pct):
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False,
                            f"breakout not near POC ({last_close:.2f} vs POC {poc:.2f})")
    reasons.append(f"breakout near POC ({poc:.2f})")

    # --- תנאי 6: מומנטום כפול - RSI + MACD Histogram ---
    rsi_val = rsi(close, cfg.entry.rsi_period).iloc[-1]
    if candidate_direction == "long":
        if not (cfg.entry.rsi_long_min <= rsi_val <= cfg.entry.rsi_long_max):
            return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, f"RSI {rsi_val:.1f} outside long range")
    else:
        if not (cfg.entry.rsi_short_min <= rsi_val <= cfg.entry.rsi_short_max):
            return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, f"RSI {rsi_val:.1f} outside short range")

    macd_df = macd(close, cfg.entry.macd_fast, cfg.entry.macd_slow, cfg.entry.macd_signal)
    accelerating = macd_histogram_accelerating(macd_df["histogram"])
    if candidate_direction == "long" and not accelerating:
        return EntrySignal(symbol, candidate_direction, 0.0, reasons, False, "MACD histogram not accelerating up")
    reasons.append(f"RSI={rsi_val:.1f}, MACD histogram momentum confirmed")

    # --- הכל עבר! ---
    entry_price = float(intraday_df["close"].iloc[-1])
    return EntrySignal(symbol, candidate_direction, entry_price, reasons, True, None)
