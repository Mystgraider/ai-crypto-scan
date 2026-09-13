"""Phase 2D-H.5 realized-R accounting from explicit execution evidence."""


def _finite(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if value == value and abs(value) != float("inf") else None


def calculate_realized_r(row: dict) -> float | None:
    """Calculate weighted realized R from explicit execution evidence.

    Per-TP realized-R fields are per-unit R values and are weighted by their
    executed quantity. ``remaining_position_exit_r`` is an explicit contribution
    for the remaining position and is therefore added directly.
    """
    components = []
    for level in ("tp1", "tp2", "tp3"):
        qty = _finite(row.get(f"{level}_qty_pct"))
        r = _finite(row.get(f"{level}_realized_r"))
        if qty is None and r is None:
            continue
        if qty is None or r is None or not 0 < qty <= 100:
            return None
        components.append((qty / 100.0) * r)

    remaining = row.get("remaining_position_exit_r")
    if remaining not in (None, ""):
        remaining = _finite(remaining)
        if remaining is None:
            return None
        components.append(remaining)

    if not components:
        return None
    return round(sum(components), 6)
