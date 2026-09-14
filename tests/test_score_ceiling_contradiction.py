"""
Documentation test: Score ceiling vs S-grade threshold contradiction.

Current config (config.py):
    "signal_score_s": 95,      # S grade requires score >= 95
    "signal_score_a": 82,      # A grade requires score >= 82
    "signal_score_b": 70,      # B grade requires score >= 70
    "signal_score_c": 65,      # C grade requires score >= 65
    "signal_score_ceiling": 84, # Hard reject composite >= 84

CONTRADICTION:
    - S grade requires score >= 95
    - But signal_score_ceiling = 84 hard-rejects any composite >= 84
    - Therefore S grade is UNREACHABLE by design
    
    This means:
    - Scores 84+ are rejected as "overextended" (likely already-flown)
    - Scores 82-83 can achieve A grade (if they pass all gates)
    - Scores 70-81 can achieve B grade (best historical WR per V6.1 comment)
    - Scores 65-69 can achieve C grade (but blocked by min_score=70)
    - Scores < 70 get D grade and are rejected

RESOLUTION OPTIONS (do not implement without explicit authorization):
    1. Accept the contradiction: S grade is aspirational/documentation only,
       actual maximum achievable grade is A (82-83 range).
    
    2. Raise ceiling to 94: Allow A and potentially S grades through, but
       this contradicts V6.3 data showing 84+ = likely already-flown.
    
    3. Lower S threshold to 83: Make S grade achievable (83-84 range),
       but this dilutes the meaning of S grade.
    
    4. Remove ceiling entirely: Not recommended — contradicts V6.3 fix
       that identified score paradox (84+ had 0% WR in backtest).

RECOMMENDED: Option 1 (status quo). The contradiction is intentional based
on V6.3 data analysis. S grade exists as documentation of exceptional
theoretical quality, but practical signals cap at A grade (82-83).
"""

from config import CONFIG


def test_s_grade_is_unreachable_due_to_ceiling():
    """
    Verify that S grade threshold (95) exceeds signal_score_ceiling (84),
    making S grade unreachable by design.
    """
    s_threshold = CONFIG["signal_score_s"]  # 95
    ceiling = CONFIG.get("signal_score_ceiling", 84)  # 84
    
    assert s_threshold > ceiling, \
        f"S grade threshold ({s_threshold}) must exceed ceiling ({ceiling}) " \
        f"to document the intentional contradiction"
    
    # No score can be both >= 95 (S grade) AND < 84 (below ceiling)
    # Therefore S grade signals are impossible to fire
    for score in range(0, 101):
        grade = _grade_score(score)
        is_rejected = score >= ceiling
        
        if grade == "S":
            assert is_rejected, \
                f"Score {score} gives S grade but should be rejected by ceiling"
    
    # Maximum achievable grade is A (82-83 range)
    assert _grade_score(82) == "A"
    assert _grade_score(83) == "A"
    assert _grade_score(84) == "A"  # Would be A, but rejected by ceiling


def test_score_distribution_with_ceiling():
    """
    Document the effective score distribution given the ceiling.
    """
    ceiling = CONFIG.get("signal_score_ceiling", 84)
    min_score = CONFIG["min_score"]  # 70
    
    # Rejected scores
    for score in range(0, min_score):
        assert _grade_score(score) in ("D", "C"), f"Score {score} should be low grade"
    
    # Achievable grades (70 to 83)
    for score in range(min_score, ceiling):
        grade = _grade_score(score)
        assert grade in ("B", "A"), \
            f"Score {score} should achieve B or A grade, got {grade}"
    
    # Rejected by ceiling (84+)
    for score in range(ceiling, 100):
        grade = _grade_score(score)
        # These would be A or S grade, but rejected by ceiling
        assert grade in ("A", "S"), \
            f"Score {score} should be A or S grade before ceiling rejection"


def _grade_score(score: float) -> str:
    """Mirror of scanner_v5.py grade_score function."""
    if score >= CONFIG["signal_score_s"]: return "S"
    if score >= CONFIG["signal_score_a"]: return "A"
    if score >= CONFIG["signal_score_b"]: return "B"
    if score >= CONFIG["signal_score_c"]: return "C"
    return "D"
