"""Regression tests for independent LONG/SHORT direction discovery."""

from config import CONFIG
from engines.direction_policy import get_candidate_directions


def test_trend_gate_disabled_discovers_both_directions():
    for trend_direction in ("NONE", "LONG", "SHORT"):
        assert get_candidate_directions(trend_direction, False) == ["LONG", "SHORT"]


def test_trend_gate_enabled_still_filters():
    assert get_candidate_directions("NONE", True) == []
    assert get_candidate_directions("LONG", True) == ["LONG"]
    assert get_candidate_directions("SHORT", True) == ["SHORT"]


def test_policy_does_not_depend_on_config_global():
    """The production policy receives the gate explicitly."""
    original = CONFIG.get("require_trend_gate")
    try:
        CONFIG["require_trend_gate"] = True
        assert get_candidate_directions("LONG", False) == ["LONG", "SHORT"]
        CONFIG["require_trend_gate"] = False
        assert get_candidate_directions("LONG", True) == ["LONG"]
    finally:
        CONFIG["require_trend_gate"] = original
