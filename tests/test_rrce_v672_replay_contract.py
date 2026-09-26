"""Contract tests for the diagnostic V6.7.2 RRCE replay."""

import inspect

from engines.rrce_v672_legacy import LegacyV672RRCEEngine


def test_v672_replay_is_distinct_from_production_engine():
    engine = LegacyV672RRCEEngine()
    assert engine.__class__.__name__ == "LegacyV672RRCEEngine"
    sig = inspect.signature(engine.evaluate)
    assert list(sig.parameters) == ["df", "direction", "price"]


def test_v672_replay_preserves_soft_bonus_contract():
    source = inspect.getsource(LegacyV672RRCEEngine.evaluate)
    assert "Nothing here HARD BLOCKS a signal by default" in source
    assert 'if fvg or ob:' in source
    assert 'result["bonus"]' in source
