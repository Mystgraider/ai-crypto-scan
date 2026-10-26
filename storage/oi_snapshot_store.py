"""Isolated, unit-safe persistence primitives for OI observations.

This module is deliberately not imported by scanner_v5.py or OIEngine.
A caller must choose and configure a durable backend before production use;
a local JSONL file alone is not persistent across ephemeral GitHub Actions jobs.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1


def _utc_timestamp(value: str | datetime) -> datetime:
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("observed_at must be an ISO-8601 timestamp") from exc
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    return value.astimezone(timezone.utc)


def _timestamp_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _validate_snapshot(
    symbol: str,
    observed_at: str | datetime,
    value: float,
    field_path: str,
    unit: str,
) -> dict[str, Any]:
    if not isinstance(symbol, str) or not symbol.strip():
        raise ValueError("symbol must be a non-empty string")
    if not isinstance(field_path, str) or not field_path.strip():
        raise ValueError("field_path must be a non-empty string")
    if not isinstance(unit, str) or not unit.strip():
        raise ValueError("unit must be explicit and non-empty")

    try:
        numeric_value = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("OI value must be numeric") from exc
    if not math.isfinite(numeric_value) or numeric_value <= 0:
        raise ValueError("OI value must be finite and positive")

    timestamp = _utc_timestamp(observed_at)
    return {
        "schema_version": SCHEMA_VERSION,
        "symbol": symbol.strip(),
        "observed_at": _timestamp_text(timestamp),
        "value": numeric_value,
        "field_path": field_path.strip(),
        "unit": unit.strip(),
    }


def load_snapshots(path: str | Path) -> list[dict[str, Any]]:
    """Load validated JSONL snapshots; fail loudly on malformed persisted data."""
    file_path = Path(path)
    if not file_path.exists():
        return []

    snapshots: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                if raw.get("schema_version") != SCHEMA_VERSION:
                    raise ValueError("unsupported schema_version")
                snapshot = _validate_snapshot(
                    raw.get("symbol"),
                    raw.get("observed_at"),
                    raw.get("value"),
                    raw.get("field_path"),
                    raw.get("unit"),
                )
            except (json.JSONDecodeError, AttributeError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"Invalid OI snapshot at {file_path}:{line_number}: {exc}"
                ) from exc
            snapshots.append(snapshot)
    return snapshots


def append_snapshot(
    path: str | Path,
    *,
    symbol: str,
    observed_at: str | datetime,
    value: float,
    field_path: str,
    unit: str,
) -> bool:
    """Append one observation.

    Returns False for an identical duplicate. Conflicting observations with the
    same symbol/time/field/unit key raise ValueError rather than silently
    overwriting evidence.
    """
    snapshot = _validate_snapshot(symbol, observed_at, value, field_path, unit)
    file_path = Path(path)
    existing = load_snapshots(file_path)
    key_fields = ("symbol", "observed_at", "field_path", "unit")
    for prior in existing:
        if all(prior[key] == snapshot[key] for key in key_fields):
            if prior["value"] == snapshot["value"]:
                return False
            raise ValueError("conflicting OI values for the same snapshot key")

    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(snapshot, sort_keys=True, separators=(",", ":")) + "\n")
    return True


def find_previous_snapshot(
    path: str | Path,
    *,
    symbol: str,
    current_at: str | datetime,
    field_path: str,
    unit: str,
    min_age: timedelta = timedelta(hours=1),
    max_age: timedelta = timedelta(minutes=90),
) -> dict[str, Any] | None:
    """Find the newest compatible prior observation inside an explicit age band.

    Exact field-path and unit matches are required. The current observation is
    not written here. Returns None when no qualifying history exists.
    """
    current_time = _utc_timestamp(current_at)
    if min_age < timedelta(0) or max_age < min_age:
        raise ValueError("require 0 <= min_age <= max_age")

    candidates = []
    for snapshot in load_snapshots(path):
        if snapshot["symbol"] != symbol:
            continue
        if snapshot["field_path"] != field_path or snapshot["unit"] != unit:
            continue
        snapshot_time = _utc_timestamp(snapshot["observed_at"])
        age = current_time - snapshot_time
        if min_age <= age <= max_age:
            candidates.append((snapshot_time, snapshot))

    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]
