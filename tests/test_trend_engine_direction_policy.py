from engines.trend_engine import TrendEngine
from config import CONFIG


def _analyze_long(engine):
    return engine.analyze(
        price=105.0,
        ema20=103.0,
        ema50=100.0,
        adx=30.0,
        roc=1.0,
        macd=2.0,
        macd_sig=1.0,
        macd_hist=1.0,
        stoch_k=55.0,
        stoch_d=50.0,
        bb_pct_b=0.60,
    )


def _analyze_short(engine):
    return engine.analyze(
        price=95.0,
        ema20=97.0,
        ema50=100.0,
        adx=30.0,
        roc=-1.0,
        macd=-2.0,
        macd_sig=-1.0,
        macd_hist=-1.0,
        stoch_k=45.0,
        stoch_d=50.0,
        bb_pct_b=0.40,
    )


def test_long_trend_is_soft_evidence_when_gate_disabled(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", False)
    result = _analyze_long(TrendEngine())

    assert result["direction"] == "NONE"
    assert result["direction_hint"] == "LONG"
    assert result["directional_score"] > 50
    assert result["score"] == 50.0


def test_short_trend_is_soft_evidence_when_gate_disabled(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", False)
    result = _analyze_short(TrendEngine())

    assert result["direction"] == "NONE"
    assert result["direction_hint"] == "SHORT"
    assert result["directional_score"] < 50
    assert result["score"] == 50.0


def test_trend_remains_directional_when_gate_enabled(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", True)
    result = _analyze_long(TrendEngine())

    assert result["direction"] == "LONG"
    assert result["score"] > 50
    assert "direction_hint" not in result


def test_short_trend_remains_directional_when_gate_enabled(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", True)
    result = _analyze_short(TrendEngine())

    assert result["direction"] == "SHORT"
    assert result["score"] < 50
    assert "direction_hint" not in result
