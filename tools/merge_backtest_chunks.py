"""Merge fixed chronological replay chunks into one auditable backtest artifact."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_OFFSETS = (70, 80, 90)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--expected-offset-days", type=int, default=90)
    parser.add_argument("--expected-days", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("backtest_results.json"))
    return parser.parse_args()


def load_chunk(root: Path, offset: int) -> dict:
    path = root / f"historical-backtest-chunk-{offset}" / "backtest_results.json"
    if not path.is_file():
        raise RuntimeError(f"missing_chunk_artifact:{offset}:{path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    metadata = payload.get("metadata", {})

    if int(metadata.get("days", -1)) != 10:
        raise RuntimeError(f"invalid_chunk_days:{offset}")
    if int(metadata.get("offset_days", -1)) != offset:
        raise RuntimeError(f"invalid_chunk_offset:{offset}")
    if not isinstance(payload.get("results"), list):
        raise RuntimeError(f"invalid_chunk_results:{offset}")

    return payload


def sort_key(row: dict) -> tuple[str, str, str]:
    return (
        str(row.get("replay_time", "")),
        str(row.get("symbol", "")),
        str(row.get("direction", "")),
    )


def counts(rows: list[dict]) -> dict:
    outcomes = Counter(row.get("outcome", "UNKNOWN") for row in rows)
    tp3 = outcomes.get("TP3_HIT", 0)
    sl = outcomes.get("SL_HIT", 0)
    resolved = tp3 + sl

    return {
        "signals": len(rows),
        "tp3": tp3,
        "sl": sl,
        "expired": outcomes.get("EXPIRED", 0),
        "open_or_other": len(rows)
        - tp3
        - sl
        - outcomes.get("EXPIRED", 0),
        "resolved_tp3_or_sl": resolved,
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
        "outcomes": dict(sorted(outcomes.items())),
    }


def main() -> None:
    args = parse_args()

    if args.expected_days != 30:
        raise SystemExit("this merger is intentionally fixed at 30 days")

    chunks = [load_chunk(args.root, offset) for offset in REQUIRED_OFFSETS]

    all_rows: list[dict] = []
    for payload in chunks:
        all_rows.extend(payload["results"])

    unique: dict[tuple[str, str, str], dict] = {}
    duplicates = 0

    for row in all_rows:
        key = sort_key(row)
        if key in unique:
            duplicates += 1
            if unique[key] != row:
                raise RuntimeError(f"conflicting_duplicate_replay_row:{key}")
        else:
            unique[key] = row

    rows = sorted(unique.values(), key=sort_key)
    if not rows:
        raise RuntimeError("merged_replay_has_zero_signals")

    ranges = []
    for payload in chunks:
        metadata = payload["metadata"]
        ranges.append(
            {
                "offset_days": int(metadata["offset_days"]),
                "days": int(metadata["days"]),
                "start": metadata.get("start"),
                "end": metadata.get("end"),
                "signals": len(payload["results"]),
            }
        )

    # Higher offsets are older periods. After descending sort, each older
    # chunk must end exactly where the immediately newer chunk starts.
    ranges.sort(key=lambda item: item["offset_days"], reverse=True)

    for older, newer in zip(ranges, ranges[1:]):
        if older["end"] != newer["start"]:
            raise RuntimeError(f"non_contiguous_chunks:{older}:{newer}")

    metadata = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "start": ranges[0]["start"],
        "end": ranges[-1]["end"],
        "days": 30,
        "offset_days": args.expected_offset_days,
        "chunked": True,
        "chunk_days": 10,
        "chunk_offsets": list(REQUIRED_OFFSETS),
        "duplicate_boundary_rows_removed": duplicates,
        "symbols": chunks[0]["metadata"].get("symbols", []),
        "timeframes": chunks[0]["metadata"].get("timeframes", []),
        "lookahead_policy": chunks[0]["metadata"].get("lookahead_policy"),
        "same_candle_conflict_policy": chunks[0]["metadata"].get(
            "same_candle_conflict_policy"
        ),
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

    args.output.write_text(
        json.dumps(payload, indent=2, default=str),
        encoding="utf-8",
    )

    print(
        json.dumps(
            {
                "output": str(args.output),
                "rows": len(rows),
                "duplicate_boundary_rows_removed": duplicates,
                "range": f"{ranges[0]['start']} -> {ranges[-1]['end']}",
                "summary": payload["summary"]["outcomes"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
