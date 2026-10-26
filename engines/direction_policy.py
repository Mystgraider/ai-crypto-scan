"""Direction discovery policy for scanner orchestration.

BTC is market context, not a direction generator. Direction enablement can be
controlled by LONG_SIGNALS_ENABLED in the production workflow environment.
Set it to "false" to temporarily suppress all LONG candidates while preserving
the existing trend-gate behavior for SHORT candidates.
"""
import os

VALID_DIRECTIONS = ("LONG", "SHORT")


def get_candidate_directions(trend_direction: str, require_trend_gate: bool):
    """Return directions downstream validation is allowed to evaluate.

    When LONG_SIGNALS_ENABLED=false, LONG is removed before downstream checks.
    Otherwise, preserve the normal policy:
      Gate enabled: LONG -> [LONG], SHORT -> [SHORT], NONE -> []
      Gate disabled: any trend state -> [LONG, SHORT]
    """
    if not require_trend_gate:
        directions = list(VALID_DIRECTIONS)
    elif trend_direction in VALID_DIRECTIONS:
        directions = [trend_direction]
    else:
        directions = []

    long_enabled = os.getenv("LONG_SIGNALS_ENABLED", "true").strip().lower() not in {
        "0", "false", "no", "off"
    }
    if not long_enabled:
        directions = [direction for direction in directions if direction != "LONG"]
    return directions
