import csv
import json

import storage.signal_logger as signal_logger


def test_save_signal_persists_ai_attribution(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    attribution = {
        "attribution_version": "2D-D1",
        "components": {
            "trend": 28.0,
            "quality": 17.6,
            "rs": 9.0,
            "oi": 5.56,
            "rr": 3.2,
            "sr": 0.0,
            "category": 1.33,
        },
        "ai_rank_raw": 64.69,
        "ai_rank_score": 64.69,
    }

    signal_logger.save_signal(
        symbol="BTC/USDT:USDT",
        direction="LONG",
        entry=100.0,
        sl=95.0,
        tp1=105.0,
        tp2=110.0,
        tp3=115.0,
        ai_rank_score=64.69,
        ai_rank_raw=64.69,
        confidence=78.5,
        ai_attribution=attribution,
    )

    with path.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))

    assert json.loads(row["ai_attribution"]) == attribution
    assert row["ai_rank_score"] == "64.69"
    assert row["ai_rank_raw"] == "64.69"
    assert row["confidence"] == "78.5"


def test_save_signal_keeps_attribution_optional(tmp_path, monkeypatch):
    path = tmp_path / "signals.csv"
    monkeypatch.setattr(signal_logger, "SIGNALS_FILE", str(path))

    signal_logger.save_signal(
        symbol="ETH/USDT:USDT",
        direction="LONG",
        entry=100.0,
        sl=95.0,
        tp1=105.0,
        tp2=110.0,
        tp3=115.0,
    )

    with path.open(newline="", encoding="utf-8") as f:
        row = next(csv.DictReader(f))

    assert row["ai_attribution"] == ""
