"""Research-only replay opportunity de-duplication.

The production scanner still emits every eligible 5-minute observation.
Historical LONG validation uses a causal one-opportunity-per-hour rule because
the LONG setup is built from a 1H pullback/reclaim state. The first signal in
a burst is retained; later observations inside the separation window are
treated as repeated observations of the same opportunity.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any


LONG_OPPORTUNITY_MIN_SEPARATION_MINUTES = 60


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
            str(row.get("_replay_time", "")),
            str(row.get("symbol", "")),
            str(row.get("direction", "")),
        ),
    )

    kept: list[dict[str, Any]] = []
    last_kept: dict[tuple[str, str], Any] = {}
    suppressed = 0

    for signal in ordered:
        if signal.get("direction") != "LONG":
            kept.append(signal)
            continue

        replay_time = signal.get("_replay_timestamp")
        if replay_time is None:
            raise ValueError("LONG replay signal missing _replay_timestamp")

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
