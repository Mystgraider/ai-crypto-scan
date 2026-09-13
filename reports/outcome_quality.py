"""Phase 2D-H.6 — outcome quality and evidence diagnostics.

Read-only diagnostics over stored signals. This module does not change
scanner decisions, ranking, thresholds, sizing, or outcome resolution.

Canonical trade-R resolution remains delegated to H.5. The diagnostics
report which authoritative source was selected and separately identifies
unresolved or incomplete outcome evidence.
"""

from collections import Counter

from reports.execution_outcome import calculate_canonical_trade_r

RESOLVED_STATUSES = {"TP3_HIT", "SL_HIT"}
TERMINAL_STATUSES = RESOLVED_STATUSES | {"EXPIRED"}


def _has_execution_evidence(signal):
    """Return whether any explicit execution field is present."""
    for level in ("tp1", "tp2", "tp3"):
        for suffix in ("qty_pct", "exit_price", "realized_r", "executed_at"):
            if signal.get(f"{level}_{suffix}") not in (None, ""):
                return True

    return any(
        signal.get(field) not in (None, "")
        for field in ("remaining_position_pct", "remaining_position_exit_r")
    )


def _execution_evidence_state(signal, outcome):
    """Classify explicit execution fields without inferring execution."""
    if not _has_execution_evidence(signal):
        return "none"
    if outcome.source == "explicit_execution":
        return "complete"
    return "incomplete_or_invalid"


def _coverage(count, denominator):
    """Return a deterministic percentage, avoiding division by zero."""
    if denominator <= 0:
        return 0.0
    return round((count / denominator) * 100.0, 2)


def analyze_outcome_quality(signals):
    """Return deterministic diagnostics for a collection of signal records."""
    signals = list(signals)
    source_counts = Counter(
        {
            "explicit_execution": 0,
            "terminal_realized_r": 0,
            "legacy_calculation": 0,
            "unresolved": 0,
        }
    )
    execution_counts = Counter(
        {
            "complete": 0,
            "incomplete_or_invalid": 0,
            "none": 0,
        }
    )
    unresolved_reasons = Counter()

    terminal = 0
    resolved = 0
    expired = 0
    unresolved = 0

    for signal in signals:
        status = signal.get("status")
        outcome = calculate_canonical_trade_r(signal)
        execution_counts[_execution_evidence_state(signal, outcome)] += 1

        if status == "EXPIRED":
            expired += 1
        if status in TERMINAL_STATUSES:
            terminal += 1

        source_counts[outcome.source] += 1

        if status in RESOLVED_STATUSES:
            if outcome.resolved:
                resolved += 1
            else:
                unresolved += 1
                unresolved_reasons[outcome.reason or "no authoritative outcome"] += 1

    total = len(signals)
    resolved_or_unresolved = resolved + unresolved

    return {
        "total_signals": total,
        "terminal_signals": terminal,
        "resolved_signals": resolved,
        "expired_signals": expired,
        "unresolved_resolved_statuses": unresolved,
        "outcome_source_counts": dict(sorted(source_counts.items())),
        "execution_evidence_counts": dict(sorted(execution_counts.items())),
        "unresolved_reasons": dict(sorted(unresolved_reasons.items())),
        "coverage_pct": {
            "terminal": _coverage(terminal, total),
            "resolved": _coverage(resolved, resolved_or_unresolved),
            "unresolved_resolved_statuses": _coverage(unresolved, resolved_or_unresolved),
            "expired": _coverage(expired, total),
            "explicit_execution": _coverage(source_counts["explicit_execution"], total),
            "terminal_realized_r": _coverage(source_counts["terminal_realized_r"], total),
            "legacy_calculation": _coverage(source_counts["legacy_calculation"], total),
            "unresolved": _coverage(source_counts["unresolved"], total),
            "complete_execution_evidence": _coverage(execution_counts["complete"], total),
            "incomplete_or_invalid_execution_evidence": _coverage(
                execution_counts["incomplete_or_invalid"], total
            ),
        },
    }
