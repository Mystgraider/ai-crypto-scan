"""Merge three contiguous 10-day historical replay chunks into a 30-day artifact."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-offset-days", type=int, default=90)
    parser.add_argument("--expected-days", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("backtest_results.json"))
    return parser.parse_args()


def load_chunk(root: Path, offset: int) -> dict:
    candidates = (
        root / f"historical-backtest-chunk-{offset}" / "backtest_results.json",
        root / f"short-holdout-120-chunk-{offset}" / "backtest_results.json",
        root / f"short-holdout-chunk-{offset}" / "backtest_results.json",
    )
    path = next((candidate for candidate in candidates if candidate.is_file()), None)
    if path is None:
        tried = ", ".join(str(candidate) for candidate in candidates)
        raise RuntimeError(f"missing_chunk_artifact:{offset}; searched: {tried}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})
    if int(metadata.get("days", -1)) != 10:
        raise RuntimeError(f"invalid_chunk_days:{offset}")
    if int(metadata.get("offset_days", -1)) != offset:
        raise RuntimeError(f"invalid_chunk_offset:{offset}")
    if not isinstance(payload.get("results"), list):
        raise RuntimeError(f"invalid_chunk_results:{offset}")
    if not metadata.get("start") or not metadata.get("end"):
        raise RuntimeError(f"missing_chunk_time_range:{offset}")
    return payload


def sort_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("replay_time", "")),
        str(row.get("symbol", "")),
        str(row.get("direction", "")),
    )


def counts(rows: list[dict]) -> dict:
    outcomes = Counter(row.get("outcome", "UNKNOWN") for row in rows)
    tp3, sl = outcomes.get("TP3_HIT", 0), outcomes.get("SL_HIT", 0)
    resolved = tp3 + sl
    return {
        "signals": len(rows),
        "tp3": tp3,
        "sl": sl,
        "expired": outcomes.get("EXPIRED", 0),
        "incomplete_data": outcomes.get("INCOMPLETE_DATA", 0),
        "open_or_other": len(rows) - tp3 - sl - outcomes.get("EXPIRED", 0) - outcomes.get("INCOMPLETE_DATA", 0),
        "resolved_tp3_or_sl": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
        "outcomes": dict(sorted(outcomes.items())),
    }


def parse_time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"invalid_timestamp:{label}:{value}") from exc
    if parsed.tzinfo is None:
        raise RuntimeError(f"naive_timestamp:{label}:{value}")
    return parsed.astimezone(timezone.utc)


def main() -> None:
    args = parse_args()
    if args.expected_days != 30:
        raise SystemExit("this merger is intentionally fixed at 30 days")
    if args.expected_offset_days < 20:
        raise SystemExit("expected offset must be at least 20 days")

    required_offsets = tuple(args.expected_offset_days - step for step in (0, 10, 20))
    chunks = [load_chunk(args.root, offset) for offset in required_offsets]

    # All chunks must describe the same universe and outcome semantics.
    invariant_fields = (
        "symbols", "timeframes", "lookahead_policy",
        "same_candle_conflict_policy", "outcome_expiry_hours",
        "outcome_candle_interval", "incomplete_outcome_policy",
        "scan_cadence", "forming_candle_policy",
    )
    reference_metadata = chunks[0]["metadata"]
    for offset, chunk in zip(required_offsets[1:], chunks[1:]):
        for field in invariant_fields:
            if chunk["metadata"].get(field) != reference_metadata.get(field):
                raise RuntimeError(
                    f"chunk_metadata_mismatch:{field}:offset={offset}:"
                    f"{chunk['metadata'].get(field)!r}!={reference_metadata.get(field)!r}"
                )

    ranges = []
    for chunk in chunks:
        metadata = chunk["metadata"]
        start = parse_time(metadata["start"], f"offset_{metadata['offset_days']}_start")
        end = parse_time(metadata["end"], f"offset_{metadata['offset_days']}_end")
        if end - start != timedelta(days=10):
            raise RuntimeError(f"invalid_chunk_duration:{metadata['offset_days']}:{start}:{end}")
        ranges.append({
            "offset_days": int(metadata["offset_days"]),
            "days": int(metadata["days"]),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "signals": len(chunk["results"]),
        })

    ranges.sort(key=lambda item: item["offset_days"], reverse=True)
    for older, newer in zip(ranges, ranges[1:]):
        if parse_time(older["end"], "older_end") != parse_time(newer["start"], "newer_start"):
            raise RuntimeError(f"non_contiguous_chunks:{older}:{newer}")

    all_rows = [row for chunk in chunks for row in chunk["results"]]
    unique: dict[tuple[str, str, str], dict] = {}
    duplicates = 0
    for row in all_rows:
        key = sort_key(row)
        if key in unique:
            if unique[key] != row:
                raise RuntimeError(f"conflicting_duplicate_replay_row:{key}")
            duplicates += 1
        else:
            unique[key] = row

    rows = sorted(unique.values(), key=sort_key)
    if not rows:
        raise RuntimeError("merged_replay_has_zero_signals")
    if duplicates > sum(len(chunk["results"]) for chunk in chunks) * 0.01:
        raise RuntimeError(f"unexpected_duplicate_rate:{duplicates}")

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start": ranges[0]["start"],
        "end": ranges[-1]["end"],
        "days": 30,
        "offset_days": args.expected_offset_days,
        "chunked": True,
        "chunk_days": 10,
        "chunk_offsets": list(required_offsets),
        "duplicate_boundary_rows_removed": duplicates,
        "symbols": reference_metadata.get("symbols", []),
        "timeframes": reference_metadata.get("timeframes", []),
        "lookahead_policy": reference_metadata.get("lookahead_policy"),
        "same_candle_conflict_policy": reference_metadata.get("same_candle_conflict_policy"),
        "outcome_expiry_hours": reference_metadata.get("outcome_expiry_hours"),
        "outcome_candle_interval": reference_metadata.get("outcome_candle_interval"),
        "incomplete_outcome_policy": reference_metadata.get("incomplete_outcome_policy"),
        "scan_cadence": reference_metadata.get("scan_cadence"),
        "forming_candle_policy": reference_metadata.get("forming_candle_policy"),
        "production_code_modified": False,
        "harness_mode": "scanner_v5.main historical injection; 3-way chronological chunk merge",
    }
    payload = {
        "metadata": metadata,
        "summary": {
            "signals": len(rows),
            "outcomes": counts(rows),
            "chunk_ranges": ranges,
        },
        "results": rows,
    }
    args.output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps({
        "output": str(args.output),
        "rows": len(rows),
        "duplicate_boundary_rows_removed": duplicates,
        "range": f"{ranges[0]['start']} -> {ranges[-1]['end']}",
        "summary": payload["summary"]["outcomes"],
    }, indent=2))


if __name__ == "__main__":
    main()
