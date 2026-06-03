import os
import json
from datetime import datetime

SIGNALS_FILE = "storage/signals_history.json"


def save_signal(
    symbol,
    direction,
    entry,
    sl,
    tp1,
    tp2,
    tp3,
    score=0
):

    os.makedirs("storage", exist_ok=True)

    if os.path.exists(SIGNALS_FILE):

        try:
            with open(
                SIGNALS_FILE,
                "r"
            ) as f:

                signals = json.load(f)

        except:

            signals = []

    else:

        signals = []

    signal = {

        "timestamp":
            datetime.utcnow().isoformat(),

        "symbol":
            symbol,

        "direction":
            direction,

        "entry":
            entry,

        "sl":
            sl,

        "tp1":
            tp1,

        "tp2":
            tp2,

        "tp3":
            tp3,

        "score":
            score,

        "status":
            "OPEN"
    }

    signals.append(signal)

    with open(
        SIGNALS_FILE,
        "w"
    ) as f:

        json.dump(
            signals,
            f,
            indent=2
        )

    print(
        f"Signal saved: {symbol}"
    )
