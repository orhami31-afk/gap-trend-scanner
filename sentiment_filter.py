"""
sentiment_filter.py
--------------------
שלב 3: פילטר סנטימנט שוק רחב (SPY / QQQ).
אוסר כניסה ללונגים אם מדד השוק הרחב מתחת לממוצע הנע שלו.
"""

from __future__ import annotations
import logging
from config import SentimentConfig
from data_provider import DataProvider
from indicators import sma

logger = logging.getLogger("gap_trend_bot.sentiment")


class MarketSentiment:
    def __init__(self, provider: DataProvider, cfg: SentimentConfig):
        self.provider = provider
        self.cfg = cfg
        self._cache: dict[str, bool] = {}

    def refresh(self):
        """מושך נתונים עדכניים לכל אינדקסי הסנטימנט ומחשב האם כל אחד 'בריא' (מעל הממוצע הנע)."""
        self._cache.clear()
        for symbol in self.cfg.market_symbols:
            daily = self.provider.get_daily_bars(symbol, lookback_days=self.cfg.market_sma_period + 10)
            if daily.empty or len(daily) < self.cfg.market_sma_period:
                logger.warning(f"Not enough data for sentiment symbol {symbol}")
                self._cache[symbol] = False
                continue
            sma_val = sma(daily["close"], self.cfg.market_sma_period).iloc[-1]
            last_close = daily["close"].iloc[-1]
            self._cache[symbol] = bool(last_close > sma_val)
            logger.info(f"Sentiment {symbol}: close={last_close:.2f} sma{self.cfg.market_sma_period}={sma_val:.2f} healthy={self._cache[symbol]}")

    def is_market_healthy_for_longs(self) -> bool:
        """כל אינדקסי הסנטימנט חייבים להיות מעל הממוצע הנע שלהם כדי לאשר לונגים."""
        if not self._cache:
            self.refresh()
        return all(self._cache.values())
