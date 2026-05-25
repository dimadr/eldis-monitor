import os
import requests
from datetime import datetime

from app.config import settings


def send_alert(
    object_name: str,
    device_name: str,
    error_type: str,
    value: float,
    previous: float | None = None,
):
    if not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_CHAT_ID:
        return

    text = f"""⚠️ ELDIS ALERT

Object: {object_name}
Device: {device_name}
Type: {error_type}
Value: {value}
Previous: {previous}

Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}"""

    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": settings.TELEGRAM_CHAT_ID, "text": text})
