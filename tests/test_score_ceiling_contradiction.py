"""Regression contract for the unresolved score/grade configuration conflict."""

from config import CONFIG
from scanner_v5 import grade_score


def test_score_ceiling_contradiction_is_explicit_and_unchanged():
    """Record the contradiction without selecting a strategy resolution."""
    assert CONFIG["signal_score_s"] > CONFIG["signal_score_ceiling"]
    assert grade_score(CONFIG["signal_score_s"]) == "S"
    assert CONFIG["signal_score_ceiling"] < CONFIG["signal_score_s"]

    # This is a confirmed configuration contradiction requiring a strategy-owner decision.
    # Thresholds are intentionally not changed by this test.
