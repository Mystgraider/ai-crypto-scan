"""Regression contract for the unresolved score/grade configuration conflict.

Confirmed strategy/configuration contradiction requiring strategy-owner decision.
No threshold is changed by this test.
"""

from config import CONFIG


def test_score_ceiling_contradiction_is_explicit_and_unchanged():
    assert CONFIG["signal_score_s"] > CONFIG["signal_score_ceiling"]
    assert CONFIG["signal_score_s"] == 95
    assert CONFIG["signal_score_ceiling"] == 84
