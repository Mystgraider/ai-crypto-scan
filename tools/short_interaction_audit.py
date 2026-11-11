"""Research-only SHORT interaction audit.

Evaluates fixed indicator/structure interactions across the three independent
30-day chronological windows. It does not modify production strategy, LONG,
risk, SL/TP geometry, or thresholds.
"""
from __future__ import annotations
import json, math
from pathlib import Path

WINDOWS = (120, 90, 60)
BASE = Path("merged")
OUT = Path("pooled_short_interaction_audit.json")

def f(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def stats(rows):
    tp = sum(r.get("outcome") == "TP3_HIT" for r in rows)
    sl = sum(r.get("outcome") == "SL_HIT" for r in rows)
    ex = sum(r.get("outcome") == "EXPIRED" for r in rows)
    resolved = tp + sl
    sl_dist = []
    for r in rows:
        if r.get("outcome") != "SL_HIT":
            continue
        e, s = f(r.get("entry")), f(r.get("sl"))
        if e and e > 0 and s is not None:
            sl_dist.append(abs(s-e)/e*100)
    return {
        "signals": len(rows), "tp3": tp, "sl": sl, "expired": ex,
        "resolved": resolved,
        "tp3_rate_pct": round(100*tp/resolved, 2) if resolved else None,
        "median_sl_distance_pct": round(sorted(sl_dist)[len(sl_dist)//2], 5) if sl_dist else None,
    }

def val(r, key):
    return f(r.get(key))

def conditions(r):
    adx, rsi, sup = val(r,"adx"), val(r,"rsi"), val(r,"support_distance_pct")
    pos = val(r,"rrce_stage1_position_pct")
    plus, minus = val(r,"plus_di"), val(r,"minus_di")
    sweep = str(r.get("rrce_stage2_passed")).lower() == "true"
    return {
        "ADX_10_15": adx is not None and 10 <= adx < 15,
        "ADX_10_15_RSI_50_60": adx is not None and rsi is not None and 10 <= adx < 15 and 50 <= rsi < 60,
        "ADX_10_15_RSI_55_65": adx is not None and rsi is not None and 10 <= adx < 15 and 55 <= rsi < 65,
        "ADX_10_15_RSI_60_65": adx is not None and rsi is not None and 10 <= adx < 15 and 60 <= rsi < 65,
        "ADX_10_15_SUPPORT_LT1": adx is not None and sup is not None and 10 <= adx < 15 and sup < 1,
        "ADX_10_15_SUPPORT_1_2": adx is not None and sup is not None and 10 <= adx < 15 and 1 <= sup < 2,
        "ADX_10_15_NOT_BEARISH_DI": adx is not None and plus is not None and minus is not None and 10 <= adx < 15 and minus <= plus,
        "ADX_10_15_4H_40_80": adx is not None and pos is not None and 10 <= adx < 15 and 40 <= pos < 80,
        "ADX_10_15_4H_40_80_SUPPORT_LT1": adx is not None and pos is not None and sup is not None and 10 <= adx < 15 and 40 <= pos < 80 and sup < 1,
        "ADX_10_15_4H_40_80_RSI_50_60": adx is not None and pos is not None and rsi is not None and 10 <= adx < 15 and 40 <= pos < 80 and 50 <= rsi < 60,
        "ADX_10_15_4H_40_80_RSI_60_65": adx is not None and pos is not None and rsi is not None and 10 <= adx < 15 and 40 <= pos < 80 and 60 <= rsi < 65,
        "ADX_10_15_4H_40_80_SWEEP": adx is not None and pos is not None and 10 <= adx < 15 and 40 <= pos < 80 and sweep,
        "ADX_10_15_RSI_50_60_SUPPORT_LT1": adx is not None and rsi is not None and sup is not None and 10 <= adx < 15 and 50 <= rsi < 60 and sup < 1,
    }

def run():
    windows = {}
    for w in WINDOWS:
        data = json.loads((BASE / f"short_window_{w}.json").read_text())
        rows = [r for r in data.get("results", []) if r.get("direction") == "SHORT"]
        windows[w] = rows

    baseline = {str(w): stats(rows) for w, rows in windows.items()}
    candidates = {}
    for name in next(iter(conditions(r) for r in windows[WINDOWS[0]])):
        per = {}
        stable = True
        concentration = {}
        for w, rows in windows.items():
            selected = [r for r in rows if conditions(r).get(name, False)]
            s = stats(selected)
            tp_symbols = {}
            for r in selected:
                if r.get("outcome") == "TP3_HIT":
                    tp_symbols[r.get("symbol","MISSING")] = tp_symbols.get(r.get("symbol","MISSING"),0) + 1
            max_share = (max(tp_symbols.values()) / s["tp3"] * 100) if s["tp3"] else None
            s["largest_symbol_tp3_share_pct"] = round(max_share,2) if max_share is not None else None
            per[str(w)] = s
            base_rate = baseline[str(w)]["tp3_rate_pct"] or 0
            if s["signals"] < 50 or s["tp3_rate_pct"] is None or s["tp3_rate_pct"] <= base_rate:
                stable = False
        candidates[name] = {"windows": per, "passes_basic_cross_window_test": stable}

    report = {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "method": "Fixed predeclared SHORT interactions tested independently on 120d, 90d, and 60d merged chronological holdouts. Candidate approval requires improvement over each window baseline and at least 50 observations per window. Symbol concentration is reported but never used to manufacture approval.",
        "baseline": baseline,
        "candidates": candidates,
        "decision": "NO_PRODUCTION_CHANGE",
    }
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    run()
