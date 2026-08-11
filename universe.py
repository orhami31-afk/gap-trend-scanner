"""
universe.py
------------
שלב 1: בחירת יקום המניות הראשוני - סינון לפי מחיר, נפח, RVOL וגאפ.
"""

from __future__ import annotations
import pandas as pd
import logging
from config import UniverseConfig

logger = logging.getLogger("gap_trend_bot.universe")


def filter_universe(snapshot: pd.DataFrame, cfg: UniverseConfig) -> pd.DataFrame:
    """
    snapshot: DataFrame עם עמודות symbol, price, volume, avg_volume_30d, rvol, gap_pct
    (כפי שמוחזר מ-DataProvider.get_universe_snapshot)
    מחזיר רק את השורות שעומדות בכל תנאי שלב 1.
    """
    if snapshot.empty:
        return snapshot

    mask = (
        (snapshot["price"] > cfg.min_price)
        & (snapshot["avg_volume_30d"] > cfg.min_avg_daily_volume)
        & (snapshot["rvol"] >= cfg.min_rvol)
        & (snapshot["gap_pct"].abs() >= cfg.min_gap_pct)
        & (snapshot["gap_pct"].abs() <= cfg.max_gap_pct)
    )

    result = snapshot.loc[mask].copy()
    result["gap_direction"] = result["gap_pct"].apply(lambda g: "up" if g > 0 else "down")

    logger.info(f"Universe filter: {len(snapshot)} -> {len(result)} symbols passed stage 1")
    return result.reset_index(drop=True)
