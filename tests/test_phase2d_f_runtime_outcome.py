import csv

import storage.signal_logger as signal_logger


def _read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_tp_ladder_persists_across_reload(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="BTC/USDT:USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=105.0, tp2=107.5, tp3=110.0, rr=2.0,
    )

    row = _read_rows(path)[0]
    assert float(row["tp1"]) == 105.0
    assert float(row["tp2"]) == 107.5
    assert float(row["tp3"]) == 110.0


def test_tracker_updates_persisted_lifecycle_without_changing_targets(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="BTC/USDT:USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=105.0, tp2=107.5, tp3=110.0, rr=2.0,
    )

    assert signal_logger.update_signal_tracking(
        "BTC/USDT:USDT", "LONG", 100.0, "OPEN_TP1", new_sl=100.0,
        event_at="2026-01-01T00:05:00+00:00", event_price=105.0,
    )

    row = _read_rows(path)[0]
    assert row["status"] == "OPEN_TP1"
    assert float(row["sl"]) == 100.0
    assert float(row["tp1"]) == 105.0
    assert float(row["tp2"]) == 107.5
    assert float(row["tp3"]) == 110.0
    assert row["tp1_hit_at"] == "2026-01-01T00:05:00+00:00"
    assert row["exit_at"] == ""


def test_terminal_outcome_persists_realized_r_and_exit_price(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="ETH/USDT:USDT", direction="SHORT", entry=200.0, sl=210.0,
        tp1=195.0, tp2=192.5, tp3=190.0, rr=1.0,
    )

    assert signal_logger.update_signal_tracking(
        "ETH/USDT:USDT", "SHORT", 200.0, "TP3_HIT",
        event_at="2026-01-01T01:00:00+00:00", event_price=190.0,
        realized_r=1.0,
    )

    row = _read_rows(path)[0]
    assert row["status"] == "TP3_HIT"
    assert row["tp3_hit_at"] == "2026-01-01T01:00:00+00:00"
    assert row["exit_at"] == "2026-01-01T01:00:00+00:00"
    assert float(row["exit_price"]) == 190.0
    assert float(row["realized_r"]) == 1.0
    assert float(row["tp1"]) == 195.0
    assert float(row["tp2"]) == 192.5
    assert float(row["tp3"]) == 190.0


def test_expired_outcome_persists_terminal_state(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="SOL/USDT:USDT", direction="LONG", entry=100.0, sl=95.0,
        tp1=105.0, tp2=107.5, tp3=110.0,
    )

    assert signal_logger.update_signal_tracking(
        "SOL/USDT:USDT", "LONG", 100.0, "EXPIRED",
        event_at="2026-01-01T02:00:00+00:00", realized_r=0.0,
    )

    row = _read_rows(path)[0]
    assert row["status"] == "EXPIRED"
    assert row["exit_at"] == "2026-01-01T02:00:00+00:00"
    assert float(row["realized_r"]) == 0.0
    assert row["exit_price"] == ""
