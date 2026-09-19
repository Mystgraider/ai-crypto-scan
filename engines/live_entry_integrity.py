"""Helpers for revalidating RRCE execution levels against live price."""

from engines.tp_ladder import build_tp_ladder


def revalidate(rrce_engine, direction, live_price, stage4, max_deviation_pct, min_rr):
    """Recalculate executable RRCE levels and attach the staged TP ladder.

    RRCE remains the source of the structural SL/TP contract. The live price
    becomes the executable entry, RR is recalculated from that entry, and the
    structural TP is converted into TP1/TP2/TP3 milestones by the isolated
    Phase 2D-E ladder adapter.
    """
    if not stage4:
        return {"valid": False, "reason": "missing_rrce_stage4"}

    result = rrce_engine.live_entry_levels(
        direction=direction,
        live_price=float(live_price),
        stage4=stage4,
        max_deviation_pct=max_deviation_pct,
        min_rr=min_rr,
    )

    if not result.get("valid"):
        return result

    ladder = build_tp_ladder(
        direction=direction,
        entry=result["entry"],
        structural_tp=result["tp3"],
    )
    result["tp1"] = ladder["tp1"]
    result["tp2"] = ladder["tp2"]
    result["tp3"] = ladder["tp3"]
    result["structural_tp"] = ladder["structural_tp"]
    result["tp1_fraction"] = ladder["tp1_fraction"]
    result["tp2_fraction"] = ladder["tp2_fraction"]
    return result
