"""Research-only replay opportunity de-duplication.

The production scanner still evaluates every 5-minute observation. Historical
LONG validation collapses repeated observations of the same 1H setup into one
causal trade opportunity. The first eligible observation is retained.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any


LONG_OPPORTUNITY_MIN_SEPARATION_MINUTES = 60


def _parse_replay_time(signal: dict[str, Any]):
    value = signal.get("_replay_timestamp")
    if value is not None:
        return value.to_pydatetime() if hasattr(value, "to_pydatetime") else value

    raw = signal.get("_replay_time") or signal.get("replay_time")
    if not raw:
        raise ValueError("LONG replay signal missing replay timestamp")
    parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def deduplicate_long_opportunities(
    signals: list[dict[str, Any]],
    *,
    min_separation_minutes: int = LONG_OPPORTUNITY_MIN_SEPARATION_MINUTES,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if min_separation_minutes <= 0:
        raise ValueError("min_separation_minutes must be positive")

    ordered = sorted(
        signals,
        key=lambda row: (
            str(row.get("_replay_time") or row.get("replay_time") or ""),
            str(row.get("symbol", "")),
            str(row.get("direction", "")),
        ),
    )

    kept: list[dict[str, Any]] = []
    last_kept: dict[tuple[str, str], datetime] = {}
    suppressed = 0

    for signal in ordered:
        if signal.get("direction") != "LONG":
            kept.append(signal)
            continue

        replay_time = _parse_replay_time(signal)
        key = (str(signal.get("symbol", "")), "LONG")
        previous = last_kept.get(key)

        if previous is not None and replay_time - previous < timedelta(minutes=min_separation_minutes):
            suppressed += 1
            continue

        opportunity = dict(signal)
        opportunity["_research_opportunity_id"] = (
            f"{key[0]}|{key[1]}|{replay_time.isoformat()}"
        )
        kept.append(opportunity)
        last_kept[key] = replay_time

    return kept, {
        "policy": "first_signal_per_symbol_direction_with_minimum_time_separation",
        "timeframe_basis": "1h_LONG_setup",
        "min_separation_minutes": min_separation_minutes,
        "raw_signals": len(signals),
        "independent_signals": len(kept),
        "suppressed_duplicate_signals": suppressed,
    }
