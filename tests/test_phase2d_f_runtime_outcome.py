import csv
import storage.signal_logger as signal_logger

def _read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))

def test_tp_ladder_persists_across_reload(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal("BTC/USDT:USDT", "LONG", 100.0, 95.0, 105.0, 107.5, 110.0, rr=2.0)
    row = _read_rows(path)[0]
    assert [float(row[k]) for k in ("tp1", "tp2", "tp3")] == [105.0, 107.5, 110.0]

def test_tracker_updates_preserve_ladder(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal("BTC/USDT:USDT", "LONG", 100.0, 95.0, 105.0, 107.5, 110.0, rr=2.0)
    assert signal_logger.update_signal_tracking("BTC/USDT:USDT", "LONG", 100.0, "OPEN_TP1", new_sl=100.0, event_at="2026-01-01T00:05:00+00:00", event_price=105.0)
    row = _read_rows(path)[0]
    assert row["status"] == "OPEN_TP1"
    assert float(row["sl"]) == 100.0
    assert [float(row[k]) for k in ("tp1", "tp2", "tp3")] == [105.0, 107.5, 110.0]

def test_terminal_outcome_persists(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal("ETH/USDT:USDT", "SHORT", 200.0, 210.0, 195.0, 192.5, 190.0, rr=1.0)
    assert signal_logger.update_signal_tracking("ETH/USDT:USDT", "SHORT", 200.0, "TP3_HIT", event_at="2026-01-01T01:00:00+00:00", event_price=190.0, realized_r=1.0)
    row = _read_rows(path)[0]
    assert row["status"] == "TP3_HIT"
    assert row["exit_at"] == "2026-01-01T01:00:00+00:00"
    assert float(row["exit_price"]) == 190.0
    assert float(row["realized_r"]) == 1.0
    assert float(row["tp3"]) == 190.0

def test_expired_outcome_persists(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))
    signal_logger.save_signal("SOL/USDT:USDT", "LONG", 100.0, 95.0, 105.0, 107.5, 110.0)
    assert signal_logger.update_signal_tracking("SOL/USDT:USDT", "LONG", 100.0, "EXPIRED", event_at="2026-01-01T02:00:00+00:00", realized_r=0.0)
    row = _read_rows(path)[0]
    assert row["status"] == "EXPIRED"
    assert row["exit_at"] == "2026-01-01T02:00:00+00:00"
    assert float(row["realized_r"]) == 0.0
