"""SHORT-only 4H RSI floor (research branch).

Evidence (replay windows 120/90/60/30, 8 symbols, 4h-cooldown production-equivalent
sample): among SHORT candidates that already pass the 1H RSI band and the 15M
not-bearish gate, a closed-candle 4H RSI >= 50 held in discovery, development and an
untouched holdout, remained after controlling for 1H RSI and ADX, and did not widen
the initial SL. Effect size is modest (about +3 to +5pp TP3 in larger samples).

Contract
- Reads the LAST CLOSED 4H candle (``iloc[-2]``), the same value persisted as
  ``rsi_4h`` in replay and live signals. ``iloc[-1]`` is the forming candle and is
  never read.
- Fails closed: a missing/NaN 4H RSI rejects the SHORT with an explicit reason; there
  is no neutral fallback value.
- Never touches LONG, risk, SL/TP, or RRCE.
"""
import math

REASON_FLOOR = "short_rsi_4h_floor"
REASON_UNAVAILABLE = "short_rsi_4h_unavailable"


def validate_short_gate_config(cfg) -> None:
    """Raise ValueError on an unusable SHORT RSI configuration (no silent fallback)."""
    floor = cfg.get("short_rsi_4h_floor", 0.0)
    try:
        floor = float(floor)
    except (TypeError, ValueError):
        raise ValueError(f"short_rsi_4h_floor must be numeric, got {floor!r}")
    if not math.isfinite(floor) or not (0.0 <= floor < 100.0):
        raise ValueError(f"short_rsi_4h_floor must be in [0, 100), got {floor}")
    ceiling = float(cfg.get("short_rsi_ceiling", 100.0))
    if floor and floor >= ceiling:
        raise ValueError(
            f"short_rsi_4h_floor ({floor}) must be below short_rsi_ceiling ({ceiling})"
        )


def short_rsi_4h_check(df_4h, floor):
    """Return (allowed, reason, value). ``floor`` <= 0 or None disables the gate."""
    if floor is None or float(floor) <= 0.0:
        return True, None, None
    if df_4h is None or len(df_4h) < 2 or "rsi" not in getattr(df_4h, "columns", ()):
        return False, REASON_UNAVAILABLE, None
    value = df_4h.iloc[-2]["rsi"]
    try:
        value = float(value)
    except (TypeError, ValueError):
        return False, REASON_UNAVAILABLE, None
    if not math.isfinite(value):
        return False, REASON_UNAVAILABLE, None
    if value < float(floor):
        return False, REASON_FLOOR, value
    return True, None, value
