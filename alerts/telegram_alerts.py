import requests

from config.settings import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID
)


def send_telegram_alert(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    requests.post(url, json=payload)
