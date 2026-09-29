"""Verify that strong score bands are not blocked by a legacy score ceiling.

The old 84 composite ceiling contradicted the configured S threshold (95).
The production fix removes that artificial ceiling, so these tests now
lock in the intended behavior: the S band remains reachable and high
composite scores are not rejected by a separate ceiling.
"""

from pathlib import Path

from config import CONFIG


ROOT = Path(__file__).resolve().parents[1]
SCANNER = ROOT / "scanner_v5.py"


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


def test_score_ceiling_is_removed_and_s_band_is_reachable():
    scanner = SCANNER.read_text(encoding="utf-8")

    assert "signal_score_ceiling" not in CONFIG
    assert '"signal_score_ceiling"' not in scanner
    assert 'CONFIG.get("signal_score_ceiling", 84)' not in scanner

    s_threshold = CONFIG["signal_score_s"]
    assert s_threshold == 95
    assert _grade_score(s_threshold) == "S"


def test_effective_signal_range_has_no_artificial_upper_ceiling():
    scanner = SCANNER.read_text(encoding="utf-8")

    assert CONFIG["min_score"] < CONFIG["signal_score_s"]
    assert "composite >= CONFIG.get(\"signal_score_ceiling\", 84)" not in scanner
    assert _grade_score(CONFIG["min_score"]) in ("B", "C")
    assert _grade_score(CONFIG["signal_score_s"]) == "S"
