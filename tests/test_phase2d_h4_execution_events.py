import csv

import pytest

from storage import signal_logger
from tracker.signal_tracker import SignalTracker


EVENT_AT = "2026-01-01T00:10:00+00:00"


def _save(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal(
        "BTC/USDT", "LONG", 100.0, 98.0, 102.0, 104.0, 106.0,
    )
    return path


def _row(path):
    with path.open(newline="") as f:
        return next(csv.DictReader(f))


def test_tracker_records_explicit_tp1_execution_without_changing_status(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        event_at=EVENT_AT, remaining_position_pct=50.0,
    )

    row = _row(path)
    assert row["status"] == "OPEN"
    assert float(row["tp1_qty_pct"]) == 50.0
    assert float(row["tp1_exit_price"]) == 102.0
    assert float(row["tp1_realized_r"]) == 2.0
    assert row["tp1_executed_at"] == EVENT_AT
    assert float(row["remaining_position_pct"]) == 50.0


def test_tracker_records_tp2_execution_after_tp1(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        event_at=EVENT_AT, remaining_position_pct=50.0,
    )
    tp2_at = "2026-01-01T00:20:00+00:00"
    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP2", 25.0, 104.0, 3.0,
        event_at=tp2_at, remaining_position_pct=25.0,
    )

    row = _row(path)
    assert float(row["tp1_qty_pct"]) == 50.0
    assert float(row["tp2_qty_pct"]) == 25.0
    assert float(row["tp2_exit_price"]) == 104.0
    assert float(row["tp2_realized_r"]) == 3.0
    assert row["tp1_executed_at"] == EVENT_AT
    assert row["tp2_executed_at"] == tp2_at
    assert float(row["remaining_position_pct"]) == 25.0


def test_execution_evidence_does_not_change_tracker_status(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert signal_logger.update_signal_tracking(
        "BTC/USDT", "LONG", 100.0, "OPEN_TP1",
        new_sl=100.0, event_at=EVENT_AT, event_price=102.0,
    )
    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        event_at=EVENT_AT, remaining_position_pct=50.0,
    )

    row = _row(path)
    assert row["status"] == "OPEN_TP1"
    assert row["tp1_hit_at"] == EVENT_AT
    assert row["tp1_executed_at"] == EVENT_AT
    assert float(row["tp1_qty_pct"]) == 50.0


def test_tp_milestone_alone_does_not_create_execution_evidence(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    result = tracker._check(
        "LONG", 102.5, 100.0, 98.0, 102.0, 104.0, 106.0, "OPEN"
    )
    assert result == {"status": "OPEN_TP1", "sl": 100.0}

    row = _row(path)
    assert row["tp1_qty_pct"] == ""
    assert row["tp1_exit_price"] == ""
    assert row["tp1_realized_r"] == ""
    assert row["tp1_executed_at"] == ""


def test_execution_without_remaining_quantity_does_not_infer_it(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        event_at=EVENT_AT,
    )

    row = _row(path)
    assert row["tp1_qty_pct"] == "50.0"
    assert row["tp1_executed_at"] == EVENT_AT
    assert row["remaining_position_pct"] == ""


def test_execution_is_rejected_after_terminal_status(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert signal_logger.update_signal_tracking(
        "BTC/USDT", "LONG", 100.0, "TP3_HIT",
        event_at=EVENT_AT, event_price=106.0, realized_r=3.0,
    )
    assert not tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP3", 25.0, 106.0, 3.0,
        event_at=EVENT_AT,
    )

    row = _row(path)
    assert row["status"] == "TP3_HIT"
    assert row["tp3_qty_pct"] == ""
    assert row["tp3_executed_at"] == ""


def test_duplicate_execution_level_is_not_overwritten(tmp_path, monkeypatch):
    path = _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        event_at=EVENT_AT, remaining_position_pct=50.0,
    )
    assert not tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 40.0, 102.1, 2.1,
        event_at="2026-01-01T00:20:00+00:00", remaining_position_pct=60.0,
    )

    row = _row(path)
    assert float(row["tp1_qty_pct"]) == 50.0
    assert float(row["tp1_exit_price"]) == 102.0
    assert float(row["tp1_realized_r"]) == 2.0
    assert row["tp1_executed_at"] == EVENT_AT


@pytest.mark.parametrize(
    "level,qty,price,realized_r",
    [
        ("BAD", 50.0, 102.0, 2.0),
        ("TP1", 0.0, 102.0, 2.0),
        ("TP1", 101.0, 102.0, 2.0),
        ("TP1", 50.0, 0.0, 2.0),
    ],
)
def test_execution_event_rejects_invalid_inputs(tmp_path, monkeypatch, level, qty, price, realized_r):
    _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    with pytest.raises(ValueError):
        tracker.record_partial_execution(
            "BTC/USDT", "LONG", 100.0, level, qty, price, realized_r,
            event_at=EVENT_AT,
        )


def test_cumulative_execution_quantity_cannot_exceed_100_percent(tmp_path, monkeypatch):
    _save(tmp_path, monkeypatch)
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 60.0, 102.0, 2.0,
        event_at=EVENT_AT,
    )
    with pytest.raises(ValueError, match="cannot exceed 100%"):
        tracker.record_partial_execution(
            "BTC/USDT", "LONG", 100.0, "TP2", 50.0, 104.0, 3.0,
            event_at="2026-01-01T00:20:00+00:00",
        )
