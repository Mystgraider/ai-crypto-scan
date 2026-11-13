"""Research-only event-aligned SHORT quality audit.

The audit evaluates RRCE event-state features rather than fitting raw global
indicator thresholds. It also measures repeated scanner observations of the
same RRCE structural episode so row-level hit rates are not mistaken for
independent evidence.

No production scanner, LONG logic, risk engine, or SL/TP geometry is changed.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

OUT = Path("short_event_aligned_audit.json")
WINDOWS = (120, 90, 60, 30)
OUTCOMES = {"TP3_HIT", "SL_HIT", "EXPIRED"}


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def sl_distance(row):
    entry = num(row.get("entry"))
    stop = num(row.get("sl"))
    if entry is None or entry <= 0 or stop is None:
        return None
    return abs(stop - entry) / entry * 100.0


def episode_key(row):
    """Identify repeated scans belonging to one RRCE structural episode."""
    return (
        str(row.get("symbol") or ""),
        str(row.get("rrce_stage2_sweep_time") or ""),
        str(row.get("rrce_stage3_break_time") or ""),
        str(row.get("rrce_stage4_entry_zone") or ""),
    )


def event_features(row):
    width = num(row.get("rrce_stage1_range_width_pct"))
    sd = sl_distance(row)
    sweep = None
    pool = num(row.get("rrce_stage2_pool_level"))
    extreme = num(row.get("rrce_stage2_sweep_extreme"))
    if pool is not None and pool != 0 and extreme is not None:
        sweep = abs(extreme - pool) / abs(pool) * 100.0

    choch = None
    entry = num(row.get("entry"))
    choch_level = num(row.get("rrce_stage3_choch_level"))
    if entry is not None and entry != 0 and choch_level is not None:
        choch = abs(entry - choch_level) / abs(entry) * 100.0

    fvg = None
    fvg_bottom = num(row.get("rrce_stage3_fvg_bottom"))
    fvg_top = num(row.get("rrce_stage3_fvg_top"))
    if entry is not None and entry != 0 and fvg_bottom is not None and fvg_top is not None:
        fvg = abs(fvg_top - fvg_bottom) / abs(entry) * 100.0

    width_to_sl = width / sd if width is not None and sd not in (None, 0) else None

    return {
        "range_width_pct": width,
        "range_width_to_initial_sl": width_to_sl,
        "sweep_depth_pct": sweep,
        "choch_displacement_pct": choch,
        "fvg_width_pct": fvg,
        "premium_position_pct": num(row.get("rrce_stage1_position_pct")),
        "rsi_15m": num(row.get("rsi_15m")),
        "roc": num(row.get("roc")),
        "stoch_k_15m": num(row.get("stoch_k_15m")),
        "adx_15m": num(row.get("adx_15m")),
    }


def stats(rows):
    tp = sum(r.get("outcome") == "TP3_HIT" for r in rows)
    sl = sum(r.get("outcome") == "SL_HIT" for r in rows)
    expired = sum(r.get("outcome") == "EXPIRED" for r in rows)
    resolved = tp + sl
    distances = sorted(x for x in (sl_distance(r) for r in rows) if x is not None)
    p75 = distances[int(0.75 * (len(distances) - 1))] if distances else None
    return {
        "signals": len(rows),
        "tp3": tp,
        "sl": sl,
        "expired": expired,
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp / resolved, 3) if resolved else None,
        "median_sl_distance_pct": round(statistics.median(distances), 5) if distances else None,
        "p75_sl_distance_pct": round(p75, 5) if p75 is not None else None,
    }


def symbol_concentration(rows):
    tp_by_symbol = {}
    for symbol in sorted({str(r.get("symbol")) for r in rows if r.get("symbol")}):
        group = [r for r in rows if str(r.get("symbol")) == symbol]
        tp_by_symbol[symbol] = sum(r.get("outcome") == "TP3_HIT" for r in group)
    total_tp = sum(tp_by_symbol.values())
    largest = max(tp_by_symbol.values(), default=0)
    return {
        "symbol_count": len(tp_by_symbol),
        "largest_symbol_tp3_share_pct": round(100 * largest / total_tp, 2) if total_tp else 0.0,
        "tp3_by_symbol": tp_by_symbol,
    }


def episode_audit(rows):
    """Quantify dependence caused by repeated 5-minute observations."""
    groups = defaultdict(list)
    for row in rows:
        groups[episode_key(row)].append(row)

    episodes = []
    conflicts = 0
    for key, group in groups.items():
        ordered = sorted(group, key=lambda r: str(r.get("replay_time", "")))
        outcomes = {r.get("outcome") for r in ordered}
        if len(outcomes) > 1:
            conflicts += 1
        episodes.append(
            {
                "key": list(key),
                "symbol": ordered[0].get("symbol"),
                "rows": len(ordered),
                "first_outcome": ordered[0].get("outcome"),
                "any_tp3": "TP3_HIT" in outcomes,
                "outcomes": sorted(outcomes),
            }
        )

    n_rows = len(rows)
    n_episodes = len(episodes)
    sum_sq = sum(ep["rows"] ** 2 for ep in episodes)
    ess = (n_rows * n_rows / sum_sq) if sum_sq else 0.0

    first_resolved = [
        ep for ep in episodes if ep["first_outcome"] in {"TP3_HIT", "SL_HIT"}
    ]
    any_tp3 = [ep for ep in episodes if ep["any_tp3"]]
    first_tp3 = sum(ep["first_outcome"] == "TP3_HIT" for ep in first_resolved)
    any_tp3_count = sum(ep["any_tp3"] for ep in episodes)

    first_tp_by_symbol = defaultdict(int)
    any_tp_by_symbol = defaultdict(int)
    for ep in first_resolved:
        if ep["first_outcome"] == "TP3_HIT":
            first_tp_by_symbol[str(ep["symbol"])] += 1
    for ep in any_tp3:
        any_tp_by_symbol[str(ep["symbol"])] += 1

    def concentration(mapping):
        total = sum(mapping.values())
        return round(100 * max(mapping.values(), default=0) / total, 2) if total else 0.0

    return {
        "rows": n_rows,
        "independent_rrce_episodes": n_episodes,
        "mean_rows_per_episode": round(n_rows / n_episodes, 3) if n_episodes else 0.0,
        "max_rows_per_episode": max((ep["rows"] for ep in episodes), default=0),
        "effective_sample_size": round(ess, 3),
        "outcome_conflict_episode_count": conflicts,
        "first_entry_resolved_episodes": len(first_resolved),
        "first_entry_tp3_rate_pct": round(100 * first_tp3 / len(first_resolved), 3) if first_resolved else None,
        "episode_any_tp3_rate_pct": round(100 * any_tp3_count / n_episodes, 3) if n_episodes else None,
        "first_entry_tp3_symbol_concentration_pct": concentration(first_tp_by_symbol),
        "any_tp3_symbol_concentration_pct": concentration(any_tp_by_symbol),
        "episode_symbol_count": len({str(ep["symbol"]) for ep in episodes if ep["symbol"]}),
    }


def chronological_thirds(rows):
    ordered = sorted(rows, key=lambda r: str(r.get("replay_time", "")))
    n = len(ordered)
    out = {}
    for i, label in enumerate(("first", "middle", "last")):
        group = ordered[(i * n) // 3 : ((i + 1) * n) // 3]
        out[label] = stats(group)
    return out


def load(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        r for r in payload.get("results", [])
        if r.get("direction") == "SHORT"
        and r.get("outcome") in OUTCOMES
        and r.get("rrce_stage3_passed") is True
    ]
    if not rows:
        raise ValueError(f"{path}: no RRCE stage-3-passed SHORT rows")
    return rows


def candidate_predicates():
    return {
        "range_width_to_initial_sl_ge_5": lambda f: f["range_width_to_initial_sl"] is not None and f["range_width_to_initial_sl"] >= 5.0,
        "range_width_to_initial_sl_ge_6": lambda f: f["range_width_to_initial_sl"] is not None and f["range_width_to_initial_sl"] >= 6.0,
        "sweep_depth_le_0_15pct": lambda f: f["sweep_depth_pct"] is not None and f["sweep_depth_pct"] <= 0.15,
        "choch_displacement_le_0_40pct": lambda f: f["choch_displacement_pct"] is not None and f["choch_displacement_pct"] <= 0.40,
        "fvg_width_le_0_10pct": lambda f: f["fvg_width_pct"] is not None and f["fvg_width_pct"] <= 0.10,
    }


def evaluate(rows, predicate):
    return [row for row in rows if predicate(event_features(row))]


def candidate_report(all_windows):
    predicates = candidate_predicates()
    report = {}
    approvals = {}

    for name, predicate in predicates.items():
        windows = {}
        window_ok = True

        for w in WINDOWS:
            rows = all_windows[w]
            selected = evaluate(rows, predicate)
            base = stats(rows)
            quality = stats(selected)
            concentration = symbol_concentration(selected)
            dependence = episode_audit(selected)
            enough = (
                quality["resolved"] >= 20
                and concentration["symbol_count"] >= 3
                and concentration["largest_symbol_tp3_share_pct"] < 60.0
                and dependence["independent_rrce_episodes"] >= 20
                and dependence["episode_symbol_count"] >= 3
                and dependence["first_entry_tp3_symbol_concentration_pct"] < 60.0
            )
            improved = (
                quality["tp3_rate_pct"] is not None
                and base["tp3_rate_pct"] is not None
                and quality["tp3_rate_pct"] > base["tp3_rate_pct"]
            )
            geometry_ok = (
                quality["median_sl_distance_pct"] is not None
                and base["median_sl_distance_pct"] is not None
                and quality["median_sl_distance_pct"] <= base["median_sl_distance_pct"]
                and quality["p75_sl_distance_pct"] is not None
                and base["p75_sl_distance_pct"] is not None
                and quality["p75_sl_distance_pct"] <= base["p75_sl_distance_pct"]
            )
            passed = enough and improved and geometry_ok
            window_ok = window_ok and passed
            windows[str(w)] = {
                "baseline": base,
                "selected": quality,
                "retention_pct": round(100 * len(selected) / len(rows), 2),
                "symbol_concentration": concentration,
                "episode_dependence": dependence,
                "passes_window": passed,
                "chronological_thirds": chronological_thirds(selected),
            }

        approvals[name] = window_ok
        report[name] = {"windows": windows, "approved_for_research": window_ok}

    return report, approvals


def main(paths):
    if len(paths) != 4:
        raise SystemExit("Expected 120d, 90d, 60d, and 30d merged JSON paths")

    loaded = {}
    for path in paths:
        stem = Path(path).stem
        window = int(stem.rsplit("_", 1)[-1])
        loaded[window] = load(path)

    if set(loaded) != set(WINDOWS):
        raise SystemExit(f"Expected windows {WINDOWS}, got {sorted(loaded)}")

    candidates, approvals = candidate_report(loaded)
    fresh = {
        name: report["windows"]["30"]["passes_window"]
        for name, report in candidates.items()
    }
    approved = [
        name for name, ok in approvals.items()
        if ok and fresh.get(name) is True
    ]

    report = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "rrce_gate_changed": False,
        "decision": "APPROVED_FOR_FURTHER_RESEARCH_ONLY" if approved else "NO_CANDIDATE_APPROVED",
        "approved_candidates": approved,
        "method": {
            "population": "SHORT rows that reached RRCE stage 3 confirmation",
            "event_features": [
                "4H range width relative to initial SL distance",
                "1H sweep depth relative to swept pool",
                "15M CHOCH displacement relative to entry",
                "15M FVG width relative to entry",
            ],
            "fresh_window": "30d",
            "dependence_control": [
                "Repeated 5-minute scans are grouped by symbol + RRCE sweep time + CHOCH break time + execution zone.",
                "Row-level TP3 remains visible, but approval additionally requires at least 20 independent RRCE episodes.",
                "Episode first-entry and any-TP3 rates are reported separately.",
                "Mixed outcomes inside one structural episode are reported instead of silently deduplicated.",
            ],
            "approval_requirements": [
                "TP3 rate strictly improves in 120d, 90d, 60d, and fresh 30d",
                "median and P75 initial SL distance do not worsen in every window",
                "at least 20 resolved selected trades per window",
                "at least 3 symbols contribute selected trades",
                "no single symbol contributes 60% or more of selected TP3 outcomes",
                "at least 20 independent RRCE episodes per window",
                "no single symbol contributes 60% or more of first-entry episode TP3 outcomes",
            ],
        },
        "candidates": candidates,
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
