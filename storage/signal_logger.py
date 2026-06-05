import os
import csv
from datetime import datetime, timezone

SIGNALS_FILE = "storage/signals.csv"

FIELDNAMES = [
    "timestamp", "symbol", "direction",
    "entry", "sl", "tp1", "tp2", "tp3",
    "score", "grade", "rr", "status"
]


def _ensure_file():
    os.makedirs("storage", exist_ok=True)
    if not os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def save_signal(
    symbol:    str,
    direction: str,
    entry:     float,
    sl:        float,
    tp1:       float,
    tp2:       float,
    tp3:       float,
    score:     float = 0.0,
    grade:     str   = "D",
    rr:        float = 0.0,
    status:    str   = "OPEN",
):
    _ensure_file()

    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol":    symbol,
        "direction": direction,
        "entry":     entry,
        "sl":        sl,
        "tp1":       tp1,
        "tp2":       tp2,
        "tp3":       tp3,
        "score":     round(score, 2),
        "grade":     grade,
        "rr":        rr,
        "status":    status,
    }

    with open(SIGNALS_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(row)

    print(f"📝 Logged: {symbol} {direction}")


def load_signals() -> list[dict]:
    _ensure_file()
    with open(SIGNALS_FILE, "r", newline="") as f:
        return list(csv.DictReader(f))


def update_signal_status(symbol: str, direction: str, entry: float, new_status: str):
    """Update the status of the most recent matching open signal."""
    _ensure_file()
    rows = load_signals()
    updated = False

    for row in reversed(rows):
        if (
            row["symbol"] == symbol and
            row["direction"] == direction and
            float(row["entry"]) == entry and
            row["status"] == "OPEN"
        ):
            row["status"] = new_status
            updated = True
            break

    if updated:
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
