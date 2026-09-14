from engines.direction_policy import get_candidate_directions


def test_gate_disabled_discovers_both_directions_for_every_trend_state():
    for trend_direction in ("LONG", "SHORT", "NONE", "UNKNOWN"):
        assert get_candidate_directions(trend_direction, False) == ["LONG", "SHORT"]


def test_gate_enabled_preserves_directional_gate():
    assert get_candidate_directions("LONG", True) == ["LONG"]
    assert get_candidate_directions("SHORT", True) == ["SHORT"]
    assert get_candidate_directions("NONE", True) == []
    assert get_candidate_directions("UNKNOWN", True) == []
