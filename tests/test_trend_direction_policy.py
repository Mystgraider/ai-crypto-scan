from engines.direction_policy import get_candidate_directions
from config import CONFIG


def test_gate_disabled_always_exposes_both_directions(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", False)
    for trend_direction in ("LONG", "SHORT", "NONE", "UNKNOWN"):
        assert get_candidate_directions(trend_direction, False) == ["LONG", "SHORT"]


def test_gate_enabled_keeps_directional_gate(monkeypatch):
    monkeypatch.setitem(CONFIG, "require_trend_gate", True)
    assert get_candidate_directions("LONG", True) == ["LONG"]
    assert get_candidate_directions("SHORT", True) == ["SHORT"]
    assert get_candidate_directions("NONE", True) == []
