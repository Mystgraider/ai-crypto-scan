"""Direction discovery policy for scanner orchestration.

BTC is market context, not a direction generator. Direction enablement can be
controlled independently for LONG and SHORT so research replays can isolate one
strategy without changing production defaults.
"""
import os

VALID_DIRECTIONS = ("LONG", "SHORT")


def _enabled(name: str) -> bool:
    return os.getenv(name, "true").strip().lower() not in {
        "0", "false", "no", "off"
    }


def get_candidate_directions(trend_direction: str, require_trend_gate: bool):
    """Return directions downstream validation is allowed to evaluate.

    Defaults remain unchanged: both directions are enabled when the trend gate
    is disabled. Research replays can set BACKTEST_DIRECTION indirectly through
    LONG_SIGNALS_ENABLED / SHORT_SIGNALS_ENABLED to isolate one side.
    """
    if not require_trend_gate:
        directions = list(VALID_DIRECTIONS)
    elif trend_direction in VALID_DIRECTIONS:
        directions = [trend_direction]
    else:
        directions = []

    if not _enabled("LONG_SIGNALS_ENABLED"):
        directions = [d for d in directions if d != "LONG"]
    if not _enabled("SHORT_SIGNALS_ENABLED"):
        directions = [d for d in directions if d != "SHORT"]
    return directions
