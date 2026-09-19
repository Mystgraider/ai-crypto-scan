"""Direction discovery policy for scanner orchestration.

BTC is market context, not a direction generator. When the trend gate is
 disabled, TrendEngine is evidence only and downstream structural validation
must evaluate both LONG and SHORT independently.
"""

VALID_DIRECTIONS = ("LONG", "SHORT")


def get_candidate_directions(trend_direction: str, require_trend_gate: bool):
    """Return directions that downstream validation is allowed to evaluate.

    Gate enabled:
      LONG  -> [LONG]
      SHORT -> [SHORT]
      NONE  -> []

    Gate disabled:
      any trend state -> [LONG, SHORT]
    """
    if not require_trend_gate:
        return list(VALID_DIRECTIONS)
    if trend_direction in VALID_DIRECTIONS:
        return [trend_direction]
    return []
