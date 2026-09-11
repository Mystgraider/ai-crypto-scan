from pathlib import Path

import storage.signal_logger as signal_logger


def _base_kwargs():
    return {
        "symbol": "BTC/USDT:USDT",
        "direction": "LONG",
        "entry": 100.0,
        "sl": 95.0,
        "tp1": 105.0,
        "tp2": 110.0,
        "tp3": 115.0,
        "score": 84.0,
        "grade": "A",
        "rr": 3.0,
        "adx": 25.0,
        "rsi": 58.0,
        "rel_volume": 1.2,
        "spike_tier": "NORMAL",
        "mtf_status": "CONFIRMED",
        "btc_regime": "BULL",
        "rs_label": "STRONG",
        "funding_pct": "0.01",
        "oi_signal": "CONFIRMED",
        "beta_label": "NORMAL",
    }


def test_save_signal_persists_ai_calibration_fields(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        **_base_kwargs(),
        ai_rank_score=91.25,
        ai_rank_raw=91.2467,
        confidence=78.5,
    )

    rows = signal_logger._read_rows()
    assert len(rows) == 1
    row = rows[0]
    assert row["score"] == "84.0"
    assert row["ai_rank_score"] == "91.25"
    assert row["ai_rank_raw"] == "91.25"
    assert row["confidence"] == "78.5"
    assert row["initial_sl"] == "95.0"


def test_legacy_csv_schema_is_migrated_before_append(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    path.write_text(
        "timestamp,symbol,direction,entry,sl,tp1,tp2,tp3,score,grade,rr,adx,rsi,rel_volume,spike_tier,mtf_status,btc_regime,rs_label,funding_pct,oi_signal,beta_label\n"
        "2026-01-01T00:00:00+00:00,BTC/USDT:USDT,LONG,100,95,105,110,115,80,A,3,25,55,1.1,NORMAL,CONFIRMED,BULL,STRONG,0.01,CONFIRMED,NORMAL\n"
    )

    signal_logger.save_signal(**_base_kwargs())

    rows = signal_logger._read_rows()
    assert len(rows) == 2
    assert rows[0]["symbol"] == "BTC/USDT:USDT"
    assert rows[0]["ai_rank_score"] == ""
    assert rows[0]["confidence"] == ""
    assert rows[0]["initial_sl"] == ""
    assert rows[1]["initial_sl"] == "95.0"


def test_legacy_ai_fields_are_optional_for_backward_compatibility(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(**_base_kwargs())

    rows = signal_logger._read_rows()
    assert rows[0]["ai_rank_score"] == ""
    assert rows[0]["ai_rank_raw"] == ""
    assert rows[0]["confidence"] == ""
