"""Persistent diagnostic watchlist for RRCE Stage-2 liquidity sweeps.

The watchlist makes the gap between a 15m sweep and a later 5m confirmation
observable across independent scanner runs. It is intentionally not an alert
or signal queue: every trade still has to pass the full live RRCE evaluation.
"""

import json
import os
from datetime import datetime, timedelta, timezone


WATCHLIST_FILE = "storage/rrce_watchlist.json"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _load() -> dict:
    try:
        with open(WATCHLIST_FILE, "r") as file:
            data = json.load(file)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save(entries: dict) -> None:
    os.makedirs(os.path.dirname(WATCHLIST_FILE), exist_ok=True)
    with open(WATCHLIST_FILE, "w") as file:
        json.dump(entries, file, indent=2, sort_keys=True)


def _prune(entries: dict, now: datetime, ttl_hours: float) -> dict:
    cutoff = now - timedelta(hours=ttl_hours)
    return {
        key: entry for key, entry in entries.items()
        if datetime.fromisoformat(entry["last_seen"]) >= cutoff
    }


def record_stage2_setup(symbol: str, direction: str, regime: str,
                        stage1: dict, stage2: dict, ttl_hours: float,
                        now: datetime | None = None) -> int:
    """Record a swept liquidity setup and return the current active count."""
    now = now or _now()
    entries = _prune(_load(), now, ttl_hours)
    key = f"{symbol}|{direction}"
    existing = entries.get(key, {})
    entries[key] = {
        "symbol": symbol,
        "direction": direction,
        "regime": regime,
        "range_low": stage1["range_low"],
        "range_high": stage1["range_high"],
        "pool_level": stage2["pool_level"],
        "sweep_extreme": stage2["sweep_extreme"],
        "first_seen": existing.get("first_seen", now.isoformat()),
        "last_seen": now.isoformat(),
        "observations": existing.get("observations", 0) + 1,
    }
    _save(entries)
    return len(entries)


def active_count(ttl_hours: float, now: datetime | None = None) -> int:
    """Remove expired entries and return the number still being watched."""
    now = now or _now()
    entries = _prune(_load(), now, ttl_hours)
    _save(entries)
    return len(entries)
