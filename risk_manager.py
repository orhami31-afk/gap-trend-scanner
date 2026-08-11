"""
risk_manager.py
-----------------
שלב 4: ניהול סיכונים - חישוב סטופ-לוס, יעד רווח, גודל פוזיציה,
וגרירת סטופ ל-breakeven ברגע שמגיעים ל-1:1.
"""

from __future__ import annotations
from dataclasses import dataclass
import pandas as pd
import logging

from config import RiskConfig

logger = logging.getLogger("gap_trend_bot.risk")


@dataclass
class TradePlan:
    symbol: str
    direction: str          # "long" / "short"
    entry_price: float
    stop_loss: float
    take_profit: float
    shares: int
    risk_usd: float
    reward_usd: float
    breakeven_triggered: bool = False


def find_recent_swing_stop(df: pd.DataFrame, direction: str, lookback: int = 10) -> float:
    """מוצא שפל מקומי אחרון (ללונג) או שיא מקומי אחרון (לשורט) לצורך מיקום סטופ טכני."""
    window = df.tail(lookback)
    if direction == "long":
        return float(window["low"].min())
    else:
        return float(window["high"].max())


def build_trade_plan(
    symbol: str,
    direction: str,
    entry_price: float,
    intraday_df: pd.DataFrame,
    cfg: RiskConfig,
) -> TradePlan:
    """
    בונה תוכנית עסקה מלאה:
    - סטופ-לוס טכני (שפל/שיא מקומי), מותאם כך שהסיכון הכספי = fixed_risk_usd בדיוק
      (באמצעות חישוב גודל הפוזיציה, לא הזזת הסטופ עצמו).
    - יעד רווח לפי risk_reward_ratio (או fixed_target_usd אם הוגדר).
    """
    technical_stop = find_recent_swing_stop(intraday_df, direction)

    if direction == "long":
        risk_per_share = entry_price - technical_stop
    else:
        risk_per_share = technical_stop - entry_price

    if risk_per_share <= 0:
        # הגנה: אם הסטופ הטכני "הפוך" (לא הגיוני), נשתמש במרחק מינימלי סביר
        risk_per_share = entry_price * 0.01
        technical_stop = entry_price - risk_per_share if direction == "long" else entry_price + risk_per_share
        logger.warning(f"{symbol}: technical stop invalid, using 1% fallback")

    shares = int(cfg.fixed_risk_usd // risk_per_share)
    shares = max(shares, 1)

    actual_risk_usd = shares * risk_per_share
    reward_per_share = risk_per_share * cfg.risk_reward_ratio

    if direction == "long":
        take_profit = entry_price + reward_per_share
    else:
        take_profit = entry_price - reward_per_share

    actual_reward_usd = shares * reward_per_share

    return TradePlan(
        symbol=symbol,
        direction=direction,
        entry_price=entry_price,
        stop_loss=technical_stop,
        take_profit=take_profit,
        shares=shares,
        risk_usd=round(actual_risk_usd, 2),
        reward_usd=round(actual_reward_usd, 2),
    )


def update_breakeven(plan: TradePlan, current_price: float, cfg: RiskConfig) -> TradePlan:
    """
    בודק אם העסקה הגיעה לרווח של breakeven_trigger_rr (ברירת מחדל 1:1)
    ואם כן, גורר את הסטופ לנקודת הכניסה.
    """
    if plan.breakeven_triggered:
        return plan

    risk_per_share = abs(plan.entry_price - plan.stop_loss)
    trigger_distance = risk_per_share * cfg.breakeven_trigger_rr

    if plan.direction == "long":
        reached = current_price >= plan.entry_price + trigger_distance
    else:
        reached = current_price <= plan.entry_price - trigger_distance

    if reached:
        plan.stop_loss = plan.entry_price
        plan.breakeven_triggered = True
        logger.info(f"{plan.symbol}: stop moved to breakeven ({plan.entry_price})")

    return plan


def estimate_holding_days(daily_df: pd.DataFrame, entry_price: float, target_price: float,
                           min_days: int = 1, max_days: int = 10) -> int:
    """
    אומדן מספר ימי אחזקה סבירים: מבוסס על תנועה יומית ממוצעת (ATR מקורב) מול
    המרחק ליעד. לא חוזה בוודאות - זו הערכה גסה לצורך תכנון בלבד.
    מוגבל בין min_days (מסחר יומי) ל-max_days (ברירת מחדל 10 = כשבוע וחצי מסחר).
    """
    avg_daily_range = (daily_df["high"] - daily_df["low"]).tail(20).mean()
    if avg_daily_range <= 0 or pd.isna(avg_daily_range):
        return min(5, max_days)
    distance = abs(target_price - entry_price)
    days = int(-(-distance // avg_daily_range))  # ceiling division
    return max(min_days, min(days, max_days))
