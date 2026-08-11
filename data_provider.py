"""
data_provider.py
-----------------
שכבת גישה לנתוני שוק. מבודד את שאר המערכת ממקור הנתונים הספציפי,
כך שאפשר להחליף ספק (yfinance / Alpaca / Polygon וכו') בלי לגעת בלוגיקה.

ברירת המחדל משתמשת ב-yfinance (חינמי, מספיק לפיתוח ובדיקה).
לשימוש production מומלץ ספק בתשלום עם נתוני intraday איכותיים יותר.
"""

from __future__ import annotations
import pandas as pd
from typing import Optional
import logging

logger = logging.getLogger("gap_trend_bot.data")


class DataProvider:
    """Interface מופשט - כל ספק נתונים חדש צריך לממש את המתודות האלה."""

    def get_daily_bars(self, symbol: str, lookback_days: int) -> pd.DataFrame:
        raise NotImplementedError

    def get_intraday_bars(self, symbol: str, interval: str, lookback_days: int) -> pd.DataFrame:
        raise NotImplementedError

    def get_universe_snapshot(self, symbols: list[str]) -> pd.DataFrame:
        """מחזיר snapshot של מחיר נוכחי, מחיר פתיחה, נפח וכו' לכל הרשימה."""
        raise NotImplementedError


class YFinanceProvider(DataProvider):
    """מימוש מבוסס yfinance. דורש: pip install yfinance"""

    def __init__(self):
        try:
            import yfinance as yf
            self._yf = yf
        except ImportError as e:
            raise ImportError(
                "yfinance is not installed. Run: pip install yfinance --break-system-packages"
            ) from e

    def get_daily_bars(self, symbol: str, lookback_days: int = 90) -> pd.DataFrame:
        df = self._yf.Ticker(symbol).history(period=f"{lookback_days}d", interval="1d")
        df = df.rename(columns=str.lower)
        df.index.name = "date"
        return df

    def get_intraday_bars(self, symbol: str, interval: str = "15m", lookback_days: int = 5) -> pd.DataFrame:
        # yfinance מגביל טווח היסטוריה ל-intraday (בד"כ עד 60 יום ל-15m)
        df = self._yf.Ticker(symbol).history(period=f"{lookback_days}d", interval=interval)
        df = df.rename(columns=str.lower)
        df.index.name = "datetime"
        return df

    def get_universe_snapshot(self, symbols: list[str]) -> pd.DataFrame:
        rows = []
        for sym in symbols:
            try:
                daily = self.get_daily_bars(sym, lookback_days=35)
                if daily.empty or len(daily) < 2:
                    continue
                today = daily.iloc[-1]
                prev = daily.iloc[-2]
                avg_vol_30d = daily["volume"].tail(30).mean()
                gap_pct = (today["open"] - prev["close"]) / prev["close"] * 100
                rows.append({
                    "symbol": sym,
                    "price": today["close"],
                    "open": today["open"],
                    "prev_close": prev["close"],
                    "volume": today["volume"],
                    "avg_volume_30d": avg_vol_30d,
                    "rvol": today["volume"] / avg_vol_30d if avg_vol_30d else 0,
                    "gap_pct": gap_pct,
                })
            except Exception as e:
                logger.warning(f"Failed to fetch snapshot for {sym}: {e}")
        return pd.DataFrame(rows)
