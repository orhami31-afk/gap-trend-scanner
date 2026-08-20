"""
config.py
---------
כל הפרמטרים של אסטרטגיית "Pullback Continuation" (גרסה 2 - מחליפה את Gap & Trend
Breakout המקורית). השינוי המרכזי: שערי חובה מצומצמים + ניקוד איכות (4 מתוך 5)
במקום AND מלא על כל 10 התנאים - כי AND מלא כמעט אף פעם לא נמצא ביקום סביר.

אחוז ההצלחה לעולם לא נקבע כאן - הוא תמיד מחושב בפועל ב-backtest.py על נתונים
היסטוריים אמיתיים, לכל מניה בנפרד.
"""

from dataclasses import dataclass, field


@dataclass
class UniverseConfig:
    """שלב 1: שערי חובה - כל מניה חייבת לעבור את כל אלה כדי בכלל להיכנס לבדיקה."""
    min_price: float = 15.0
    min_avg_daily_volume: int = 2_000_000
    min_rvol: float = 1.8
    rvol_lookback_days: int = 20
    min_gap_pct: float = 1.5
    max_gap_pct: float = 6.0


@dataclass
class QualityConfig:
    """שלב 2: מאגר תנאי איכות - נדרש min_quality_score מתוך quality_pool_size."""
    quality_pool_size: int = 5
    min_quality_score: int = 4

    ema_pullback: int = 20            # EMA לבדיקת נסיגה
    pullback_tolerance_pct: float = 2.0   # מרחק מותר מ-EMA20/POC כדי להיחשב "נסיגה"

    vwap_lookback_days: int = 20      # קירוב VWAP מגליל (אין נתוני תוך-יומי)
    vwap_volume_confirm_days: int = 20

    rsi_period: int = 14
    rsi_long_min: float = 40.0
    rsi_long_max: float = 50.0
    rsi_short_min: float = 50.0
    rsi_short_max: float = 60.0

    macd_fast: int = 12
    macd_slow: int = 26
    macd_signal: int = 9

    daily_trend_sma: int = 50
    daily_trend_slope_lookback: int = 5

    poc_lookback_days: int = 30
    poc_num_bins: int = 40


@dataclass
class SentimentConfig:
    """שער חובה נוסף (ללונג בלבד): SPY וגם QQQ מעל SMA20."""
    market_symbols: list = field(default_factory=lambda: ["SPY", "QQQ"])
    market_sma_period: int = 20


@dataclass
class RiskConfig:
    """שלב 3: ניהול סיכונים."""
    risk_reward_ratio: float = 2.0     # המפרט מאפשר 1.5-2.0, ברירת מחדל 2.0
    fixed_risk_usd: float = 500.0
    fixed_target_usd: float = 1000.0
    breakeven_trigger_rr: float = 1.0


@dataclass
class TradeManagementConfig:
    min_holding_days: int = 1
    max_holding_days: int = 10


@dataclass
class StrategyConfig:
    universe: UniverseConfig = field(default_factory=UniverseConfig)
    quality: QualityConfig = field(default_factory=QualityConfig)
    sentiment: SentimentConfig = field(default_factory=SentimentConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    trade_mgmt: TradeManagementConfig = field(default_factory=TradeManagementConfig)


CONFIG = StrategyConfig()
