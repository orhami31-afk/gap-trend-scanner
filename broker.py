"""
broker.py
----------
שכבת ביצוע (Execution). זהו ה-interface שמחבר את הבוט לברוקר האמיתי שלך.

חשוב: בקובץ הזה יש שתי מחלקות -
1. PaperBroker - "ברוקר נייר" שרק מדמה ביצוע ורושם ללוג. בטוח להרצה מיידית,
   מומלץ להתחיל איתו כדי לוודא שהלוגיקה מייצרת עסקאות הגיוניות.
2. AlpacaBroker - שלד (stub) לחיבור אמיתי ל-Alpaca (ברוקר פופולרי עם API טוב
   ל-swing/algo trading). צריך למלא כאן את מפתחות ה-API האישיים שלך כדי
   שזה יבצע פקודות אמיתיות. לא ממולא בכוונה - זה משהו שאתה צריך להזין בעצמך.

כדי לחבר ברוקר אחר (Interactive Brokers, TradeStation וכו') - ממש מחלקה חדשה
שיורשת מ-BrokerInterface ומממשת את אותן מתודות.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
import logging
from risk_manager import TradePlan

logger = logging.getLogger("gap_trend_bot.broker")


class BrokerInterface(ABC):
    @abstractmethod
    def place_entry_order(self, plan: TradePlan) -> str:
        """שולח פקודת כניסה. מחזיר order_id."""
        ...

    @abstractmethod
    def update_stop_loss(self, symbol: str, new_stop: float) -> None:
        """מעדכן/גורר סטופ-לוס קיים."""
        ...

    @abstractmethod
    def close_position(self, symbol: str) -> None:
        """סוגר פוזיציה קיימת (למשל בתום 5 ימי מסחר אם לא נסגרה קודם)."""
        ...

    @abstractmethod
    def get_open_positions(self) -> list[str]:
        ...


class PaperBroker(BrokerInterface):
    """ברוקר דמה - לא שולח שום פקודה אמיתית, רק מדמה ורושם ללוג. שימושי לבדיקה."""

    def __init__(self):
        self._positions: dict[str, TradePlan] = {}

    def place_entry_order(self, plan: TradePlan) -> str:
        self._positions[plan.symbol] = plan
        order_id = f"PAPER-{plan.symbol}-{id(plan)}"
        logger.info(f"[PAPER] Entry order placed: {plan.symbol} {plan.direction} "
                    f"{plan.shares} shares @ {plan.entry_price:.2f} (order_id={order_id})")
        return order_id

    def update_stop_loss(self, symbol: str, new_stop: float) -> None:
        if symbol in self._positions:
            self._positions[symbol].stop_loss = new_stop
        logger.info(f"[PAPER] Stop updated for {symbol}: {new_stop:.2f}")

    def close_position(self, symbol: str) -> None:
        if symbol in self._positions:
            del self._positions[symbol]
        logger.info(f"[PAPER] Position closed: {symbol}")

    def get_open_positions(self) -> list[str]:
        return list(self._positions.keys())


class AlpacaBroker(BrokerInterface):
    """
    שלד לחיבור ל-Alpaca. דורש: pip install alpaca-trade-api --break-system-packages
    ומפתחות API אישיים (מוגדרים כמשתני סביבה ALPACA_API_KEY / ALPACA_SECRET_KEY).

    לא מבצע דבר עד שתמלא את הפרטים שלך - זו נקודת ההתחלה לחיבור אמיתי.
    """

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        try:
            import alpaca_trade_api as tradeapi
        except ImportError as e:
            raise ImportError(
                "alpaca-trade-api is not installed. Run: pip install alpaca-trade-api --break-system-packages"
            ) from e
        base_url = "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"
        self.api = tradeapi.REST(api_key, secret_key, base_url)

    def place_entry_order(self, plan: TradePlan) -> str:
        side = "buy" if plan.direction == "long" else "sell"
        order = self.api.submit_order(
            symbol=plan.symbol,
            qty=plan.shares,
            side=side,
            type="market",
            time_in_force="day",
        )
        logger.info(f"[ALPACA] Order submitted: {order.id}")
        # TODO: שלח גם פקודת stop-loss ו-take-profit נלוות (bracket order)
        return order.id

    def update_stop_loss(self, symbol: str, new_stop: float) -> None:
        # TODO: לממש עדכון/ביטול-והחלפה של פקודת הסטופ הקיימת דרך Alpaca API
        logger.info(f"[ALPACA] TODO: update stop for {symbol} to {new_stop:.2f}")

    def close_position(self, symbol: str) -> None:
        self.api.close_position(symbol)
        logger.info(f"[ALPACA] Position closed: {symbol}")

    def get_open_positions(self) -> list[str]:
        positions = self.api.list_positions()
        return [p.symbol for p in positions]
