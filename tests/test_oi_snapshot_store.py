from datetime import datetime, timedelta, timezone

import pytest

from storage.oi_snapshot_store import (
    append_snapshot,
    find_previous_snapshot,
    load_snapshots,
)


BASE = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def put(path, *, at=BASE, value=100.0, symbol="BTC/USDT:USDT",
        field_path="openInterestAmount", unit="contracts"):
    return append_snapshot(
        path,
        symbol=symbol,
        observed_at=at,
        value=value,
        field_path=field_path,
        unit=unit,
    )


def test_missing_store_loads_as_empty(tmp_path):
    assert load_snapshots(tmp_path / "missing.jsonl") == []


def test_append_creates_parent_and_normalizes_timestamp(tmp_path):
    path = tmp_path / "nested" / "oi.jsonl"
    assert put(path, at="2026-10-24T12:00:00+00:00") is True
    row = load_snapshots(path)[0]
    assert row["observed_at"] == "2026-10-24T12:00:00Z"
    assert row["value"] == 100.0


def test_identical_duplicate_is_idempotent(tmp_path):
    path = tmp_path / "oi.jsonl"
    assert put(path) is True
    assert put(path) is False
    assert len(load_snapshots(path)) == 1


def test_conflicting_duplicate_is_rejected(tmp_path):
    path = tmp_path / "oi.jsonl"
    put(path, value=100)
    with pytest.raises(ValueError, match="conflicting"):
        put(path, value=101)


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), float("-inf")])
def test_non_positive_or_non_finite_values_are_rejected(tmp_path, value):
    with pytest.raises(ValueError):
        put(tmp_path / "oi.jsonl", value=value)


def test_naive_timestamp_is_rejected(tmp_path):
    with pytest.raises(ValueError, match="timezone"):
        put(tmp_path / "oi.jsonl", at=datetime(2026, 10, 24, 12, 0))


def test_finds_newest_compatible_snapshot_in_age_band(tmp_path):
    path = tmp_path / "oi.jsonl"
    put(path, at=BASE - timedelta(hours=2), value=80)
    put(path, at=BASE - timedelta(minutes=70), value=95)
    put(path, at=BASE - timedelta(minutes=30), value=99)
    found = find_previous_snapshot(
        path, symbol="BTC/USDT:USDT", current_at=BASE,
        field_path="openInterestAmount", unit="contracts",
    )
    assert found is not None
    assert found["value"] == 95.0


def test_never_matches_different_field_path_or_unit(tmp_path):
    path = tmp_path / "oi.jsonl"
    put(path, at=BASE - timedelta(minutes=70), value=500,
        field_path="openInterestValue", unit="USDT")
    put(path, at=BASE - timedelta(minutes=65), value=200,
        field_path="openInterestAmount", unit="base_asset")
    assert find_previous_snapshot(
        path, symbol="BTC/USDT:USDT", current_at=BASE,
        field_path="openInterestAmount", unit="contracts",
    ) is None


def test_no_snapshot_outside_age_band_returns_none(tmp_path):
    path = tmp_path / "oi.jsonl"
    put(path, at=BASE - timedelta(minutes=91))
    assert find_previous_snapshot(
        path, symbol="BTC/USDT:USDT", current_at=BASE,
        field_path="openInterestAmount", unit="contracts",
    ) is None


def test_malformed_persisted_line_fails_loudly(tmp_path):
    path = tmp_path / "oi.jsonl"
    path.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid OI snapshot"):
        load_snapshots(path)
