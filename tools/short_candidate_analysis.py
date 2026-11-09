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
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) <= 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
    ),
    "rsi_50_70_adx_below_20_price_at_or_above_ema20": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) <= 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
        and num(row.get("price_to_ema20_pct")) is not None
        and num(row["price_to_ema20_pct"]) >= 0
    ),
    "rsi_50_70_adx_below_20_di_not_bearish": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) <= 70
        and num(row.get("adx")) is not None and num(row["adx"]) < 20
        and num(row.get("plus_di")) is not None and num(row.get("minus_di")) is not None
        and num(row["minus_di"]) <= num(row["plus_di"])
    ),
    "rsi_50_70_adx_below_20_price_at_or_above_ema20_di_not_bearish": lambda row: (
        num(row.get("rsi")) is not None and 50 <= num(row["rsi"]) <= 70
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


# ---------------------------------------------------------------------------
# Multi-feature SHORT candidate discovery (research-only).
# Uses the first two chronological thirds for candidate ranking and reports
# the final third as a holdout. It never changes scanner production behavior.
# Candidate thresholds below are fixed research buckets, not optimized cutoffs.
# ---------------------------------------------------------------------------
from itertools import combinations

dated_rows = sorted(
    (row for row in shorts if row.get("replay_time")),
    key=lambda row: row["replay_time"],
)
split_index = max(1, min(len(dated_rows) - 1, (len(dated_rows) * 2) // 3))
discovery_rows = dated_rows[:split_index]
holdout_rows = dated_rows[split_index:]

# Broad, interpretable ranges spanning entry momentum, trend strength,
# directional pressure, volatility, location, and higher/lower timeframe context.
multi_feature_bands = {
    "rsi": [(0, 40), (40, 50), (50, 60), (60, 70), (70, 101)],
    "adx": [(0, 15), (15, 20), (20, 25), (25, 30), (30, 101)],
    "di_spread": [(-100, -10), (-10, 0), (0, 10), (10, 100)],
    "ema20_ema50_gap_pct": [(-100, -1), (-1, -0.25), (-0.25, 0), (0, 0.25), (0.25, 1), (1, 100)],
    "price_to_ema20_pct": [(-100, -2), (-2, -1), (-1, 0), (0, 1), (1, 2), (2, 100)],
    "support_distance_pct": [(0, 0.25), (0.25, 0.5), (0.5, 1), (1, 2), (2, 4), (4, 100)],
    "rel_volume": [(0, 0.5), (0.5, 0.8), (0.8, 1), (1, 1.5), (1.5, 3), (3, 100)],
    "macd_hist": [(-1e9, -0.01), (-0.01, -0.001), (-0.001, 0), (0, 0.001), (0.001, 0.01), (0.01, 1e9)],
    "stoch_k": [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)],
    "stoch_d": [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)],
    "bb_pct_b": [(-10, 0), (0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1), (1, 10)],
    "roc": [(-100, -3), (-3, -1), (-1, 0), (0, 1), (1, 3), (3, 100)],
    "atr_pct": [(0, 0.3), (0.3, 0.5), (0.5, 0.8), (0.8, 1.2), (1.2, 2), (2, 100)],
    "ema200_distance_pct": [(-100, -4), (-4, -2), (-2, 0), (0, 2), (2, 4), (4, 100)],
    "rsi_4h": [(0, 40), (40, 50), (50, 60), (60, 70), (70, 101)],
    "adx_4h": [(0, 15), (15, 20), (20, 25), (25, 30), (30, 101)],
    "macd_hist_4h": [(-1e9, -0.01), (-0.01, -0.001), (-0.001, 0), (0, 0.001), (0.001, 0.01), (0.01, 1e9)],
    "stoch_k_4h": [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)],
    "bb_pct_b_4h": [(-10, 0), (0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1), (1, 10)],
    "rsi_15m": [(0, 40), (40, 50), (50, 60), (60, 70), (70, 101)],
    "adx_15m": [(0, 15), (15, 20), (20, 25), (25, 30), (30, 101)],
    "macd_hist_15m": [(-1e9, -0.01), (-0.01, -0.001), (-0.001, 0), (0, 0.001), (0.001, 0.01), (0.01, 1e9)],
    "stoch_k_15m": [(0, 20), (20, 40), (40, 60), (60, 80), (80, 100)],
    "bb_pct_b_15m": [(-10, 0), (0, 0.2), (0.2, 0.4), (0.4, 0.6), (0.6, 0.8), (0.8, 1), (1, 10)],
}

def feature_match(row, condition):
    field, low, high = condition
    value = num(row.get(field))
    return value is not None and low <= value < high

def multi_stats(items, baseline_rows=shorts):
    result = counts(items)
    baseline_tp = sum(row.get("outcome") == "TP3_HIT" for row in baseline_rows)
    baseline_sl = sum(row.get("outcome") == "SL_HIT" for row in baseline_rows)
    baseline_signals = len(baseline_rows)
    result["signal_retention_pct"] = round(
        100 * len(items) / baseline_signals, 2
    ) if baseline_signals else None
    result["tp3_retention_pct"] = round(
        100 * result["tp3"] / baseline_tp, 2
    ) if baseline_tp else None
    result["sl_reduction_pct"] = round(
        100 * (1 - result["sl"] / baseline_sl), 2
    ) if baseline_sl else None
    result["sl_distance_pct_median"] = geometry(items)["sl_distance_pct_median"]
    result["tp3_distance_pct_median"] = geometry(items)["tp3_distance_pct_median"]
    return result

def condition_label(condition):
    field, low, high = condition
    return f"{field} in [{low}, {high})"

baseline_discovery = multi_stats(discovery_rows, discovery_rows)
baseline_holdout = multi_stats(holdout_rows, holdout_rows)
conditions = []
for field, ranges in multi_feature_bands.items():
    for low, high in ranges:
        selected_rows = [row for row in discovery_rows if feature_match(row, (field, low, high))]
        # Require a real discovery sample; this prevents tiny buckets from
        # entering the ranking solely because of one or two TP3 outcomes.
        if len(selected_rows) >= max(35, int(len(discovery_rows) * 0.035)):
            conditions.append((field, low, high))

candidate_records = []
for condition_a, condition_b in combinations(conditions, 2):
    if condition_a[0] == condition_b[0]:
        continue
    discovery = [
        row for row in discovery_rows
        if feature_match(row, condition_a) and feature_match(row, condition_b)
    ]
    train_stats = multi_stats(discovery, discovery_rows)
    if train_stats["signals"] < max(45, int(len(discovery_rows) * 0.04)):
        continue
    if train_stats["tp3"] < 8:
        continue
    # Objective directly reflects the user's priority: preserve TP3 while
    # reducing SL. Do not reward a tiny candidate that simply removes nearly
    # every signal.
    tp_keep = (train_stats["tp3_retention_pct"] or 0) / 100
    sl_keep = 1 - (train_stats["sl_reduction_pct"] or 0) / 100
    coverage = (train_stats["signal_retention_pct"] or 0) / 100
    objective_score = (tp_keep - sl_keep) * min(1.0, coverage / 0.35)
    candidate_records.append({
        "conditions": [condition_label(condition_a), condition_label(condition_b)],
        "discovery": train_stats,
        "objective_score": round(objective_score, 5),
        "_conditions": [condition_a, condition_b],
    })

candidate_records.sort(
    key=lambda item: (
        item["objective_score"],
        item["discovery"]["tp3_retention_pct"] or 0,
        item["discovery"]["sl_reduction_pct"] or 0,
    ),
    reverse=True,
)
top_candidates = []
for item in candidate_records[:40]:
    condition_a, condition_b = item["_conditions"]
    holdout = [
        row for row in holdout_rows
        if feature_match(row, condition_a) and feature_match(row, condition_b)
    ]
    public_item = {key: value for key, value in item.items() if key != "_conditions"}
    public_item["holdout"] = multi_stats(holdout, holdout_rows)
    public_item["holdout_sample_adequate"] = len(holdout) >= 20

    # Robustness diagnostics: a candidate that looks strong only because one
    # symbol or one chronological slice supplied most of its TP3s is not a
    # reliable indicator setup. This remains research-only and never gates
    # production signals.
    symbol_breakdown = {}
    for symbol in sorted({row.get("symbol") for row in holdout_rows if row.get("symbol")}):
        symbol_rows = [row for row in holdout if row.get("symbol") == symbol]
        if not symbol_rows:
            continue
        symbol_tp3 = sum(row.get("outcome") == "TP3_HIT" for row in symbol_rows)
        symbol_sl = sum(row.get("outcome") == "SL_HIT" for row in symbol_rows)
        symbol_breakdown[symbol] = {
            "signals": len(symbol_rows),
            "tp3": symbol_tp3,
            "sl": symbol_sl,
            "expired": sum(row.get("outcome") == "EXPIRED" for row in symbol_rows),
            "tp3_rate_pct": round(100 * symbol_tp3 / len(symbol_rows), 2),
        }

    holdout_dated = sorted(
        (row for row in holdout if row.get("replay_time")),
        key=lambda row: row["replay_time"],
    )
    thirds = {}
    if holdout_dated:
        third_size = max(1, (len(holdout_dated) + 2) // 3)
        for index, label in enumerate(("first_third", "middle_third", "last_third")):
            chunk = holdout_dated[index * third_size:(index + 1) * third_size]
            if not chunk:
                continue
            chunk_tp3 = sum(row.get("outcome") == "TP3_HIT" for row in chunk)
            chunk_sl = sum(row.get("outcome") == "SL_HIT" for row in chunk)
            thirds[label] = {
                "start": chunk[0]["replay_time"],
                "end": chunk[-1]["replay_time"],
                "signals": len(chunk),
                "tp3": chunk_tp3,
                "sl": chunk_sl,
                "expired": sum(row.get("outcome") == "EXPIRED" for row in chunk),
                "tp3_rate_pct": round(100 * chunk_tp3 / len(chunk), 2),
            }

    total_holdout_tp3 = public_item["holdout"]["tp3"]
    ranked_symbol_tp3 = sorted(
        (item["tp3"] for item in symbol_breakdown.values()),
        reverse=True,
    )
    largest_symbol_tp3_share = (
        round(100 * ranked_symbol_tp3[0] / total_holdout_tp3, 2)
        if total_holdout_tp3 and ranked_symbol_tp3 else 0.0
    )
    public_item["holdout_by_symbol"] = symbol_breakdown
    public_item["holdout_chronological_thirds"] = thirds
    public_item["holdout_tp3_largest_symbol_share_pct"] = largest_symbol_tp3_share
    public_item["stability_warning"] = (
        "TP3 concentration: one symbol supplies >=60% of holdout TP3s"
        if largest_symbol_tp3_share >= 60.0
        else None
    )
    top_candidates.append(public_item)

analysis["multi_feature_candidate_discovery"] = {
    "research_only": True,
    "production_strategy_changed": False,
    "split_method": "chronological first two thirds for candidate ranking; final third reported as holdout",
    "split_timestamp": holdout_rows[0].get("replay_time") if holdout_rows else None,
    "discovery_rows": len(discovery_rows),
    "holdout_rows": len(holdout_rows),
    "feature_fields_tested": list(multi_feature_bands),
    "eligible_single_feature_bands": len(conditions),
    "pairwise_candidates_evaluated": len(candidate_records),
    "discovery_baseline": baseline_discovery,
    "holdout_baseline": baseline_holdout,
    "ranking_objective": "TP3 retention minus SL retention, with both retention values measured against the same chronological split baseline; score is scaled down when candidate retains less than 35% of split signals; discovery-only ranking",
    "top_candidates_ranked_on_discovery_only": top_candidates,
    "acceptance_warning": "No candidate is approved by this report. Discovery and holdout retention are measured against their own split-local baselines. Any promising setup must be frozen and tested on a separate offset/window not used for discovery; inspect per-symbol, stop-distance, and TP3-distance behavior before any production change.",
}
payload.setdefault("summary", {})["short_rsi_adx_research"] = analysis
path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(json.dumps(analysis["multi_feature_candidate_discovery"], indent=2))
