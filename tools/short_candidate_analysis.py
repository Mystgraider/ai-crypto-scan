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
        "incomplete_data": outcomes.get("INCOMPLETE_DATA", 0),
        "open_or_other": outcomes.get("OPEN", 0) + sum(
            count for outcome, count in outcomes.items()
            if outcome not in {"TP3_HIT", "SL_HIT", "EXPIRED", "INCOMPLETE_DATA", "OPEN"}
        ),
        "resolved_tp3_or_sl": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
    }


def selected(source, rsi_min=None, rsi_max=None, adx_min=None, adx_max=None):
    result = []
    for row in source:
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


indicator_complete_shorts = [
    row for row in shorts
    if num(row.get("rsi")) is not None and num(row.get("adx")) is not None
]

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
    "incomplete_outcomes_excluded_from_tp3_rate": True,
    "short_baseline_all_rows": counts(shorts),
    "short_baseline_indicator_complete": counts(indicator_complete_shorts),
    "short_rows_missing_rsi_or_adx": len(shorts) - len(indicator_complete_shorts),
    "indicator_complete_coverage_pct": (
        round(100 * len(indicator_complete_shorts) / len(shorts), 2) if shorts else None
    ),
    "rsi_60_70": counts(selected(indicator_complete_shorts, rsi_min=60, rsi_max=70)),
    "rsi_70_plus": counts(selected(indicator_complete_shorts, rsi_min=70)),
    "rsi_60_70_by_adx_band": {},
    "rsi_60_70_adx_20_25": counts(selected(indicator_complete_shorts, rsi_min=60, rsi_max=70, adx_min=20, adx_max=25)),
    "rsi_60_70_adx_below_30": counts(selected(indicator_complete_shorts, rsi_min=60, rsi_max=70, adx_max=30)),
    "rsi_bands": {},
    "adx_bands": {},
}
for label, lo, hi in adx_bands:
    analysis["adx_bands"][label] = counts(selected(indicator_complete_shorts, adx_min=lo, adx_max=hi))
    analysis["rsi_60_70_by_adx_band"][label] = counts(
        selected(indicator_complete_shorts, rsi_min=60, rsi_max=70, adx_min=lo, adx_max=hi)
    )
for label, lo, hi in [
    ("RSI <40", None, 40),
    ("RSI 40-50", 40, 50),
    ("RSI 50-60", 50, 60),
    ("RSI 60-70", 60, 70),
    ("RSI >=70", 70, None),
]:
    analysis["rsi_bands"][label] = counts(selected(indicator_complete_shorts, rsi_min=lo, rsi_max=hi))

# EMA200 counterfactual for the RSI/ADX discovery bucket.
# It remains descriptive research only and never filters production signals.
ema_base = selected(indicator_complete_shorts, rsi_min=60, rsi_max=70, adx_min=20, adx_max=25)
ema_available = [
    row for row in ema_base
    if num(row.get("ema200_1h")) is not None and num(row.get("signal_close_1h")) is not None
]
ema_below = [
    row for row in ema_available
    if num(row["signal_close_1h"]) < num(row["ema200_1h"])
]
ema_above = [
    row for row in ema_available
    if num(row["signal_close_1h"]) >= num(row["ema200_1h"])
]
# Directional confirmation: compare -DI dominance with +DI dominance.
di_available = [
    row for row in shorts
    if num(row.get("plus_di")) is not None and num(row.get("minus_di")) is not None
]
di_bearish = [
    row for row in di_available
    if num(row["minus_di"]) > num(row["plus_di"])
]
di_not_bearish = [
    row for row in di_available
    if num(row["minus_di"]) <= num(row["plus_di"])
]
analysis["di_directional_comparison"] = {
    "available": len(di_available),
    "missing": len(shorts) - len(di_available),
    "minus_di_greater_than_plus_di": counts(di_bearish),
    "minus_di_not_greater_than_plus_di": counts(di_not_bearish),
    "definition": "Bearish DI confirmation means -DI > +DI at signal time; diagnostic only, not a production gate.",
}

# Entry-location diagnostics. Distances are measured at signal time and
# deliberately reported as buckets rather than optimized thresholds.
support_available = [
    row for row in shorts if num(row.get("support_distance_pct")) is not None
]
analysis["support_distance_bands"] = {
    "available": len(support_available),
    "missing": len(shorts) - len(support_available),
    "below_1pct": counts([row for row in support_available if num(row["support_distance_pct"]) < 1]),
    "1_to_2pct": counts([row for row in support_available if 1 <= num(row["support_distance_pct"]) < 2]),
    "2_to_4pct": counts([row for row in support_available if 2 <= num(row["support_distance_pct"]) < 4]),
    "4pct_or_more": counts([row for row in support_available if num(row["support_distance_pct"]) >= 4]),
    "definition": "Distance from signal-time price to nearest support below price; closer support may constrain SHORT downside.",
}
ema_entry_available = [
    row for row in shorts if num(row.get("price_to_ema20_pct")) is not None
]
analysis["price_to_ema20_comparison"] = {
    "available": len(ema_entry_available),
    "missing": len(shorts) - len(ema_entry_available),
    "below_ema20": counts([row for row in ema_entry_available if num(row["price_to_ema20_pct"]) < 0]),
    "at_or_above_ema20": counts([row for row in ema_entry_available if num(row["price_to_ema20_pct"]) >= 0]),
    "definition": "Signal-time price relative to completed-candle EMA20; descriptive only.",
}

analysis["rsi_60_70_adx_20_25_ema200"] = {
    "base_candidate": counts(ema_base),
    "ema200_available": len(ema_available),
    "ema200_missing": len(ema_base) - len(ema_available),
    "price_below_ema200_1h": counts(ema_below),
    "price_at_or_above_ema200_1h": counts(ema_above),
    "definition": "EMA200 computed from completed 1H closes at signal time; below means signal-time 1H close < EMA200",
}

# Additional SHORT candidate diagnostics: entry trend alignment, stop geometry,
# per-symbol concentration, and chronological thirds. These are research-only.
def subset(predicate, source=shorts):
    return [row for row in source if predicate(row)]


def pct_distance(row, field):
    entry, level = num(row.get("entry")), num(row.get(field))
    if entry is None or level is None or entry <= 0:
        return None
    return abs(level - entry) / entry * 100


def geometry(items):
    sl_dist = [pct_distance(row, "sl") for row in items]
    tp3_dist = [pct_distance(row, "tp3") for row in items]
    sl_dist = sorted(value for value in sl_dist if value is not None)
    tp3_dist = sorted(value for value in tp3_dist if value is not None)

    def median(values):
        if not values:
            return None
        middle = len(values) // 2
        return round(values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2, 4)

    return {
        "sl_distance_pct_median": median(sl_dist),
        "tp3_distance_pct_median": median(tp3_dist),
        "sl_distance_observations": len(sl_dist),
        "tp3_distance_observations": len(tp3_dist),
    }


# Candidate combinations selected from the Run #132 discovery readout.
# No thresholds are applied to scanner_v5.py; these are counterfactual counts.
candidate_predicates = {
    "baseline": lambda row: True,
    "rsi_50_70_and_adx_below_20": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) < 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
    ),
    "rsi_50_70_adx_below_20_price_at_or_above_ema20": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) < 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
        and num(row.get("price_to_ema20_pct")) is not None
        and num(row["price_to_ema20_pct"]) >= 0
    ),
    "rsi_50_70_adx_below_20_di_not_bearish": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) < 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
        and num(row.get("plus_di")) is not None and num(row.get("minus_di")) is not None
        and num(row["minus_di"]) <= num(row["plus_di"])
    ),
    "rsi_50_70_adx_below_20_price_at_or_above_ema20_di_not_bearish": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) < 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
        and num(row.get("price_to_ema20_pct")) is not None
        and num(row["price_to_ema20_pct"]) >= 0
        and num(row.get("plus_di")) is not None and num(row.get("minus_di")) is not None
        and num(row["minus_di"]) <= num(row["plus_di"])
    ),
}
analysis["short_candidate_combinations"] = {}
for name, predicate in candidate_predicates.items():
    chosen = subset(predicate)
    analysis["short_candidate_combinations"][name] = {
        **counts(chosen),
        **geometry(chosen),
        "signal_retention_pct": round(100 * len(chosen) / len(shorts), 2) if shorts else None,
        "tp3_retention_pct": round(
            100 * sum(row.get("outcome") == "TP3_HIT" for row in chosen)
            / sum(row.get("outcome") == "TP3_HIT" for row in shorts), 2
        ) if any(row.get("outcome") == "TP3_HIT" for row in shorts) else None,
        "sl_reduction_pct": round(
            100 * (1 - sum(row.get("outcome") == "SL_HIT" for row in chosen)
                  / sum(row.get("outcome") == "SL_HIT" for row in shorts)), 2
        ) if any(row.get("outcome") == "SL_HIT" for row in shorts) else None,
    }

# Broad feature audit across the 1H signal row and completed 4H/15m context.
# Quartile cut points are descriptive discovery thresholds only; they must not
# be copied into production without confirmation on a separate time offset.
feature_fields = [
    "rsi", "adx", "plus_di", "minus_di", "di_spread",
    "ema20_ema50_gap_pct", "price_to_ema20_pct", "support_distance_pct",
    "rel_volume", "macd_hist", "stoch_k", "stoch_d", "bb_pct_b",
    "roc", "atr_pct", "ema200_distance_pct",
    "rsi_4h", "adx_4h", "macd_hist_4h", "stoch_k_4h", "bb_pct_b_4h",
    "rsi_15m", "adx_15m", "macd_hist_15m", "stoch_k_15m", "bb_pct_b_15m",
]


def quantile(sorted_values, fraction):
    if not sorted_values:
        return None
    position = (len(sorted_values) - 1) * fraction
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return sorted_values[lower]
    weight = position - lower
    return sorted_values[lower] * (1 - weight) + sorted_values[upper] * weight


analysis["feature_distribution_audit"] = {}
for field in feature_fields:
    available = [(num(row.get(field)), row) for row in shorts]
    available = [(value, row) for value, row in available if value is not None]
    values = sorted(value for value, _ in available)
    if not values:
        analysis["feature_distribution_audit"][field] = {
            "available": 0, "missing": len(shorts), "quartile_cut_points": [],
            "q1": counts([]), "q2": counts([]), "q3": counts([]), "q4": counts([]),
        }
        continue
    cuts = [quantile(values, fraction) for fraction in (0.25, 0.50, 0.75)]
    buckets = {"q1": [], "q2": [], "q3": [], "q4": []}
    for value, row in available:
        if value <= cuts[0]:
            buckets["q1"].append(row)
        elif value <= cuts[1]:
            buckets["q2"].append(row)
        elif value <= cuts[2]:
            buckets["q3"].append(row)
        else:
            buckets["q4"].append(row)
    analysis["feature_distribution_audit"][field] = {
        "available": len(available),
        "missing": len(shorts) - len(available),
        "quartile_cut_points": [round(value, 8) for value in cuts],
        **{name: {**counts(items), **geometry(items)} for name, items in buckets.items()},
    }

# EMA20/EMA50 spread buckets: the gap's sign and magnitude may help separate
# early trend alignment from extended moves. Buckets are fixed, not optimized.
ema_gap_bands = [
    ("gap_below_minus_1pct", None, -1.0),
    ("gap_minus_1_to_minus_0_25pct", -1.0, -0.25),
    ("gap_minus_0_25_to_0pct", -0.25, 0.0),
    ("gap_0_to_0_25pct", 0.0, 0.25),
    ("gap_0_25_to_1pct", 0.25, 1.0),
    ("gap_1pct_or_more", 1.0, None),
]
analysis["ema20_ema50_gap_bands"] = {}
for label, low, high in ema_gap_bands:
    chosen = [
        row for row in shorts
        if num(row.get("ema20_ema50_gap_pct")) is not None
        and (low is None or num(row["ema20_ema50_gap_pct"]) >= low)
        and (high is None or num(row["ema20_ema50_gap_pct"]) < high)
    ]
    analysis["ema20_ema50_gap_bands"][label] = {**counts(chosen), **geometry(chosen)}

# Per-symbol candidate breakdown catches a result driven by one market only.
analysis["candidate_by_symbol"] = {}
primary = candidate_predicates["rsi_50_70_and_adx_below_20"]
for symbol in sorted({row.get("symbol") for row in shorts if row.get("symbol")}):
    symbol_rows = [row for row in shorts if row.get("symbol") == symbol]
    chosen = [row for row in symbol_rows if primary(row)]
    analysis["candidate_by_symbol"][symbol] = {
        "baseline": counts(symbol_rows),
        "candidate_rsi_50_70_adx_below_20": counts(chosen),
    }

# Split the replay into chronological thirds to reveal time concentration.
dated = []
for row in shorts:
    try:
        stamp = row.get("replay_time")
        if stamp:
            dated.append((stamp, row))
    except Exception:
        pass
dated.sort(key=lambda item: item[0])
third = max(1, (len(dated) + 2) // 3)
analysis["chronological_thirds"] = {}
for index, label in enumerate(("first_third", "middle_third", "last_third")):
    chunk = dated[index * third:(index + 1) * third]
    chunk_rows = [row for _, row in chunk]
    chosen = [row for row in chunk_rows if primary(row)]
    analysis["chronological_thirds"][label] = {
        "start": chunk[0][0] if chunk else None,
        "end": chunk[-1][0] if chunk else None,
        "baseline": counts(chunk_rows),
        "candidate_rsi_50_70_adx_below_20": counts(chosen),
    }

payload.setdefault("summary", {})["short_rsi_adx_research"] = analysis
path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(json.dumps(analysis, indent=2))
