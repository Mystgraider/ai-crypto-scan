"""Research-only SHORT quality score.

Learns indicator directions and weights only from the discovery segment of
chronological holdout windows, freezes them, then evaluates the untouched
final segment. It never changes scanner production logic.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from pathlib import Path

FEATURES = {
    "range_width_4h": "rrce_stage1_range_width_pct",
    "adx_4h": "adx_4h",
    "macd_hist_15m": "macd_hist_15m",
    "macd_hist_1h": "macd_hist",
    "roc_1h": "roc",
    "atr_pct": "atr_pct",
    "support_distance_pct": "support_distance_pct",
    "rsi_1h": "rsi",
}
MIN_PAIRS = 80


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def auc(rows, field):
    pairs = [
        (num(row.get(field)), row.get("outcome"))
        for row in rows
        if row.get("outcome") in {"TP3_HIT", "SL_HIT"}
    ]
    pairs = [(value, outcome) for value, outcome in pairs if value is not None]
    positive = [value for value, outcome in pairs if outcome == "TP3_HIT"]
    negative = [value for value, outcome in pairs if outcome == "SL_HIT"]
    if not positive or not negative or len(positive) * len(negative) < MIN_PAIRS:
        return None
    wins = 0.0
    for pos in positive:
        wins += sum(1.0 for neg in negative if pos > neg)
        wins += 0.5 * sum(1.0 for neg in negative if pos == neg)
    return wins / (len(positive) * len(negative))


def percentile(values, value):
    ordered = sorted(values)
    if not ordered:
        return None
    if value <= ordered[0]:
        return 0.0
    if value >= ordered[-1]:
        return 1.0
    lo, hi = 0, len(ordered) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if ordered[mid] < value:
            lo = mid + 1
        else:
            hi = mid - 1
    return lo / (len(ordered) - 1)


def stats(rows):
    tp3 = sum(row.get("outcome") == "TP3_HIT" for row in rows)
    sl = sum(row.get("outcome") == "SL_HIT" for row in rows)
    expired = sum(row.get("outcome") == "EXPIRED" for row in rows)
    resolved = tp3 + sl
    sl_distances = []
    for row in rows:
        entry = num(row.get("entry"))
        stop = num(row.get("sl"))
        if entry and entry > 0 and stop is not None:
            sl_distances.append(abs(stop - entry) / entry * 100)
    sl_distances.sort()
    p75 = None
    if sl_distances:
        p75 = sl_distances[int(0.75 * (len(sl_distances) - 1))]
    return {
        "signals": len(rows),
        "tp3": tp3,
        "sl": sl,
        "expired": expired,
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
        "median_sl_distance_pct": round(statistics.median(sl_distances), 5) if sl_distances else None,
        "p75_sl_distance_pct": round(p75, 5) if p75 is not None else None,
    }


def derive_weights(discovery_windows):
    by_feature = {name: [] for name in FEATURES}
    for rows in discovery_windows:
        for name, field in FEATURES.items():
            value = auc(rows, field)
            if value is not None:
                by_feature[name].append(value)

    medians = {
        name: statistics.median(values) if values else None
        for name, values in by_feature.items()
    }
    usable = []
    for name, value in medians.items():
        if value is None:
            continue
        direction = 1 if value >= 0.5 else -1
        strength = abs(value - 0.5)
        usable.append((name, direction, strength))

    total_strength = sum(strength for _, _, strength in usable)
    if not total_strength:
        return {}, medians, by_feature

    weights = {
        name: direction * strength / total_strength
        for name, direction, strength in usable
    }
    return weights, medians, by_feature


def score_rows(rows, weights, reference_rows):
    references = {
        name: sorted(
            value
            for row in reference_rows
            if (value := num(row.get(field))) is not None
        )
        for name, field in FEATURES.items()
    }
    scored = []
    for row in rows:
        contributions = []
        complete = True
        for name, weight in weights.items():
            value = num(row.get(FEATURES[name]))
            reference = references[name]
            if value is None or not reference:
                complete = False
                break
            rank = percentile(reference, value)
            contributions.append(weight * (rank - 0.5))
        if complete:
            copy = dict(row)
            copy["research_short_quality_score"] = round(sum(contributions), 8)
            scored.append(copy)
    return scored


def load_window(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        row
        for row in payload.get("results", [])
        if row.get("direction") == "SHORT"
        and row.get("outcome") in {"TP3_HIT", "SL_HIT", "EXPIRED"}
    ]
    rows.sort(key=lambda row: row.get("replay_time", ""))
    if len(rows) < 2:
        raise ValueError(f"{path}: insufficient SHORT rows for chronological split")
    split = max(1, min(len(rows) - 1, (len(rows) * 2) // 3))
    return Path(path).stem, rows, rows[:split], rows[split:]


def main(paths):
    windows = [load_window(path) for path in paths]
    weights, auc_medians, auc_by_window = derive_weights(
        [discovery for _, _, discovery, _ in windows]
    )

    report = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "feature_roles": {
            "range_width_4h": "structural room/location proxy",
            "adx_4h": "higher-timeframe trend-strength context",
            "macd_hist_15m": "entry confirmation",
            "macd_hist_1h": "entry momentum",
            "roc_1h": "directional momentum",
            "atr_pct": "volatility quality context",
            "support_distance_pct": "downside room context",
            "rsi_1h": "momentum context",
        },
        "discovery_auc_median": auc_medians,
        "discovery_auc_by_window": auc_by_window,
        "derived_weights": weights,
        "windows": {},
    }

    approval_checks = {}
    for name, rows, discovery, holdout in windows:
        scored_discovery = score_rows(discovery, weights, discovery)
        scored_holdout = score_rows(holdout, weights, discovery)
        discovery_scores = [
            row["research_short_quality_score"] for row in scored_discovery
        ]
        threshold = statistics.median(discovery_scores) if discovery_scores else None
        selected = (
            [row for row in scored_holdout if row["research_short_quality_score"] >= threshold]
            if threshold is not None
            else []
        )

        base = stats(holdout)
        quality = stats(selected)
        approval = (
            quality["tp3_rate_pct"] is not None
            and base["tp3_rate_pct"] is not None
            and quality["tp3_rate_pct"] > base["tp3_rate_pct"]
            and (
                quality["median_sl_distance_pct"] is None
                or base["median_sl_distance_pct"] is None
                or quality["median_sl_distance_pct"] <= base["median_sl_distance_pct"]
            )
            and (
                quality["p75_sl_distance_pct"] is None
                or base["p75_sl_distance_pct"] is None
                or quality["p75_sl_distance_pct"] <= base["p75_sl_distance_pct"]
            )
        )
        approval_checks[name] = approval
        report["windows"][name] = {
            "discovery": stats(discovery),
            "holdout": base,
            "scored_holdout": len(scored_holdout),
            "holdout_score_coverage_pct": round(
                100 * len(scored_holdout) / len(holdout), 2
            ),
            "score_threshold_from_discovery_median": threshold,
            "holdout_quality_bucket": quality,
            "holdout_quality_bucket_signal_retention_pct": round(
                100 * len(selected) / len(holdout), 2
            ),
        }

    report["approval_checks_by_window"] = approval_checks
    report["decision"] = (
        "APPROVED_FOR_FURTHER_RESEARCH_ONLY"
        if approval_checks and all(approval_checks.values())
        else "NOT_VALIDATED"
    )
    Path("short_quality_score.json").write_text(
        json.dumps(report, indent=2, default=str),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(
            "usage: python tools/short_quality_score.py "
            "merged/short_window_120.json merged/short_window_90.json merged/short_window_60.json"
        )
    main(sys.argv[1:])
