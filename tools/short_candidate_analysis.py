"""Research-only SHORT RSI/ADX counterfactual analysis.

Reads backtest_results.json produced by tools/historical_replay.py.
Does not change scanner logic or production signals.
"""
import collections
import json
import math
from pathlib import Path

path = Path("backtest_results.json")
payload = json.loads(path.read_text(encoding="utf-8"))
rows = payload.get("results", [])
shorts = [row for row in rows if row.get("direction") == "SHORT"]


def num(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def counts(items):
    outcomes = collections.Counter(row.get("outcome", "UNKNOWN") for row in items)
    tp3, sl = outcomes.get("TP3_HIT", 0), outcomes.get("SL_HIT", 0)
    resolved = tp3 + sl
    return {
        "signals": len(items),
        "tp3": tp3,
        "sl": sl,
        "expired": outcomes.get("EXPIRED", 0),
        "open_or_other": len(items) - tp3 - sl - outcomes.get("EXPIRED", 0),
        "resolved_tp3_or_sl": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
    }


def selected(rsi_min=None, rsi_max=None, adx_min=None, adx_max=None):
    result = []
    for row in shorts:
        rsi, adx = num(row.get("rsi")), num(row.get("adx"))
        if rsi is None or adx is None:
            continue
        if rsi_min is not None and rsi < rsi_min:
            continue
        if rsi_max is not None and rsi >= rsi_max:
            continue
        if adx_min is not None and adx < adx_min:
            continue
        if adx_max is not None and adx >= adx_max:
            continue
        result.append(row)
    return result


adx_bands = [
    ("ADX <20", None, 20),
    ("ADX 20-25", 20, 25),
    ("ADX 25-30", 25, 30),
    ("ADX 30-35", 30, 35),
    ("ADX 35-40", 35, 40),
    ("ADX >=40", 40, None),
]
analysis = {
    "research_only": True,
    "production_strategy_changed": False,
    "warning": "Retrospective candidate comparisons are diagnostic only; candidate selection requires separate chronological validation.",
    "short_baseline": counts(shorts),
    "short_rows_missing_rsi_or_adx": sum(
        1 for row in shorts if num(row.get("rsi")) is None or num(row.get("adx")) is None
    ),
    "rsi_60_70": counts(selected(rsi_min=60, rsi_max=70)),
    "rsi_70_plus": counts(selected(rsi_min=70)),
    "rsi_60_70_by_adx_band": {},
    "rsi_60_70_adx_20_25": counts(selected(rsi_min=60, rsi_max=70, adx_min=20, adx_max=25)),
    "rsi_60_70_adx_below_30": counts(selected(rsi_min=60, rsi_max=70, adx_max=30)),
    "rsi_bands": {},
    "adx_bands": {},
}
for label, lo, hi in adx_bands:
    analysis["adx_bands"][label] = counts(selected(adx_min=lo, adx_max=hi))
    analysis["rsi_60_70_by_adx_band"][label] = counts(selected(rsi_min=60, rsi_max=70, adx_min=lo, adx_max=hi))
for label, lo, hi in [
    ("RSI <40", None, 40),
    ("RSI 40-50", 40, 50),
    ("RSI 50-60", 50, 60),
    ("RSI 60-70", 60, 70),
    ("RSI >=70", 70, None),
]:
    analysis["rsi_bands"][label] = counts(selected(rsi_min=lo, rsi_max=hi))

# EMA200 counterfactual for the strongest RSI/ADX discovery bucket.
# This is descriptive research only; it does not filter production signals.
ema_base = [
    row for row in shorts
    if num(row.get("rsi")) is not None
    and 60 <= num(row.get("rsi")) < 70
    and num(row.get("adx")) is not None
    and 20 <= num(row.get("adx")) < 25
]
ema_available = [row for row in ema_base if num(row.get("ema200_1h")) is not None
                 and num(row.get("signal_close_1h")) is not None]
ema_below = [
    row for row in ema_available
    if num(row["signal_close_1h"]) < num(row["ema200_1h"])
]
ema_above = [
    row for row in ema_available
    if num(row["signal_close_1h"]) >= num(row["ema200_1h"])
]
analysis["rsi_60_70_adx_20_25_ema200"] = {
    "base_candidate": counts(ema_base),
    "ema200_available": len(ema_available),
    "ema200_missing": len(ema_base) - len(ema_available),
    "price_below_ema200_1h": counts(ema_below),
    "price_at_or_above_ema200_1h": counts(ema_above),
    "definition": "EMA200 computed from completed 1H closes at signal time; below means signal-time 1H close < EMA200",
}
payload.setdefault("summary", {})["short_rsi_adx_research"] = analysis
path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(json.dumps(analysis, indent=2))
