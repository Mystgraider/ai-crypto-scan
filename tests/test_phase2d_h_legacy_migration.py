import csv


def test_legacy_signal_row_migrates_with_new_execution_fields(tmp_path, monkeypatch):
    from storage import signal_logger

    signals_file = tmp_path / "signals.csv"
    legacy_fields = [
        "timestamp", "symbol", "direction", "entry", "initial_sl", "sl",
        "tp1", "tp2", "tp3", "score", "grade", "rr", "status",
    ]
    with signals_file.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=legacy_fields)
        writer.writeheader()
        writer.writerow({
            "timestamp": "2026-01-01T00:00:00+00:00",
            "symbol": "BTC/USDT",
            "direction": "LONG",
            "entry": "100",
            "initial_sl": "98",
            "sl": "98",
            "tp1": "101",
            "tp2": "102",
            "tp3": "103",
            "score": "80",
            "grade": "A",
            "rr": "1.5",
            "status": "OPEN",
        })

    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(signals_file))
    signal_logger._ensure_file()

    rows = signal_logger.load_signals()
    assert len(rows) == 1
    assert rows[0]["symbol"] == "BTC/USDT"
    assert all(field in rows[0] for field in signal_logger.EXECUTION_OUTCOME_FIELDS)
    assert all(rows[0][field] == "" for field in signal_logger.EXECUTION_OUTCOME_FIELDS)
