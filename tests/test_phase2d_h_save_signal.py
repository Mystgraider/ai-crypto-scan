import csv


def test_save_signal_initializes_execution_outcome_fields_as_blank(tmp_path, monkeypatch):
    from storage import signal_logger

    signals_file = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(signals_file))

    signal_logger.save_signal(
        "BTC/USDT", "LONG", 100.0, 98.0,
        101.0, 102.0, 103.0,
    )

    with signals_file.open("r", newline="") as f:
        row = next(csv.DictReader(f))

    for field in signal_logger.EXECUTION_OUTCOME_FIELDS:
        assert row[field] == ""
