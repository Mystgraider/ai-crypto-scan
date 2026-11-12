"""Research-only SHORT RRCE/indicator quality ranker.

Weights are learned only from the discovery portions of the 120d/90d/60d
windows. A fresh 30d window is never used to fit weights or thresholds.
The score is a ranking aid, not a production gate. A fixed moderate penalty
for planned entry-to-SL distance keeps the quality layer aligned with the
existing RRCE execution geometry without changing SL/TP itself.
"""
from __future__ import annotations

import bisect
import json
import math
import statistics
import sys
from pathlib import Path

FEATURES = {
    "adx_4h": "adx_4h",
    "macd_hist_15m": "macd_hist_15m",
    "macd_hist_1h": "macd_hist",
    "support_distance_pct": "support_distance_pct",
}
DISCOVERY_PATHS = {"short_window_120", "short_window_90", "short_window_60"}
SL_PENALTY_WEIGHT = 0.30
MIN_PAIRS = 80


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def auc(rows, field):
    pos = [num(r.get(field)) for r in rows if r.get("outcome") == "TP3_HIT"]
    neg = [num(r.get(field)) for r in rows if r.get("outcome") == "SL_HIT"]
    pos = [x for x in pos if x is not None]
    neg = [x for x in neg if x is not None]
    if not pos or not neg or len(pos) * len(neg) < MIN_PAIRS:
        return None
    wins = sum(1.0 if p > n else 0.5 if p == n else 0.0 for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def percentile(ref, value):
    if not ref:
        return None
    i = bisect.bisect_left(ref, value)
    return i / (len(ref) - 1) if len(ref) > 1 else 0.5


def sl_distance(row):
    entry = num(row.get("entry"))
    stop = num(row.get("sl"))
    if entry is None or entry <= 0 or stop is None:
        return None
    return abs(stop - entry) / entry * 100.0


def stats(rows):
    tp3 = sum(r.get("outcome") == "TP3_HIT" for r in rows)
    sl = sum(r.get("outcome") == "SL_HIT" for r in rows)
    expired = sum(r.get("outcome") == "EXPIRED" for r in rows)
    resolved = tp3 + sl
    distances = sorted(x for x in (sl_distance(r) for r in rows) if x is not None)
    p75 = distances[int(0.75 * (len(distances) - 1))] if distances else None
    return {
        "signals": len(rows),
        "tp3": tp3,
        "sl": sl,
        "expired": expired,
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
        "median_sl_distance_pct": round(statistics.median(distances), 5) if distances else None,
        "p75_sl_distance_pct": round(p75, 5) if p75 is not None else None,
    }


def load(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        r for r in payload.get("results", [])
        if r.get("direction") == "SHORT"
        and r.get("outcome") in {"TP3_HIT", "SL_HIT", "EXPIRED"}
    ]
    rows.sort(key=lambda r: str(r.get("replay_time", "")))
    if len(rows) < 3:
        raise ValueError(f"{path}: insufficient rows")
    split = max(1, min(len(rows) - 1, (len(rows) * 2) // 3))
    return Path(path).stem, rows, rows[:split], rows[split:]


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
    for name, values in by_feature.items():
        if not values or medians[name] is None:
            continue
        directions = {1 if value >= 0.5 else -1 for value in values}
        if len(directions) != 1:
            continue
        strength = abs(medians[name] - 0.5)
        usable.append((name, directions.pop(), strength))

    total = sum(strength for _, _, strength in usable)
    if total == 0:
        return {}, medians, by_feature
    weights = {
        name: direction * strength / total
        for name, direction, strength in usable
    }
    return weights, medians, by_feature


def references(rows):
    refs = {
        name: sorted(
            num(r.get(field))
            for r in rows
            if num(r.get(field)) is not None
        )
        for name, field in FEATURES.items()
    }
    sl_ref = sorted(x for x in (sl_distance(r) for r in rows) if x is not None)
    return refs, sl_ref


def score_rows(rows, weights, feature_refs, sl_ref):
    scored = []
    for row in rows:
        contributions = []
        complete = True
        for name, weight in weights.items():
            value = num(row.get(FEATURES[name]))
            ref = feature_refs[name]
            if value is None or not ref:
                complete = False
                break
            contributions.append(weight * (percentile(ref, value) - 0.5))
        distance = sl_distance(row)
        if not complete or distance is None or not sl_ref:
            continue
        sl_penalty = SL_PENALTY_WEIGHT * percentile(sl_ref, distance)
        copy = dict(row)
        copy["research_short_quality_score_v2"] = round(
            sum(contributions) - sl_penalty, 8
        )
        copy["research_short_quality_indicator_component"] = round(
            sum(contributions), 8
        )
        copy["research_short_quality_sl_penalty"] = round(sl_penalty, 8)
        scored.append(copy)
    return scored


def evaluate_bucket(scored, threshold):
    selected = [r for r in scored if r["research_short_quality_score_v2"] >= threshold]
    return selected


def main(paths):
    loaded = [load(path) for path in paths]
    discovery_rows = [
        discovery
        for name, rows, discovery, holdout in loaded
        if name in DISCOVERY_PATHS
    ]
    if len(discovery_rows) != 3:
        raise SystemExit("Expected exactly 120d, 90d, and 60d discovery windows")

    weights, auc_medians, auc_by_window = derive_weights(discovery_rows)
    pooled_discovery = [r for rows in discovery_rows for r in rows]
    feature_refs, sl_ref = references(pooled_discovery)
    scored_discovery = score_rows(pooled_discovery, weights, feature_refs, sl_ref)
    if not scored_discovery:
        raise SystemExit("No discovery rows could be scored")
    threshold = statistics.median(
        r["research_short_quality_score_v2"] for r in scored_discovery
    )

    report = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "rrce_gate_changed": False,
        "decision": "NOT_VALIDATED",
        "method": {
            "description": "Frozen RRCE-aligned indicator ranking with a fixed moderate planned-SL penalty.",
            "features": FEATURES,
            "sl_penalty_weight": SL_PENALTY_WEIGHT,
            "selection_rule": "top half by frozen score; threshold is the pooled discovery median.",
            "weights_fit_only_from": ["120d discovery", "90d discovery", "60d discovery"],
            "fresh_validation_window": "30d",
        },
        "discovery_auc_median": auc_medians,
        "discovery_auc_by_window": auc_by_window,
        "derived_weights": weights,
        "pooled_discovery_threshold": threshold,
        "windows": {},
    }

    approvals = {}
    for name, rows, discovery, holdout in loaded:
        scored_holdout = score_rows(holdout, weights, feature_refs, sl_ref)
        selected = evaluate_bucket(scored_holdout, threshold)
        base = stats(holdout)
        quality = stats(selected)
        approval = (
            quality["tp3_rate_pct"] is not None
            and base["tp3_rate_pct"] is not None
            and quality["tp3_rate_pct"] > base["tp3_rate_pct"]
            and quality["median_sl_distance_pct"] is not None
            and base["median_sl_distance_pct"] is not None
            and quality["median_sl_distance_pct"] <= base["median_sl_distance_pct"]
            and quality["p75_sl_distance_pct"] is not None
            and base["p75_sl_distance_pct"] is not None
            and quality["p75_sl_distance_pct"] <= base["p75_sl_distance_pct"]
        )
        approvals[name] = approval
        report["windows"][name] = {
            "role": "fresh_validation" if name == "short_window_30" else "historical_holdout_check",
            "holdout": base,
            "scored": len(scored_holdout),
            "score_coverage_pct": round(100 * len(scored_holdout) / len(holdout), 2),
            "selected": quality,
            "selected_retention_pct": round(100 * len(selected) / len(holdout), 2),
            "approval_check": approval,
        }

    report["approval_checks"] = approvals
    report["decision"] = (
        "APPROVED_FOR_FURTHER_RESEARCH_ONLY"
        if approvals.get("short_window_30") is True
        and all(approvals.get(name) is True for name in ("short_window_120", "short_window_90", "short_window_60"))
        else "NOT_VALIDATED"
    )
    Path("short_quality_score_v2.json").write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(
            "usage: python tools/short_quality_score_v2.py "
            "merged/short_window_120.json merged/short_window_90.json "
            "merged/short_window_60.json merged/short_window_30.json"
        )
    main(sys.argv[1:])
