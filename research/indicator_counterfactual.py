#!/usr/bin/env python3
"""Research-only chronological counterfactuals for saved scanner outcomes.

This script does NOT replay scanner gates or modify production behavior. It measures
associations in storage/signals.csv among rows resolved as TP3_HIT or SL_HIT only.
"""
from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Callable


Row = dict[str, str]
Rule = tuple[str, Callable[[Row], bool]]


def number(row: Row, key: str) -> float | None:
    raw = (row.get(key) or "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def at_least(row: Row, key: str, threshold: float) -> bool:
    value = number(row, key)
    return value is not None and value >= threshold


def resolved_rows(path: Path) -> list[Row]:
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    rows = [
        row for row in rows
        if row.get("status") in {"TP3_HIT", "SL_HIT"} and row.get("timestamp")
    ]
    rows.sort(key=lambda row: row["timestamp"])
    return rows


def metrics(rows: list[Row]) -> dict[str, int | float | None]:
    tp = sum(row["status"] == "TP3_HIT" for row in rows)
    sl = sum(row["status"] == "SL_HIT" for row in rows)
    return {
        "n": len(rows),
        "tp3": tp,
        "sl": sl,
        "tp3_rate_pct": round(100 * tp / len(rows), 2) if rows else None,
    }


def build_rules() -> list[Rule]:
    is_short = lambda row: row.get("direction") == "SHORT"
    is_long = lambda row: row.get("direction") == "LONG"
    return [
        ("ALL baseline", lambda row: True),
        ("LONG baseline", is_long),
        ("SHORT baseline", is_short),
        ("SHORT RSI >= 50", lambda row: is_short(row) and at_least(row, "rsi", 50)),
        ("SHORT ADX >= 20", lambda row: is_short(row) and at_least(row, "adx", 20)),
        (
            "SHORT RSI >= 50 AND ADX >= 20",
            lambda row: is_short(row)
            and at_least(row, "rsi", 50)
            and at_least(row, "adx", 20),
        ),
        (
            "SHORT RSI >= 50 AND ADX >= 20 AND rel_volume >= 1",
            lambda row: is_short(row)
            and at_least(row, "rsi", 50)
            and at_least(row, "adx", 20)
            and at_least(row, "rel_volume", 1),
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=Path("storage/signals.csv"))
    parser.add_argument("--train-fraction", type=float, default=0.70)
    args = parser.parse_args()
    if not 0.5 <= args.train_fraction < 1:
        parser.error("--train-fraction must be >= 0.5 and < 1")
    if not args.csv.is_file():
        parser.error(f"CSV file not found: {args.csv}")

    rows = resolved_rows(args.csv)
    if len(rows) < 20:
        parser.error(f"Only {len(rows)} resolved TP3/SL rows; need at least 20")

    split = int(len(rows) * args.train_fraction)
    train, test = rows[:split], rows[split:]
    rules = build_rules()
    report = {
        "mode": "research_only_observed_outcomes_not_scanner_replay",
        "csv": str(args.csv),
        "resolved_tp3_or_sl_rows": len(rows),
        "date_range_utc": [rows[0]["timestamp"], rows[-1]["timestamp"]],
        "split": {
            "train_fraction": args.train_fraction,
            "train_n": len(train),
            "train_dates_utc": [train[0]["timestamp"], train[-1]["timestamp"]],
            "test_n": len(test),
            "test_dates_utc": [test[0]["timestamp"], test[-1]["timestamp"]],
        },
        "metrics": [],
        "limitations": [
            "Only TP3_HIT and SL_HIT are included; TP1_HIT, TP2_HIT, expired, and open outcomes are excluded.",
            "Rows are filtered after outcomes are known; these results are not live trade expectancy.",
            "A saved-row filter is not equivalent to re-running scanner logic because the CSV does not store every gate input or pre-filter candidate.",
            "Do not promote a candidate to production from one split; use multiple chronological windows and realized-R/execution-aware analysis.",
        ],
    }
    for name, predicate in rules:
        report["metrics"].append({
            "rule": name,
            "train": metrics([row for row in train if predicate(row)]),
            "test": metrics([row for row in test if predicate(row)]),
        })
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
