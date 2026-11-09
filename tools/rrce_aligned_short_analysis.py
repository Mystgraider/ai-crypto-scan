"""Research-only RRCE-aligned SHORT analysis.

Consumes the merged backtest_results.json produced by the historical replay.
It compares observed RRCE stage cohorts and fixed, interpretable indicator
overlays. It does not change scanner behavior, risk geometry, LONG, or signals.
"""
from __future__ import annotations

import collections
import json
import math
from pathlib import Path
from typing import Callable, Iterable


def number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def outcome_counts(rows: Iterable[dict]) -> dict:
    rows = list(rows)
    outcomes = collections.Counter(row.get("outcome", "UNKNOWN") for row in rows)
    tp3 = outcomes["TP3_HIT"]
    sl = outcomes["SL_HIT"]
    resolved = tp3 + sl
    return {
        "signals": len(rows),
        "tp3": tp3,
        "sl": sl,
        "expired": outcomes["EXPIRED"],
        "incomplete_data": outcomes["INCOMPLETE_DATA"],
        "open_or_other": len(rows) - tp3 - sl - outcomes["EXPIRED"] - outcomes["INCOMPLETE_DATA"],
        "resolved": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
    }


def median(values: list[float]) -> float | None:
    values = sorted(values)
    if not values:
        return None
    middle = len(values) // 2
    value = values[middle] if len(values) % 2 else (values[middle - 1] + values[middle]) / 2
    return round(value, 5)


def geometry(rows: Iterable[dict]) -> dict:
    sl_distances, tp_distances = [], []
    for row in rows:
        entry = number(row.get("entry"))
        if entry is None or entry <= 0:
            continue
        for field, target in (("sl", sl_distances), ("tp3", tp_distances)):
            level = number(row.get(field))
            if level is not None:
                target.append(abs(level - entry) / entry * 100)
    return {
        "sl_distance_pct_median": median(sl_distances),
        "tp3_distance_pct_median": median(tp_distances),
        "sl_geometry_observations": len(sl_distances),
    }


def cohort_report(rows: list[dict]) -> dict:
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[str(row.get("rrce_status") or "MISSING")].append(row)
    return {key: {**outcome_counts(group), **geometry(group)}
            for key, group in sorted(grouped.items())}


def chronological_split(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    dated = sorted(
        (row for row in rows if row.get("replay_time")),
        key=lambda row: row["replay_time"],
    )
    if len(dated) < 3:
        return dated, []
    split = max(1, min(len(dated) - 1, (len(dated) * 2) // 3))
    return dated[:split], dated[split:]


def fixed_candidates() -> dict[str, Callable[[dict], bool]]:
    def lt(field, threshold):
        return lambda row: number(row.get(field)) is not None and number(row[field]) < threshold

    def macd_negative(field):
        return lt(field, 0)

    def both(a, b):
        return lambda row: a(row) and b(row)

    rsi4 = lt("rsi_4h", 50)
    macd4 = macd_negative("macd_hist_4h")
    rsi15 = lt("rsi_15m", 50)
    macd15 = macd_negative("macd_hist_15m")
    rsi1h_45_60 = lambda row: number(row.get("rsi")) is not None and 45 <= number(row["rsi"]) < 60
    macd1h = macd_negative("macd_hist")
    return {
        "4h_rsi_below_50_and_macd_negative": both(rsi4, macd4),
        "1h_rsi_45_60_and_macd_negative": both(rsi1h_45_60, macd1h),
        "15m_rsi_below_50_and_macd_negative": both(rsi15, macd15),
        "4h_and_15m_bearish_momentum": both(both(rsi4, macd4), both(rsi15, macd15)),
    }


def candidate_report(rows: list[dict], discovery: list[dict], holdout: list[dict]) -> dict:
    reports = {}
    for name, predicate in fixed_candidates().items():
        all_rows = [row for row in rows if predicate(row)]
        discovery_rows = [row for row in discovery if predicate(row)]
        holdout_rows = [row for row in holdout if predicate(row)]
        symbol_count = len({row.get("symbol") for row in holdout_rows if row.get("symbol")})
        holdout_stats = outcome_counts(holdout_rows)
        enough_evidence = (
            holdout_stats["signals"] >= 50
            and holdout_stats["resolved"] >= 30
            and symbol_count >= 3
        )
        passed = bool(
            enough_evidence
            and holdout_stats["tp3_rate_pct"] is not None
            and holdout_stats["tp3_rate_pct"] > 0
        )
        by_symbol = {}
        for symbol in sorted({row.get("symbol") for row in all_rows if row.get("symbol")}):
            group = [row for row in all_rows if row.get("symbol") == symbol]
            by_symbol[symbol] = outcome_counts(group)
        reports[name] = {
            "all": {**outcome_counts(all_rows), **geometry(all_rows)},
            "discovery_first_2_thirds": {**outcome_counts(discovery_rows), **geometry(discovery_rows)},
            "holdout_last_1_third": {**holdout_stats, **geometry(holdout_rows)},
            "holdout_symbol_count": symbol_count,
            "minimum_holdout_evidence_met": enough_evidence,
            "screening_status": "NOT_REJECTED_BY_BASIC_HOLDOUT_SCREEN" if passed else "REJECT_OR_INSUFFICIENT_EVIDENCE",
            "by_symbol_all_periods": by_symbol,
        }
    return reports


def build_report(payload: dict) -> dict:
    rows = [row for row in payload.get("results", []) if row.get("direction") == "SHORT"]
    discovery, holdout = chronological_split(rows)
    by_stage = collections.defaultdict(list)
    for row in rows:
        by_stage[str(row.get("rrce_failed_stage") or "RRCE_QUALIFIED")].append(row)
    choch = collections.defaultdict(list)
    for row in rows:
        choch[str(bool(row.get("rrce_choch_confirmed")))].append(row)
    stage_fields = {
        "stage1_4h_premium": "rrce_stage1_passed",
        "stage2_1h_liquidity_sweep": "rrce_stage2_passed",
        "stage3_15m_choch": "rrce_stage3_passed",
        "stage4_5m_execution": "rrce_stage4_valid",
    }
    stage_cohorts = {}
    for label, field in stage_fields.items():
        for value in (True, False, None):
            group = [row for row in rows if row.get(field) is value]
            if group:
                stage_cohorts[f"{label}:{value}"] = {
                    **outcome_counts(group), **geometry(group)
                }

    premium_bands = {
        "below_40pct": [],
        "40_to_60pct": [],
        "60_to_80pct": [],
        "80_to_100pct": [],
        "outside_or_missing": [],
    }
    for row in rows:
        position = number(row.get("rrce_stage1_position_pct"))
        if position is None or position < 0 or position > 100:
            premium_bands["outside_or_missing"].append(row)
        elif position < 40:
            premium_bands["below_40pct"].append(row)
        elif position < 60:
            premium_bands["40_to_60pct"].append(row)
        elif position < 80:
            premium_bands["60_to_80pct"].append(row)
        else:
            premium_bands["80_to_100pct"].append(row)

    entry_zones = collections.defaultdict(list)
    for row in rows:
        entry_zones[str(row.get("rrce_stage4_entry_zone") or "NOT_REACHED_OR_MISSING")].append(row)

    full_sequence = [
        row for row in rows
        if all(row.get(field) is True for field in stage_fields.values())
    ]
    stage3_and_bearish_15m = [
        row for row in rows
        if row.get("rrce_stage3_passed") is True
        and number(row.get("rsi_15m")) is not None and number(row["rsi_15m"]) < 50
        and number(row.get("macd_hist_15m")) is not None and number(row["macd_hist_15m"]) < 0
    ]
    symbols = {}
    for symbol in sorted({row.get("symbol") for row in rows if row.get("symbol")}):
        group = [row for row in rows if row.get("symbol") == symbol]
        symbols[symbol] = {
            "baseline": outcome_counts(group),
            "rrce_qualified": outcome_counts([r for r in group if r.get("rrce_status") == "QUALIFIED"]),
        }
    return {
        "research_only": True,
        "production_strategy_changed": False,
        "long_logic_changed": False,
        "risk_or_sl_tp_geometry_changed": False,
        "method": "RRCE cohorts are observed scanner outputs; indicator overlays are fixed hypotheses. First two chronological thirds are discovery, final third is holdout.",
        "warning": "This replay is regime-sensitive. A candidate is not approved by a positive aggregate result; independent additional holdout and economic expectancy checks remain required.",
        "baseline": outcome_counts(rows),
        "rrce_status_cohorts": cohort_report(rows),
        "rrce_failed_stage_cohorts": {
            key: {**outcome_counts(group), **geometry(group)}
            for key, group in sorted(by_stage.items())
        },
        "rrce_choch_confirmed_cohorts": {
            key: {**outcome_counts(group), **geometry(group)}
            for key, group in sorted(choch.items())
        },
        "rrce_stage_pass_cohorts": stage_cohorts,
        "rrce_4h_premium_position_bands": {
            key: {**outcome_counts(group), **geometry(group)}
            for key, group in premium_bands.items()
        },
        "rrce_5m_entry_zone_cohorts": {
            key: {**outcome_counts(group), **geometry(group)}
            for key, group in sorted(entry_zones.items())
        },
        "full_rrce_sequence": {**outcome_counts(full_sequence), **geometry(full_sequence)},
        "rrce_stage3_plus_bearish_15m_momentum": {
            **outcome_counts(stage3_and_bearish_15m), **geometry(stage3_and_bearish_15m)
        },
        "chronological_discovery": {
            **outcome_counts(discovery),
            "start": discovery[0].get("replay_time") if discovery else None,
            "end": discovery[-1].get("replay_time") if discovery else None,
        },
        "chronological_holdout": {
            **outcome_counts(holdout),
            "start": holdout[0].get("replay_time") if holdout else None,
            "end": holdout[-1].get("replay_time") if holdout else None,
        },
        "fixed_indicator_candidates": candidate_report(rows, discovery, holdout),
        "by_symbol": symbols,
        "decision": "NO_PRODUCTION_CHANGE",
    }


def main() -> None:
    path = Path("backtest_results.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    report = build_report(payload)
    payload.setdefault("summary", {})["rrce_aligned_short_research"] = report
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
