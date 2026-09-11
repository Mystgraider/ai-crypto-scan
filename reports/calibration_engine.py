"""Phase 2D-B1 — historical AI calibration analysis.

This module is intentionally read-only: it measures how stored AI rank,
confidence, and grade relate to realized outcomes. It does not change any
scanner formula, weights, thresholds, or signal decisions.

Only terminal TP3_HIT / SL_HIT records are treated as resolved outcomes.
EXPIRED records remain censored and are excluded from win-rate calibration.
Legacy rows without AI fields are excluded from AI/confidence calibration.
"""

from collections import OrderedDict
from statistics import mean

from storage.signal_logger import load_signals

RESOLVED_STATUSES = {"TP3_HIT", "SL_HIT"}
DEFAULT_MIN_SAMPLE = 20

AI_SCORE_BUCKETS = (
    (0.0, 59.99, "0-59"),
    (60.0, 69.99, "60-69"),
    (70.0, 79.99, "70-79"),
    (80.0, 89.99, "80-89"),
    (90.0, 100.0, "90-100"),
)

CONFIDENCE_BUCKETS = AI_SCORE_BUCKETS
GRADE_BUCKETS = ("S", "A", "B", "C", "D")


def _number(value):
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _realized_r(signal):
    stored = _number(signal.get("realized_r"))
    if stored is not None:
        return stored

    if signal.get("status") not in RESOLVED_STATUSES:
        return None

    entry = _number(signal.get("entry"))
    exit_price = _number(signal.get("exit_price"))
    initial_sl = _number(signal.get("initial_sl") or signal.get("sl"))
    if None in (entry, exit_price, initial_sl):
        return None

    risk = abs(entry - initial_sl)
    if risk <= 0:
        return None
    if signal.get("direction") == "LONG":
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk


def _bucket(value, definitions):
    for low, high, label in definitions:
        if low <= value <= high:
            return label
    return None


def _row_metrics(rows, min_sample):
    outcomes = [(_realized_r(row), row) for row in rows]
    outcomes = [(r, row) for r, row in outcomes if r is not None]
    n = len(outcomes)
    wins = sum(1 for r, _ in outcomes if r > 0)
    net_r = sum(r for r, _ in outcomes)
    avg_r = mean(r for r, _ in outcomes) if outcomes else 0.0
    wr = (wins / n * 100.0) if n else 0.0
    return {
        "n": n,
        "wins": wins,
        "losses": n - wins,
        "win_rate_pct": round(wr, 2),
        "avg_r": round(avg_r, 4),
        "net_r": round(net_r, 4),
        "reliable": n >= min_sample,
    }


def _empty_buckets(labels):
    return OrderedDict((label, None) for label in labels)


class CalibrationEngine:
    """Analyze calibration without mutating stored signals."""

    def __init__(self, signals=None, min_sample=DEFAULT_MIN_SAMPLE):
        self.signals = list(load_signals() if signals is None else signals)
        self.min_sample = int(min_sample)

    def _resolved(self):
        return [s for s in self.signals if s.get("status") in RESOLVED_STATUSES]

    def _bucket_report(self, field, definitions, calibration=False):
        resolved = self._resolved()
        labels = [item[2] for item in definitions]
        buckets = _empty_buckets(labels)

        for label in labels:
            rows = []
            for signal in resolved:
                value = _number(signal.get(field))
                if value is None:
                    continue
                if _bucket(value, definitions) == label:
                    rows.append(signal)
            metrics = _row_metrics(rows, self.min_sample)
            if calibration and metrics["n"]:
                predicted = mean(
                    _number(row.get(field)) / 100.0
                    for row in rows
                    if _number(row.get(field)) is not None
                )
                observed = metrics["win_rate_pct"] / 100.0
                metrics["mean_predicted_pct"] = round(predicted * 100.0, 2)
                metrics["calibration_error_pct"] = round(
                    abs(predicted - observed) * 100.0, 2
                )
            buckets[label] = metrics if metrics["n"] else None
        return buckets

    def _grade_report(self):
        resolved = self._resolved()
        return OrderedDict(
            (
                grade,
                _row_metrics(
                    [s for s in resolved if str(s.get("grade", "")).upper() == grade],
                    self.min_sample,
                ),
            )
            for grade in GRADE_BUCKETS
        )

    def compute(self):
        resolved = self._resolved()
        expired = sum(1 for s in self.signals if s.get("status") == "EXPIRED")
        ai_rows = [s for s in resolved if _number(s.get("ai_rank_score")) is not None]
        confidence_rows = [s for s in resolved if _number(s.get("confidence")) is not None]

        return {
            "scope": {
                "total_signals": len(self.signals),
                "resolved_signals": len(resolved),
                "expired_signals": expired,
                "ai_calibration_samples": len(ai_rows),
                "confidence_calibration_samples": len(confidence_rows),
                "min_sample": self.min_sample,
                "note": "AI/confidence calibration excludes legacy rows without stored fields and EXPIRED outcomes.",
            },
            "ai_rank_score": self._bucket_report(
                "ai_rank_score", AI_SCORE_BUCKETS, calibration=False
            ),
            "confidence": self._bucket_report(
                "confidence", CONFIDENCE_BUCKETS, calibration=True
            ),
            "grade": self._grade_report(),
        }

    def summary(self):
        """Return compact machine-readable calibration conclusions."""
        report = self.compute()
        warnings = []
        if report["scope"]["ai_calibration_samples"] < self.min_sample:
            warnings.append("insufficient AI rank samples")
        if report["scope"]["confidence_calibration_samples"] < self.min_sample:
            warnings.append("insufficient confidence samples")

        reliable_ai = {
            label: data
            for label, data in report["ai_rank_score"].items()
            if data and data["reliable"]
        }
        reliable_confidence = {
            label: data
            for label, data in report["confidence"].items()
            if data and data["reliable"]
        }
        return {
            "report": report,
            "warnings": warnings,
            "reliable_ai_buckets": reliable_ai,
            "reliable_confidence_buckets": reliable_confidence,
            "ready_for_tuning": bool(reliable_ai and reliable_confidence),
        }


if __name__ == "__main__":
    import json

    print(json.dumps(CalibrationEngine().summary(), indent=2))
