"""RRCE structural-target TP ladder adapter (Phase 2D-E)."""


def build_tp_ladder(direction, entry, structural_tp, *, tp1_fraction=0.50, tp2_fraction=0.75):
    """Build ordered TP1/TP2/TP3 milestones without changing RRCE target logic."""
    if direction not in {"LONG", "SHORT"}:
        raise ValueError("direction must be LONG or SHORT")

    entry = float(entry)
    structural_tp = float(structural_tp)
    if entry <= 0 or structural_tp <= 0:
        raise ValueError("entry and structural_tp must be positive")
    if not 0 < tp1_fraction < tp2_fraction <= 1:
        raise ValueError("fractions must satisfy 0 < tp1 < tp2 <= 1")

    reward = structural_tp - entry if direction == "LONG" else entry - structural_tp
    if reward <= 0:
        raise ValueError("structural_tp must be in the profit direction")

    if direction == "LONG":
        tp1 = entry + reward * tp1_fraction
        tp2 = entry + reward * tp2_fraction
        tp3 = structural_tp
        valid = entry < tp1 < tp2 <= tp3
    else:
        tp1 = entry - reward * tp1_fraction
        tp2 = entry - reward * tp2_fraction
        tp3 = structural_tp
        valid = entry > tp1 > tp2 >= tp3

    if not valid:
        raise ValueError("invalid TP ordering")

    return {
        "entry": entry,
        "tp1": tp1,
        "tp2": tp2,
        "tp3": tp3,
        "structural_tp": structural_tp,
        "tp1_fraction": float(tp1_fraction),
        "tp2_fraction": float(tp2_fraction),
    }
