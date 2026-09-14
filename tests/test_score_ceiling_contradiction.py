"""Document the current score-threshold contradiction without tuning it.

Current configuration has S >= 95 while composite >= 84 is rejected.
This is a confirmed strategy/configuration contradiction requiring
strategy-owner decision. This test documents the state only.
"""

from config import CONFIG


def _grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]:
        return "S"
    if score >= CONFIG["signal_score_a"]:
        return "A"
    if score >= CONFIG["signal_score_b"]:
        return "B"
    if score >= CONFIG["signal_score_c"]:
        return "C"
    return "D"


def test_score_ceiling_contradiction_requires_owner_decision():
    s_threshold = CONFIG["signal_score_s"]
    ceiling = CONFIG["signal_score_ceiling"]

    assert s_threshold > ceiling
    assert _grade_score(s_threshold) == "S"
    assert s_threshold >= ceiling


def test_effective_signal_range_before_ceiling():
    min_score = CONFIG["min_score"]
    ceiling = CONFIG["signal_score_ceiling"]

    assert min_score < ceiling
    assert all(_grade_score(score) in ("B", "A") for score in range(min_score, ceiling))
