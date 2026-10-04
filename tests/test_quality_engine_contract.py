from engines.quality_engine import QualityEngine


def test_quality_rejects_invalid_direction():
    engine = QualityEngine()
    assert engine.score(1.5, 55.0, "SIDEWAYS") == 0.0


def test_quality_fails_closed_on_nan_inputs():
    engine = QualityEngine()
    assert engine.score(float("nan"), 55.0, "LONG") == 0.0
    assert engine.score(1.5, float("nan"), "LONG") == 0.0


def test_quality_fails_closed_on_non_numeric_inputs():
    engine = QualityEngine()
    assert engine.score("bad", 55.0, "LONG") == 0.0
    assert engine.score(1.5, "bad", "LONG") == 0.0


def test_quality_valid_contract_is_unchanged():
    engine = QualityEngine()
    assert engine.score(1.2, 57.0, "LONG") == 86.25
    assert engine.score(1.2, 43.0, "SHORT") == 100.0
