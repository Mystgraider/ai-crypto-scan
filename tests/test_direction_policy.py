from engines.direction_policy import get_candidate_directions


def test_gate_disabled_discovers_both_directions():
    for trend_direction in ("NONE", "LONG", "SHORT"):
        assert get_candidate_directions(trend_direction, False) == ["LONG", "SHORT"]


def test_gate_enabled_filters_to_trend_direction():
    assert get_candidate_directions("NONE", True) == []
    assert get_candidate_directions("LONG", True) == ["LONG"]
    assert get_candidate_directions("SHORT", True) == ["SHORT"]


def test_policy_is_explicitly_independent_of_global_config():
    assert get_candidate_directions("LONG", False) == ["LONG", "SHORT"]
    assert get_candidate_directions("SHORT", False) == ["LONG", "SHORT"]
