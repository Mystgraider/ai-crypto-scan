"""Research-only LONG candidate validation.

This module never changes scanner production logic. It evaluates fixed,
interpretable LONG candidate gates against a merged historical replay and
reports chronological stability. Thresholds are deliberately fixed research
hypotheses, not fitted on the full artifact.
"""
import json
import math
from pathlib import Path

PATH = Path("backtest_results.json")


def num(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def stats(rows):
    tp = sum(r.get("outcome") == "TP3_HIT" for r in rows)
    sl = sum(r.get("outcome") == "SL_HIT" for r in rows)
    resolved = tp + sl
    return {
        "signals": len(rows),
        "tp3": tp,
        "sl": sl,
        "expired": sum(r.get("outcome") == "EXPIRED" for r in rows),
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp / resolved, 2) if resolved else None,
    }


def geometry(rows):
    sl = []
    tp3 = []
    for r in rows:
        entry = num(r.get("entry"))
        slv = num(r.get("sl"))
        tpv = num(r.get("tp3"))
        if entry and slv is not None:
            sl.append(abs(slv - entry) / entry * 100)
        if entry and tpv is not None:
            tp3.append(abs(tpv - entry) / entry * 100)

    def median(values):
        values = sorted(values)
        if not values:
            return None
        n = len(values)
        return round(values[n // 2] if n % 2 else (values[n // 2 - 1] + values[n // 2]) / 2, 4)

    return {
        "median_sl_distance_pct": median(sl),
        "median_tp3_distance_pct": median(tp3),
    }


def evaluate(name, rows, predicate, baseline):
    chosen = [r for r in rows if predicate(r)]
    out = {**stats(chosen), **geometry(chosen)}
    out["signal_retention_pct"] = round(100 * len(chosen) / len(baseline), 2) if baseline else None
    base_tp = sum(r.get("outcome") == "TP3_HIT" for r in baseline)
    base_sl = sum(r.get("outcome") == "SL_HIT" for r in baseline)
    out["tp3_retention_pct"] = round(100 * out["tp3"] / base_tp, 2) if base_tp else None
    out["sl_reduction_pct"] = round(100 * (1 - out["sl"] / base_sl), 2) if base_sl else None
    return {name: out}


def val(r, field):
    return num(r.get(field))


def main():
    payload = json.loads(PATH.read_text(encoding="utf-8"))
    rows = [
        r for r in payload.get("results", [])
        if r.get("direction") == "LONG"
        and r.get("outcome") in {"TP3_HIT", "SL_HIT", "EXPIRED"}
    ]
    rows.sort(key=lambda r: r.get("replay_time", ""))
    if not rows:
        raise SystemExit("No LONG replay rows found")

    baseline = [r for r in rows if r.get("outcome") in {"TP3_HIT", "SL_HIT"}]

    # Fixed hypotheses chosen from the prior diagnostic discovery. They are
    # intentionally broad and are not optimized against the validation window.
    candidates = {
        "baseline": lambda r: True,
        "continuation_momentum": lambda r: (
            val(r, "macd_hist_15m") is not None
            and val(r, "macd_hist_15m") > 0
            and val(r, "rsi_15m") is not None
            and val(r, "rsi_15m") > 55
        ),
        "continuation_location": lambda r: (
            val(r, "support_distance_pct") is not None
            and val(r, "support_distance_pct") >= 1.0
            and val(r, "price_to_ema20_pct") is not None
            and val(r, "price_to_ema20_pct") >= 0.0
        ),
        "continuation_trend": lambda r: (
            val(r, "ema20_ema50_gap_pct") is not None
            and val(r, "ema20_ema50_gap_pct") > -0.25
            and val(r, "macd_hist_15m") is not None
            and val(r, "macd_hist_15m") > 0
        ),
        "continuation_confirmation": lambda r: (
            val(r, "macd_hist_15m") is not None
            and val(r, "macd_hist_15m") > 0
            and val(r, "rsi_4h") is not None
            and val(r, "rsi_4h") <= 60
            and val(r, "stoch_k_4h") is not None
            and 40 <= val(r, "stoch_k_4h") < 80
        ),
    }

    result = {
        "research_only": True,
        "production_strategy_changed": False,
        "purpose": "Independent chronological validation of LONG candidate hypotheses.",
        "warning": "No candidate is approved for production from this report alone.",
        "metadata": payload.get("metadata", {}),
        "baseline": stats(baseline),
        "candidates": {},
        "chronological_thirds": {},
    }

    for name, predicate in candidates.items():
        result["candidates"][name] = evaluate(name, baseline, predicate, baseline)[name]

    n = len(rows)
    cuts = [0, n // 3, (2 * n) // 3, n]
    labels = ["first_third", "middle_third", "last_third"]
    for label, start, end in zip(labels, cuts[:-1], cuts[1:]):
        chunk = [r for r in rows[start:end] if r.get("outcome") in {"TP3_HIT", "SL_HIT"}]
        base = stats(chunk)
        result["chronological_thirds"][label] = {
            "start": rows[start].get("replay_time") if start < n else None,
            "end": rows[end - 1].get("replay_time") if end else None,
            "baseline": base,
            "candidates": {},
        }
        for name, predicate in candidates.items():
            result["chronological_thirds"][label]["candidates"][name] = evaluate(
                name, chunk, predicate, chunk
            )[name]

    # Conservative approval rule: a candidate must beat baseline TP3 rate in
    # all three chronological thirds, retain >=20% of baseline signals, and
    # not increase median SL distance by >5%.
    approvals = {}
    for name in candidates:
        if name == "baseline":
            continue
        overall = result["candidates"][name]
        thirds = [
            result["chronological_thirds"][label]["candidates"][name]
            for label in labels
        ]
        base_thirds = [
            result["chronological_thirds"][label]["baseline"]
            for label in labels
        ]
        approvals[name] = {
            "approved": bool(
                overall["signal_retention_pct"] is not None
                and overall["signal_retention_pct"] >= 20
                and all(
                    c["tp3_rate_pct"] is not None
                    and b["tp3_rate_pct"] is not None
                    and c["tp3_rate_pct"] > b["tp3_rate_pct"]
                    for c, b in zip(thirds, base_thirds)
                )
                and overall["median_sl_distance_pct"] is not None
                and result["baseline"]["median_sl_distance_pct"] is not None
                and overall["median_sl_distance_pct"]
                <= result["baseline"]["median_sl_distance_pct"] * 1.05
            ),
            "reason": "Requires positive TP3-rate improvement in every chronological third, >=20% signal retention, and controlled SL geometry.",
        }

    result["production_approval"] = approvals
    Path("long_candidate_validation.json").write_text(
        json.dumps(result, indent=2, default=str), encoding="utf-8"
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
