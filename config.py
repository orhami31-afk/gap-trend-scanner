"""
config.py
---------
כל הפרמטרים של אסטרטגיית Gap & Trend Breakout במקום אחד.
שנה כאן ערכים - שאר הקוד קורא מהקובץ הזה ולא מכיל מספרים "קשיחים".
"""

from dataclasses import dataclass, field
from typing import List


@dataclass
class UniverseConfig:
    """שלב 1: בחירת יקום המניות הראשוני"""
    min_price: float = 10.0
    min_avg_daily_volume: int = 1_000_000       # ממוצע נפח יומי ל-30 יום
    min_rvol: float = 2.0                        # נפח יחסי מינימלי (פי כמה מהממוצע)
    rvol_lookback_days: int = 30
    min_gap_pct: float = 2.0                      # גאפ מינימלי (%)
    max_gap_pct: float = 5.0                      # גאפ מקסימלי (%)


@dataclass
class EntryConfig:
    """שלב 2: תנאי כניסה (כולם חייבים להתקיים יחד)"""
    intraday_timeframe: str = "15m"               # "15m" או "60m"
    trendline_lookback_bars: int = 20              # כמה נרות אחורה לבניית קו המגמה
    breakout_volume_multiplier: float = 1.5        # נר הפריצה חייב נפח פי X מהממוצע
    breakout_volume_lookback: int = 20

    ema_fast: int = 9
    ema_medium: int = 20
    sma_slow: int = 50

    # RSI
    rsi_period: int = 14
    rsi_long_min: float = 50.0
    rsi_long_max: float = 70.0
    rsi_short_min: float = 30.0
    rsi_short_max: float = 50.0

    # MACD
    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9


@dataclass
class SentimentConfig:
    """שלב 3: פילטר סנטימנט שוק רחב"""
    market_symbols: List[str] = field(default_factory=lambda: ["SPY", "QQQ"])
    market_sma_period: int = 20


@dataclass
class VolumeProfileConfig:
    """שלב 3: אזורי ערך מוסדי (POC / Volume Profile)"""
    lookback_days: int = 30
    num_bins: int = 50
    poc_proximity_pct: float = 1.0   # הפריצה צריכה להתרחש עד X% מה-POC


@dataclass
class RiskConfig:
    """שלב 4: ניהול סיכונים"""
    risk_reward_ratio: float = 2.0
    fixed_risk_usd: float = 500.0
    fixed_target_usd: float = 1000.0
    breakeven_trigger_rr: float = 1.0   # ברגע שמגיעים לרווח של 1:1 -> גוררים סטופ ל-breakeven


@dataclass
class TradeManagementConfig:
    """כללי אחזקה - סווינג קצר"""
    min_holding_days: int = 2
    max_holding_days: int = 5


@dataclass
class StrategyConfig:
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    entry: EntryConfig = field(default_factory=EntryConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    volume_profile: VolumeProfileConfig = field(default_factory=VolumeProfileConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trade_mgmt: TradeManagementConfig = field(default_factory=TradeManagementConfig)


CONFIG = StrategyConfig()
