"""Phase 2D-D3B: read-only attribution analytics.

This module analyzes already-persisted attribution snapshots. It does not
change ranking weights, thresholds, signals, or trading decisions.
"""

from collections import defaultdict

from ai.data_sufficiency import analyze_data_sufficiency

COMPONENTS = ("trend", "quality", "rs", "oi", "rr", "sr", "category")


def _valid_attribution(value):
    return (
        isinstance(value, dict)
        and isinstance(value.get("components"), dict)
        and all(name in value["components"] for name in COMPONENTS)
    )


def analyze_attribution(signals, *, min_attributed_records=20):
    """Return winner/loser component evidence with no tuning side effects."""
    records = list(signals or [])
    sufficiency = analyze_data_sufficiency(
        records, min_attributed_records=min_attributed_records
    )

    groups = {"winner": [], "loser": []}
    for row in records:
        attribution = row.get("ai_attribution")
        if not _valid_attribution(attribution):
            continue
        status = row.get("status")
        if status == "TP3_HIT":
            groups["winner"].append(attribution["components"])
        elif status == "SL_HIT":
            groups["loser"].append(attribution["components"])

    averages = {}
    differences = {}
    for group, rows in groups.items():
        averages[group] = {
            component: round(
                sum(float(row[component]) for row in rows) / len(rows), 4
            )
            if rows else None
            for component in COMPONENTS
        }

    for component in COMPONENTS:
        winner = averages["winner"][component]
        loser = averages["loser"][component]
        differences[component] = round(winner - loser, 4) if winner is not None and loser is not None else None

    evidence_level = "sufficient" if sufficiency["ready"] else "insufficient"
    return {
        "ready": sufficiency["ready"],
        "evidence_level": evidence_level,
        "sufficiency": sufficiency,
        "winner_averages": averages["winner"],
        "loser_averages": averages["loser"],
        "winner_minus_loser": differences,
        "winner_sample": len(groups["winner"]),
        "loser_sample": len(groups["loser"]),
        "components": list(COMPONENTS),
    }
