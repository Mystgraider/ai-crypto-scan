import os
import csv
import json
from datetime import datetime, timezone

SIGNALS_FILE = "storage/signals.csv"

EXECUTION_OUTCOME_FIELDS = [
    "tp1_qty_pct", "tp2_qty_pct", "tp3_qty_pct",
    "tp1_exit_price", "tp2_exit_price", "tp3_exit_price",
    "tp1_realized_r", "tp2_realized_r", "tp3_realized_r",
    "remaining_position_pct", "remaining_position_exit_r",
]

FIELDNAMES = [
    "timestamp", "symbol", "direction",
    "entry", "initial_sl", "sl", "tp1", "tp2", "tp3",
    "score", "grade", "rr",
    "adx", "rsi", "rel_volume", "spike_tier",
    "mtf_status", "btc_regime", "rs_label",
    "funding_pct", "oi_signal", "beta_label",
    "ai_rank_score", "ai_rank_raw", "confidence", "ai_attribution",
    "status",
    "tp1_hit_at", "tp2_hit_at", "tp3_hit_at",
    "exit_at", "exit_price", "realized_r",
    *EXECUTION_OUTCOME_FIELDS,
]

ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}


def _ensure_file():
    os.makedirs("storage", exist_ok=True)
    if not os.path.exists(SIGNALS_FILE):
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
        return

    # Migrate older tracked CSV schemas in-place before any append/update.
    with open(SIGNALS_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        existing_fields = reader.fieldnames or []
        if existing_fields == FIELDNAMES:
            return
        rows = list(reader)

    with open(SIGNALS_FILE, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in FIELDNAMES})


def save_signal(
    symbol: str, direction: str, entry: float, sl: float,
    tp1: float, tp2: float, tp3: float,
    score: float = 0.0, grade: str = "C", rr: float = 0.0,
    adx: float = 0.0, rsi: float = 0.0, rel_volume: float = 0.0,
    spike_tier: str = "", mtf_status: str = "", btc_regime: str = "",
    rs_label: str = "", funding_pct: str = "0", oi_signal: str = "",
    beta_label: str = "", ai_rank_score: float | None = None,
    ai_rank_raw: float | None = None, confidence: float | None = None,
    ai_attribution: dict | None = None,
    status: str = "OPEN",
):
    _ensure_file()
    row = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "symbol": symbol, "direction": direction,
        "entry": entry, "initial_sl": sl, "sl": sl,
        "tp1": tp1, "tp2": tp2, "tp3": tp3,
        "score": round(score, 2), "grade": grade, "rr": rr,
        "adx": round(adx, 2), "rsi": round(rsi, 2),
        "rel_volume": round(rel_volume, 2), "spike_tier": spike_tier,
        "mtf_status": mtf_status, "btc_regime": btc_regime,
        "rs_label": rs_label, "funding_pct": funding_pct,
        "oi_signal": oi_signal, "beta_label": beta_label,
        "ai_rank_score": "" if ai_rank_score is None else round(ai_rank_score, 2),
        "ai_rank_raw": "" if ai_rank_raw is None else round(ai_rank_raw, 2),
        "confidence": "" if confidence is None else round(confidence, 2),
        "ai_attribution": "" if ai_attribution is None else json.dumps(ai_attribution, sort_keys=True, separators=(",", ":")),
        "status": status,
        "tp1_hit_at": "", "tp2_hit_at": "", "tp3_hit_at": "",
        "exit_at": "", "exit_price": "", "realized_r": "",
        **{field: "" for field in EXECUTION_OUTCOME_FIELDS},
    }
    with open(SIGNALS_FILE, "a", newline="") as f:
        csv.DictWriter(f, fieldnames=FIELDNAMES).writerow(row)
    print(f"📝 Logged: {symbol} {direction} @ {entry}")


def load_signals() -> list[dict]:
    _ensure_file()
    with open(SIGNALS_FILE, "r", newline="") as f:
        return list(csv.DictReader(f))


def update_signal_tracking(
    symbol: str, direction: str, entry: float, new_status: str,
    new_sl: float | None = None, event_at: str | None = None,
    event_price: float | None = None, realized_r: float | None = None,
) -> bool:
    """Persist lifecycle state and event data for the latest active signal."""
    _ensure_file()
    rows = load_signals()
    updated = False
    event_at = event_at or datetime.now(timezone.utc).isoformat()

    for row in reversed(rows):
        if (
            row.get("symbol") == symbol
            and row.get("direction") == direction
            and float(row.get("entry", 0)) == entry
            and row.get("status") in ACTIVE_STATUSES
        ):
            row["status"] = new_status
            if not row.get("initial_sl"):
                row["initial_sl"] = row.get("sl", "")
            if new_sl is not None:
                row["sl"] = new_sl

            if new_status == "OPEN_TP1" and not row.get("tp1_hit_at"):
                row["tp1_hit_at"] = event_at
            elif new_status == "OPEN_TP2" and not row.get("tp2_hit_at"):
                row["tp2_hit_at"] = event_at
            elif new_status == "TP3_HIT":
                row["tp3_hit_at"] = event_at
                row["exit_at"] = event_at
            elif new_status in {"SL_HIT", "EXPIRED"}:
                row["exit_at"] = event_at

            if event_price is not None and new_status in {"TP3_HIT", "SL_HIT"}:
                row["exit_price"] = event_price
            if realized_r is not None and new_status in {"TP3_HIT", "SL_HIT", "EXPIRED"}:
                row["realized_r"] = round(realized_r, 6)

            updated = True
            break

    if updated:
        with open(SIGNALS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()
            writer.writerows(rows)
    return updated


def update_signal_status(symbol: str, direction: str, entry: float, new_status: str):
    """Backward-compatible wrapper for older callers."""
    return update_signal_tracking(symbol, direction, entry, new_status)
