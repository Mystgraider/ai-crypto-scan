import pytest

from analytics.execution_outcome import calculate_realized_r
from storage import signal_logger
from tracker.signal_tracker import SignalTracker


def _row(**updates):
    row = {
        "tp1_qty_pct": "",
        "tp2_qty_pct": "",
        "tp3_qty_pct": "",
        "tp1_realized_r": "",
        "tp2_realized_r": "",
        "tp3_realized_r": "",
        "remaining_position_pct": "",
        "remaining_position_exit_r": "",
    }
    row.update(updates)
    return row


def test_weighted_realized_r_50_25_25():
    row = _row(
        tp1_qty_pct="50", tp1_realized_r="2",
        tp2_qty_pct="25", tp2_realized_r="3",
        tp3_qty_pct="25", tp3_realized_r="4",
    )
    assert calculate_realized_r(row) == pytest.approx(2.75)


def test_realized_r_with_remaining_position_exit():
    row = _row(
        tp1_qty_pct="50", tp1_realized_r="2",
        remaining_position_pct="50",
    )
    assert calculate_realized_r(row, remaining_exit_r=0.0) == pytest.approx(1.0)


def test_realized_r_requires_complete_position_evidence():
    row = _row(tp1_qty_pct="50", tp1_realized_r="2")
    assert calculate_realized_r(row) is None


def test_realized_r_rejects_inconsistent_remaining_position():
    row = _row(
        tp1_qty_pct="50", tp1_realized_r="2",
        remaining_position_pct="40",
    )
    assert calculate_realized_r(row, remaining_exit_r=0.0) is None


def test_tracker_uses_partial_realized_r_when_execution_is_complete(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal(
        "BTC/USDT", "LONG", 100.0, 98.0, 102.0, 104.0, 106.0,
    )
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        remaining_position_pct=50.0,
    )
    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP2", 25.0, 104.0, 3.0,
        remaining_position_pct=25.0,
    )
    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP3", 25.0, 106.0, 4.0,
        remaining_position_pct=0.0,
    )

    row = signal_logger.load_signals()[0]
    assert tracker._execution_realized_r(
        row, "LONG", 100.0, 98.0, 106.0
    ) == pytest.approx(2.75)


def test_tracker_does_not_fabricate_total_r_from_incomplete_execution():
    tracker = SignalTracker.__new__(SignalTracker)
    row = _row(tp1_qty_pct="50", tp1_realized_r="2")
    assert tracker._execution_realized_r(
        row, "LONG", 100.0, 98.0, 106.0
    ) is None


def test_signal_logger_remaining_position_consistency(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal(
        "BTC/USDT", "LONG", 100.0, 98.0, 102.0, 104.0, 106.0,
    )
    tracker = SignalTracker.__new__(SignalTracker)

    assert tracker.record_partial_execution(
        "BTC/USDT", "LONG", 100.0, "TP1", 50.0, 102.0, 2.0,
        remaining_position_pct=50.0,
    )
    with pytest.raises(ValueError, match="remaining_position_pct"):
        tracker.record_partial_execution(
            "BTC/USDT", "LONG", 100.0, "TP2", 25.0, 104.0, 3.0,
            remaining_position_pct=40.0,
        )
