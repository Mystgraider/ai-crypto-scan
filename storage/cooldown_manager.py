import os
import json
from datetime import datetime, timezone, timedelta
from config import CONFIG

COOLDOWN_FILE = "storage/cooldown.json"


def _load() -> dict:
    if os.path.exists(COOLDOWN_FILE):
        try:
            with open(COOLDOWN_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save(data: dict):
    os.makedirs("storage", exist_ok=True)
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f, indent=2)


def is_on_cooldown(symbol: str) -> bool:
    data = _load()
    if symbol not in data:
        return False
    last = datetime.fromisoformat(data[symbol])
    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=CONFIG["signal_cooldown_hours"]
    )
    return last > cutoff


def set_cooldown(symbol: str):
    data = _load()
    data[symbol] = datetime.now(timezone.utc).isoformat()
    _save(data)
