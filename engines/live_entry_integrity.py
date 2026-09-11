"""Helpers for revalidating RRCE execution levels against live price."""


def revalidate(rrce_engine, direction, live_price, stage4, max_deviation_pct, min_rr):
    """Recalculate executable levels from the original RRCE Stage 4 setup.

    RRCE remains the source of structural SL/TP levels; the live price becomes
    the executable entry and RR is recalculated from that entry.
    """
    if not stage4:
        return {"valid": False, "reason": "missing_rrce_stage4"}

    return rrce_engine.live_entry_levels(
        direction=direction,
        live_price=float(live_price),
        stage4=stage4,
        max_deviation_pct=max_deviation_pct,
        min_rr=min_rr,
    )
