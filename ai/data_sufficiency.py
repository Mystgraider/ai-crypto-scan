"""Phase 2D-D3A: evidence dataset sufficiency checks.

This module only inspects persisted signal records. It does not alter
ranking weights, thresholds, signals, or trading decisions.
"""

ATTRIBUTION_REQUIRED_FIELDS = {
    "attribution_version",
    "components",
    "ai_rank_raw",
    "ai_rank_score",
}

COMPLETED_STATUSES = {"TP3_HIT", "SL_HIT", "EXPIRED"}
WIN_STATUSES = {"TP3_HIT"}
LOSS_STATUSES = {"SL_HIT"}


def _parse_attribution(value):
    if not isinstance(value, dict):
        return None
    if not ATTRIBUTION_REQUIRED_FIELDS.issubset(value):
        return None
    if not isinstance(value.get("components"), dict):
        return None
    return value


def analyze_data_sufficiency(signals, *, min_attributed_records=20):
    """Return deterministic dataset-quality metrics for attribution analysis."""
    records = list(signals or [])
    attributed = [row for row in records if _parse_attribution(row.get("ai_attribution"))]
    completed = [row for row in attributed if row.get("status") in COMPLETED_STATUSES]
    winners = [row for row in completed if row.get("status") in WIN_STATUSES]
    losers = [row for row in completed if row.get("status") in LOSS_STATUSES]

    attributed_count = len(attributed)
    total_count = len(records)
    coverage = (attributed_count / total_count) if total_count else 0.0

    return {
        "ready": attributed_count >= min_attributed_records and len(winners) > 0 and len(losers) > 0,
        "total_records": total_count,
        "attributed_records": attributed_count,
        "attribution_coverage": round(coverage, 4),
        "completed_attributed_records": len(completed),
        "winner_records": len(winners),
        "loser_records": len(losers),
        "min_attributed_records": min_attributed_records,
        "missing_attribution_records": total_count - attributed_count,
    }
