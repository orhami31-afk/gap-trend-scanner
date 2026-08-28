"""
notifier.py
------------
התראות Push חינמיות לחלוטין לטלפון, דרך ntfy.sh - בלי הרשמה, בלי כרטיס אשראי.

איך זה עובד:
1. בוחרים "topic" - מזהה פרטי (מחרוזת ארוכה ואקראית, כמו סיסמה - כל מי שיודע
   אותה יכול לראות את ההתראות, אז אל תבחר משהו מנוחש כמו "mystocks").
2. מתקינים את אפליקציית ntfy החינמית (iOS/Android) ונרשמים (Subscribe) לאותו topic.
3. הסקריפט הזה שולח בקשת POST רגילה ל-https://ntfy.sh/<topic> - וזהו, ההתראה מגיעה.

דורש משתנה סביבה: NTFY_TOPIC (אם לא מוגדר, ההתראות פשוט מדולגות בשקט - לא שובר
כלום אם המשתמש לא הגדיר את זה).
"""

from __future__ import annotations
import os
import logging
import requests

logger = logging.getLogger("notifier")

NTFY_BASE_URL = "https://ntfy.sh"


def send_push_notification(title: str, message: str, priority: str = "default", tags: str = "") -> bool:
    """
    priority: 'min' | 'low' | 'default' | 'high' | 'urgent'
    tags: השוואה חופשית ל-emoji של ntfy (למשל 'chart_with_upwards_trend', 'rotating_light')
    מחזיר True אם נשלח בהצלחה, False אם דולג (לא מוגדר) או נכשל - לעולם לא זורק
    exception, כדי שכשל בהתראה לא יפיל את כל הסריקה.
    """
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        logger.info("NTFY_TOPIC not set - skipping push notification.")
        return False
    try:
        headers = {"Title": title.encode("utf-8"), "Priority": priority}
        if tags:
            headers["Tags"] = tags
        resp = requests.post(
            f"{NTFY_BASE_URL}/{topic}",
            data=message.encode("utf-8"),
            headers=headers,
            timeout=15,
        )
        if resp.status_code != 200:
            logger.error(f"ntfy.sh push failed: {resp.status_code} {resp.text}")
            return False
        logger.info(f"Push notification sent: {title}")
        return True
    except Exception as e:
        logger.error(f"Push notification failed (non-fatal): {e}")
        return False
