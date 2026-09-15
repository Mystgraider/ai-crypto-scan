"""Direction discovery policy for scanner orchestration."""

VALID_DIRECTIONS = ("LONG", "SHORT")


def get_candidate_directions(trend_direction: str, require_trend_gate: bool):
    """Return directions allowed for downstream structural validation.

    With the trend gate disabled, TrendEngine is evidence only, so both
    directions are independently discoverable regardless of trend_direction.
    With the gate enabled, only an explicit LONG or SHORT trend is allowed.
    """
    if not require_trend_gate:
        return list(VALID_DIRECTIONS)
    if trend_direction in VALID_DIRECTIONS:
        return [trend_direction]
    return []
