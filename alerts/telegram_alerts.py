import os
import requests


def send_telegram_alert(message):

    bot_token = os.getenv("BOT_TOKEN")
    chat_id = os.getenv("CHAT_ID")

    if not bot_token:
        print("BOT_TOKEN missing")
        return

    if not chat_id:
        print("CHAT_ID missing")
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{bot_token}/sendMessage"
    )

    payload = {
        "chat_id": chat_id,
        "text": message
    }

    try:

        response = requests.post(
            url,
            json=payload,
            timeout=10
        )

        print(
            f"Telegram Status: {response.status_code}"
        )

    except Exception as e:

        print(
            f"Telegram Error: {e}"
        )
