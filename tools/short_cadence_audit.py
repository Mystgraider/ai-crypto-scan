"""Research-only SHORT production-cadence / first-entry audit.

Purpose:
- Collapse repeated 5m observations of the same RRCE structural episode.
- Model the production 4-hour per-symbol signal cooldown as a deterministic
  replay proxy.
- Evaluate fixed, pre-specified structural hypotheses without retuning them.
- Keep production SHORT logic, LONG logic, RRCE gates, risk, and SL/TP geometry
  completely untouched.

This is diagnostic/research only. No candidate from this file is promoted.
"""
from __future__ import annotations

import json
import math
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUT = Path("short_cadence_audit.json")
WINDOWS = (120, 90, 60, 30)
OUTCOMES = {"TP3_HIT", "SL_HIT", "EXPIRED"}
COOLDOWN_HOURS = 4.0


def num(value):
    try:
        x = float(value)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def parse_time(value):
    if value is None:
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def sl_distance(row):
    entry = num(row.get("entry"))
    stop = num(row.get("sl"))
    if entry is None or entry <= 0 or stop is None:
        return None
    return abs(stop - entry) / entry * 100.0


def episode_key(row):
    return (
        str(row.get("symbol") or ""),
        str(row.get("rrce_stage2_sweep_time") or ""),
        str(row.get("rrce_stage3_break_time") or ""),
        str(row.get("rrce_stage4_entry_zone") or ""),
    )


def event_features(row):
    width = num(row.get("rrce_stage1_range_width_pct"))
    sd = sl_distance(row)

    pool = num(row.get("rrce_stage2_pool_level"))
    extreme = num(row.get("rrce_stage2_sweep_extreme"))
    sweep = (
        abs(extreme - pool) / abs(pool) * 100.0
        if pool not in (None, 0) and extreme is not None
        else None
    )

    entry = num(row.get("entry"))
    choch_level = num(row.get("rrce_stage3_choch_level"))
    choch = (
        abs(entry - choch_level) / abs(entry) * 100.0
        if entry not in (None, 0) and choch_level is not None
        else None
    )

    fvg_bottom = num(row.get("rrce_stage3_fvg_bottom"))
    fvg_top = num(row.get("rrce_stage3_fvg_top"))
    fvg = (
        abs(fvg_top - fvg_bottom) / abs(entry) * 100.0
        if entry not in (None, 0) and fvg_bottom is not None and fvg_top is not None
        else None
    )

    return {
        "range_width_pct": width,
        "range_width_to_initial_sl": width / sd if width is not None and sd not in (None, 0) else None,
        "sweep_depth_pct": sweep,
        "choch_displacement_pct": choch,
        "fvg_width_pct": fvg,
        "premium_position_pct": num(row.get("rrce_stage1_position_pct")),
        "rsi_15m": num(row.get("rsi_15m")),
        "adx_15m": num(row.get("adx_15m")),
        "macd_hist_15m": num(row.get("macd_hist_15m")),
        "roc": num(row.get("roc")),
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


def episode_first(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[episode_key(row)].append(row)

    selected = []
    episode_sizes = []
    for group in groups.values():
        ordered = sorted(
            group,
            key=lambda r: (
                parse_time(r.get("replay_time")) or datetime.max.replace(tzinfo=timezone.utc),
                str(r.get("replay_time", "")),
            ),
        )
        if ordered:
            selected.append(ordered[0])
            episode_sizes.append(len(ordered))

    return sorted(
        selected,
        key=lambda r: parse_time(r.get("replay_time"))
        or datetime.max.replace(tzinfo=timezone.utc),
    ), episode_sizes


def cooldown_first(rows):
    """Apply the production per-symbol 4-hour cooldown to episode-first rows."""
    first_rows, episode_sizes = episode_first(rows)
    last_accepted = {}
    accepted = []
    suppressed = 0

    for row in first_rows:
        symbol = str(row.get("symbol") or "")
        timestamp = parse_time(row.get("replay_time"))
        if not symbol or timestamp is None:
            continue
        previous = last_accepted.get(symbol)
        if previous is not None and timestamp < previous + timedelta(hours=COOLDOWN_HOURS):
            suppressed += 1
            continue
        accepted.append(row)
        last_accepted[symbol] = timestamp

    return accepted, {
        "episode_count": len(first_rows),
        "episode_size_mean": round(statistics.mean(episode_sizes), 3) if episode_sizes else 0.0,
        "episode_size_max": max(episode_sizes, default=0),
        "cooldown_accepted": len(accepted),
        "cooldown_suppressed": suppressed,
        "cooldown_hours": COOLDOWN_HOURS,
    }


def symbol_concentration(rows):
    tp_by_symbol = defaultdict(int)
    for row in rows:
        if row.get("outcome") == "TP3_HIT":
            tp_by_symbol[str(row.get("symbol") or "MISSING")] += 1
    total = sum(tp_by_symbol.values())
    largest = max(tp_by_symbol.values(), default=0)
    return {
        "symbol_count": len({str(r.get("symbol") or "MISSING") for r in rows}),
        "tp3_by_symbol": dict(sorted(tp_by_symbol.items())),
        "largest_symbol_tp3_share_pct": round(100 * largest / total, 2) if total else 0.0,
    }


def chronological_thirds(rows):
    ordered = sorted(
        rows,
        key=lambda r: parse_time(r.get("replay_time"))
        or datetime.max.replace(tzinfo=timezone.utc),
    )
    n = len(ordered)
    out = {}
    for i, label in enumerate(("first", "middle", "last")):
        group = ordered[(i * n) // 3 : ((i + 1) * n) // 3]
        out[label] = stats(group)
    return out


def candidate_predicates():
    # Frozen hypotheses from the preceding event-aligned audit. No threshold
    # is selected from this audit's outcomes.
    return {
        "range_width_to_initial_sl_ge_5": lambda f: f["range_width_to_initial_sl"] is not None and f["range_width_to_initial_sl"] >= 5.0,
        "range_width_to_initial_sl_ge_6": lambda f: f["range_width_to_initial_sl"] is not None and f["range_width_to_initial_sl"] >= 6.0,
        "sweep_depth_le_0_15pct": lambda f: f["sweep_depth_pct"] is not None and f["sweep_depth_pct"] <= 0.15,
        "choch_displacement_le_0_40pct": lambda f: f["choch_displacement_pct"] is not None and f["choch_displacement_pct"] <= 0.40,
        "fvg_width_le_0_10pct": lambda f: f["fvg_width_pct"] is not None and f["fvg_width_pct"] <= 0.10,
    }


def evaluate(rows, predicate):
    return [row for row in rows if predicate(event_features(row))]


def cohort_report(rows, label):
    predicates = candidate_predicates()
    base = stats(rows)
    report = {
        "label": label,
        "base": base,
        "symbol_concentration": symbol_concentration(rows),
        "chronological_thirds": chronological_thirds(rows),
        "candidates": {},
    }

    for name, predicate in predicates.items():
        selected = evaluate(rows, predicate)
        quality = stats(selected)
        report["candidates"][name] = {
            "selected": quality,
            "retention_pct": round(100 * len(selected) / len(rows), 2) if rows else 0.0,
            "symbol_concentration": symbol_concentration(selected),
            "chronological_thirds": chronological_thirds(selected),
            "tp3_delta_pp": (
                round(quality["tp3_rate_pct"] - base["tp3_rate_pct"], 3)
                if quality["tp3_rate_pct"] is not None and base["tp3_rate_pct"] is not None
                else None
            ),
            "sl_median_delta_pct": (
                round(quality["median_sl_distance_pct"] - base["median_sl_distance_pct"], 5)
                if quality["median_sl_distance_pct"] is not None and base["median_sl_distance_pct"] is not None
                else None
            ),
            "sl_p75_delta_pct": (
                round(quality["p75_sl_distance_pct"] - base["p75_sl_distance_pct"], 5)
                if quality["p75_sl_distance_pct"] is not None and base["p75_sl_distance_pct"] is not None
                else None
            ),
        }
    return report


def load(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        r
        for r in payload.get("results", [])
        if r.get("direction") == "SHORT"
        and r.get("outcome") in OUTCOMES
        and r.get("rrce_stage3_passed") is True
    ]
    if not rows:
        raise ValueError(f"{path}: no RRCE stage-3-passed SHORT rows")
    return rows


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

    windows = {}
    for window in WINDOWS:
        rows = loaded[window]
        first, episode_meta = episode_first(rows)
        cooldown, cooldown_meta = cooldown_first(rows)
        windows[str(window)] = {
            "raw_stage3_population": stats(rows),
            "episode_first": cohort_report(first, "first_actionable_rrce_episode_entry"),
            "cooldown_first": cohort_report(cooldown, "first_actionable_entry_after_4h_symbol_cooldown"),
            "episode_meta": episode_meta,
            "cooldown_meta": cooldown_meta,
        }

    report = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "rrce_gate_changed": False,
        "decision": "DIAGNOSTIC_ONLY_NO_CANDIDATE_PROMOTED",
        "method": {
            "population": "SHORT rows reaching RRCE stage 3 with resolved/expired outcomes",
            "episode_first": "Keep the earliest replay observation for each symbol + sweep time + CHOCH break time + execution zone.",
            "production_cadence_proxy": "From episode-first entries, accept the first entry per symbol and suppress later entries for 4 hours, matching CONFIG signal_cooldown_hours.",
            "candidate_thresholds": "Frozen from the preceding event-aligned audit; no threshold tuning occurs here.",
            "fresh_window": "30d",
        },
        "windows": windows,
        "interpretation_rules": [
            "Row-level TP3 rates are not treated as independent evidence.",
            "Episode-first is the primary structural unit for setup quality.",
            "Cooldown-first is the closer replay proxy for production signal cadence.",
            "A candidate is not approved by this audit, especially when the fresh window has fewer than 20 independent episodes.",
            "Mixed outcomes remain visible; this audit does not convert any-TP3 into a trade success.",
        ],
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main(sys.argv[1:])
