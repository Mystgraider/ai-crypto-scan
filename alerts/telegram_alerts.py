import os
import requests


def send_telegram_alert(message: str, parse_mode: str = "HTML") -> bool:

    bot_token = os.getenv("BOT_TOKEN")
    chat_id   = os.getenv("CHAT_ID")

    if not bot_token or not chat_id:
        print("❌ Telegram: BOT_TOKEN or CHAT_ID missing")
        return False

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": parse_mode,
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        ok   = resp.status_code == 200
        print(f"{'✅' if ok else '❌'} Telegram: {resp.status_code}")
        return ok

    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False


def format_signal(
    symbol:    str,
    direction: str,
    score:     float,
    entry:     float,
    sl:        float,
    tp1:       float,
    tp2:       float,
    tp3:       float,
    rr:        float,
    grade:     str,
) -> str:

    emoji = "🟢" if direction == "LONG" else "🔴"

    return (
        f"🚨 <b>ELITE V5 SIGNAL</b>\n\n"
        f"{emoji} <b>{direction}</b> — <b>{symbol}</b>\n"
        f"🏅 Grade: <b>{grade}</b>  |  Score: <b>{round(score, 1)}</b>\n\n"
        f"🎯 Entry: <code>{entry}</code>\n"
        f"🛑 SL:    <code>{sl}</code>\n"
        f"✅ TP1:  <code>{tp1}</code>\n"
        f"✅ TP2:  <code>{tp2}</code>\n"
        f"✅ TP3:  <code>{tp3}</code>\n\n"
        f"📐 RR: {rr}R"
    )
