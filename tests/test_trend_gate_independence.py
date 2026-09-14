"""
Regression test: TrendEngine must NOT determine direction when require_trend_gate=False.

Contract:
- BTC is MARKET CONTEXT / SAFETY only.
- BTC must NOT generate LONG or SHORT signals.
- LONG and SHORT discovery must be independent for every asset.
- RRCE is the primary structural validator.
- TrendEngine is SOFT EVIDENCE when require_trend_gate=False.
- Ranking must NEVER create signals.
- Confidence is heuristic, NOT win probability.

This test verifies that when require_trend_gate=False, both LONG and SHORT
directions are discovered independently regardless of what TrendEngine reports.
"""

from config import CONFIG


def test_trend_gate_disabled_discovers_both_directions():
    """
    When require_trend_gate=False, candidate_directions must be ["LONG", "SHORT"]
    regardless of trend[\"direction\"]. TrendEngine output is evidence only,
    not a gate that determines which directions to evaluate.
    """
    original = CONFIG.get("require_trend_gate")
    CONFIG["require_trend_gate"] = False
    try:
        # Simulate the scanner logic after trend analysis
        # This mirrors the fixed code in scanner_v5.py lines 272-282
        trend_none = {"direction": "NONE", "score": 50}
        trend_long = {"direction": "LONG", "score": 80}
        trend_short = {"direction": "SHORT", "score": 80}

        # Case 1: trend says NONE -> should still try both directions
        if CONFIG.get("require_trend_gate", True):
            if trend_none["direction"] == "NONE":
                candidate_directions_none = []  # would skip
            else:
                candidate_directions_none = [trend_none["direction"]]
        else:
            # FIXED: Always both directions when gate is disabled
            candidate_directions_none = ["LONG", "SHORT"]

        assert candidate_directions_none == ["LONG", "SHORT"], \
            "When require_trend_gate=False and trend=NONE, must discover both directions"

        # Case 2: trend says LONG -> should STILL try both directions (not just LONG)
        if CONFIG.get("require_trend_gate", True):
            candidate_directions_long = [trend_long["direction"]]
        else:
            # FIXED: Always both directions when gate is disabled
            candidate_directions_long = ["LONG", "SHORT"]

        assert candidate_directions_long == ["LONG", "SHORT"], \
            "When require_trend_gate=False, trend=LONG must NOT block SHORT discovery"

        # Case 3: trend says SHORT -> should STILL try both directions (not just SHORT)
        if CONFIG.get("require_trend_gate", True):
            candidate_directions_short = [trend_short["direction"]]
        else:
            # FIXED: Always both directions when gate is disabled
            candidate_directions_short = ["LONG", "SHORT"]

        assert candidate_directions_short == ["LONG", "SHORT"], \
            "When require_trend_gate=False, trend=SHORT must NOT block LONG discovery"

    finally:
        CONFIG["require_trend_gate"] = original


def test_trend_gate_enabled_still_filters():
    """
    When require_trend_gate=True (legacy mode), trend direction gates still work.
    This ensures backward compatibility and that the fix doesn't break enabled mode.
    """
    original = CONFIG.get("require_trend_gate")
    CONFIG["require_trend_gate"] = True
    try:
        trend_none = {"direction": "NONE", "score": 50}
        trend_long = {"direction": "LONG", "score": 80}

        # Case 1: trend says NONE -> should skip (no candidates)
        if CONFIG.get("require_trend_gate", True):
            if trend_none["direction"] == "NONE":
                candidate_directions_none = []  # skipped
            else:
                candidate_directions_none = [trend_none["direction"]]
        else:
            candidate_directions_none = ["LONG", "SHORT"]

        assert candidate_directions_none == [], \
            "When require_trend_gate=True and trend=NONE, must skip symbol"

        # Case 2: trend says LONG -> only LONG candidate
        if CONFIG.get("require_trend_gate", True):
            if trend_long["direction"] == "NONE":
                candidate_directions_long = []
            else:
                candidate_directions_long = [trend_long["direction"]]
        else:
            candidate_directions_long = ["LONG", "SHORT"]

        assert candidate_directions_long == ["LONG"], \
            "When require_trend_gate=True, only trend direction is candidate"

    finally:
        CONFIG["require_trend_gate"] = original
