"""Research-only pooled SHORT setup audit across independent chronological windows.

This module never changes production strategy, LONG logic, risk geometry, or SL/TP.
It consumes merged backtest_results.json files and evaluates fixed, pre-declared
candidate setups without threshold fitting on the evaluation windows.
"""
from __future__ import annotations

import collections
import json
import math
import sys
from pathlib import Path
from statistics import median


def num(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None


def stats(rows):
    c = collections.Counter(r.get("outcome", "UNKNOWN") for r in rows)
    tp = c["TP3_HIT"]
    sl = c["SL_HIT"]
    resolved = tp + sl
    return {
        "signals": len(rows),
        "tp3": tp,
        "sl": sl,
        "expired": c["EXPIRED"],
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp / resolved, 2) if resolved else None,
        "sl_rate_pct": round(100 * sl / resolved, 2) if resolved else None,
        "median_sl_distance_pct": _median_distance(rows, "sl"),
        "median_tp3_distance_pct": _median_distance(rows, "tp3"),
    }


def _median_distance(rows, field):
    values = []
    for r in rows:
        e = num(r.get("entry"))
        p = num(r.get(field))
        if e is not None and p is not None and e > 0:
            values.append(abs(p - e) / e * 100)
    return round(median(values), 4) if values else None


def by_symbol(rows):
    return {
        s: stats([r for r in rows if r.get("symbol") == s])
        for s in sorted({r.get("symbol") for r in rows if r.get("symbol")})
    }


def thirds(rows):
    ordered = sorted(
        [r for r in rows if r.get("replay_time")],
        key=lambda r: r["replay_time"],
    )
    if not ordered:
        return {}
    n = len(ordered)
    cuts = [0, n // 3, (2 * n) // 3, n]
    out = {}
    for label, a, b in zip(("first", "middle", "last"), cuts, cuts[1:]):
        part = ordered[a:b]
        out[label] = {
            "start": part[0]["replay_time"],
            "end": part[-1]["replay_time"],
            **stats(part),
        }
    return out


def field(row, name):
    return num(row.get(name))


def has_rrce_position(row):
    p = field(row, "rrce_stage1_position_pct")
    return p is not None and 0 <= p <= 100


def rrce_sweep(row):
    return row.get("rrce_stage2_passed") is True


def candidates():
    # These are fixed research hypotheses. They are deliberately not selected
    # by optimizing against the current evaluation window.
    return {
        "C0_baseline": lambda r: True,
        "C1_4h_mid_upper_40_80": lambda r:
            has_rrce_position(r) and 40 <= field(r, "rrce_stage1_position_pct") < 80,
        "C2_4h_40_80_plus_1h_sweep": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and rrce_sweep(r),
        "C3_C2_plus_rsi_60_70": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and rrce_sweep(r)
            and field(r, "rsi") is not None
            and 60 <= field(r, "rsi") <= 70,
        "C4_C3_plus_support_lt_1": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and rrce_sweep(r)
            and field(r, "rsi") is not None
            and 60 <= field(r, "rsi") <= 70
            and field(r, "support_distance_pct") is not None
            and field(r, "support_distance_pct") < 1,
        "C5_4h_40_80_plus_support_lt_1": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and field(r, "support_distance_pct") is not None
            and field(r, "support_distance_pct") < 1,
        "C6_4h_40_80_plus_rsi_60_70": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and field(r, "rsi") is not None
            and 60 <= field(r, "rsi") <= 70,
        "C7_4h_40_80_plus_sweep_plus_not_bearish_di": lambda r:
            has_rrce_position(r)
            and 40 <= field(r, "rrce_stage1_position_pct") < 80
            and rrce_sweep(r)
            and field(r, "plus_di") is not None
            and field(r, "minus_di") is not None
            and field(r, "minus_di") <= field(r, "plus_di"),
    }


def concentration(rows):
    s = stats(rows)
    if not s["tp3"]:
        return {"largest_symbol_tp3_share_pct": None, "symbols_with_tp3": 0}
    shares = []
    for symbol, item in by_symbol(rows).items():
        if item["tp3"]:
            shares.append(100 * item["tp3"] / s["tp3"])
    return {
        "largest_symbol_tp3_share_pct": round(max(shares), 2) if shares else None,
        "symbols_with_tp3": len(shares),
    }


def load(path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = [
        r for r in payload.get("results", [])
        if r.get("direction") == "SHORT"
    ]
    if not rows:
        raise ValueError(f"{path}: no SHORT rows")
    return payload, rows


def main():
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        raise SystemExit("usage: python tools/pooled_short_setup_audit.py <merged.json> [merged.json ...]")

    windows = []
    all_rows = []
    for p in paths:
        payload, rows = load(p)
        meta = payload.get("metadata", {})
        windows.append({
            "file": str(p),
            "start": meta.get("start"),
            "end": meta.get("end"),
            "offset_days": meta.get("offset_days"),
            "signals": len(rows),
            "stats": stats(rows),
        })
        all_rows.extend(rows)

    # De-duplicate only exact replay identity; conflicting duplicate timestamps
    # are rejected because they indicate a broken merge/window definition.
    keyed = {}
    for r in all_rows:
        key = (
            r.get("symbol"),
            r.get("direction"),
            r.get("replay_time"),
            r.get("entry"),
        )
        if key in keyed and keyed[key] != r:
            raise ValueError(f"conflicting duplicate replay row: {key}")
        keyed[key] = r
    rows = list(keyed.values())

    report = {}
    for name, predicate in candidates().items():
        selected = [r for r in rows if predicate(r)]
        report[name] = {
            "pooled": stats(selected),
            "pooled_concentration": concentration(selected),
            "by_window": [],
            "by_symbol": by_symbol(selected),
            "by_third": thirds(selected),
        }
        for w in windows:
            _, wr = load(w["file"])
            picked = [r for r in wr if predicate(r)]
            report[name]["by_window"].append({
                "file": w["file"],
                "offset_days": w["offset_days"],
                "stats": stats(picked),
                "concentration": concentration(picked),
            })

    # Promotion is intentionally conservative. A candidate must have usable
    # samples in every independent window, TP3 in every window, and no single
    # symbol responsible for >60% of TP3 in any window.
    decisions = {}
    for name, item in report.items():
        if name == "C0_baseline":
            continue
        ok = True
        reasons = []
        for w in item["by_window"]:
            s = w["stats"]
            c = w["concentration"]
            if s["signals"] < 20:
                ok = False
                reasons.append(f"{w['offset_days']}d:signals<{20}")
            if not s["tp3"]:
                ok = False
                reasons.append(f"{w['offset_days']}d:no_tp3")
            if c["largest_symbol_tp3_share_pct"] is not None and c["largest_symbol_tp3_share_pct"] >= 60:
                ok = False
                reasons.append(f"{w['offset_days']}d:tp3_concentration>=60%")
        decisions[name] = {
            "passes_cross_window_stability": ok,
            "reasons": reasons,
        }

    approved = [
        name for name, d in decisions.items()
        if d["passes_cross_window_stability"]
    ]

    summary = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_changed": False,
        "risk_geometry_changed": False,
        "sl_tp_changed": False,
        "rrce_gate_changed": False,
        "windows": windows,
        "pooled_baseline": stats(rows),
        "candidates": report,
        "decisions": decisions,
        "approved_candidates": approved,
        "decision": (
            "APPROVE FOR NEXT-STEP VALIDATION ONLY: " + ", ".join(approved)
            if approved else
            "NO CANDIDATE PASSES CROSS-WINDOW STABILITY. Keep production unchanged."
        ),
    }
    print(json.dumps(summary, indent=2))
    out = Path("pooled_short_setup_audit.json")
    out.write_text(json.dumps(summary, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
