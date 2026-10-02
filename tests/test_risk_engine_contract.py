from engines.risk_engine import RiskEngine


def test_long_fallback_returns_ordered_tp_ladder():
    result = RiskEngine().calculate("LONG", 100.0, 2.0)
    assert result is not None
    assert result["sl"] < result["entry"] < result["tp1"] < result["tp2"] < result["tp3"]
    assert result["rr"] >= 2.0


def test_short_fallback_returns_ordered_tp_ladder():
    result = RiskEngine().calculate("SHORT", 100.0, 2.0)
    assert result is not None
    assert result["tp3"] < result["tp2"] < result["tp1"] < result["entry"] < result["sl"]
    assert result["rr"] >= 2.0


def test_fallback_ladder_contract_rejects_non_progressing_levels():
    # Regression contract: TP1 may never equal SL or sit on the loss side.
    result = RiskEngine().calculate("LONG", 100.0, 0.001)
    assert result is None
