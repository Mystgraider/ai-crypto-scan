"""Phase 2D-H.5 canonical execution outcome accounting.

Execution evidence is authoritative when it forms a complete position
accounting (100% of quantity explicitly accounted for). Otherwise the
aggregator falls back to the terminal realized_r value, then the legacy
entry/exit/initial-SL calculation.

No TP milestone or lifecycle status is treated as proof of execution.
"""

from dataclasses import dataclass
from math import isfinite

RESOLVED_STATUSES = {"TP3_HIT", "SL_HIT"}
EXECUTION_LEVELS = ("TP1", "TP2", "TP3")
VALID_DIRECTIONS = {"LONG", "SHORT"}


@dataclass(frozen=True)
class CanonicalOutcome:
    """Canonical trade outcome and the evidence source used."""

    resolved: bool
    realized_r: float | None
    source: str
    reason: str = ""


def _number(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _explicit_execution(signal):
    """Return a complete explicit-execution R, or None when incomplete/invalid."""
    parts = []
    total_qty = 0.0
    any_execution = False

    for level in EXECUTION_LEVELS:
        qty = _number(signal.get(f"{level.lower()}_qty_pct"))
        exit_price = _number(signal.get(f"{level.lower()}_exit_price"))
        realized_r = _number(signal.get(f"{level.lower()}_realized_r"))
        executed_at = signal.get(f"{level.lower()}_executed_at")

        if any(value not in (None, "") for value in (qty, exit_price, realized_r, executed_at)):
            any_execution = True

        if qty is None and exit_price is None and realized_r is None and executed_at in (None, ""):
            continue

        if None in (qty, exit_price, realized_r) or executed_at in (None, ""):
            return None, "incomplete execution evidence"
        if not (0.0 < qty <= 100.0) or exit_price <= 0.0:
            return None, "invalid execution evidence"

        total_qty += qty
        if total_qty > 100.0 + 1e-9:
            return None, "execution quantity exceeds 100%"
        parts.append((qty, realized_r))

    remaining_pct = _number(signal.get("remaining_position_pct"))
    remaining_r = _number(signal.get("remaining_position_exit_r"))
    if remaining_pct is not None or remaining_r is not None:
        any_execution = True
        if remaining_pct is None:
            return None, "incomplete remaining-position evidence"
        if not (0.0 <= remaining_pct <= 100.0):
            return None, "invalid remaining-position quantity"
        if remaining_pct > 0.0 and remaining_r is None:
            return None, "incomplete remaining-position evidence"
        if abs((total_qty + remaining_pct) - 100.0) > 1e-9:
            return None, "execution quantities do not account for 100%"
        if remaining_pct > 0.0:
            parts.append((remaining_pct, remaining_r))
    elif any_execution and abs(total_qty - 100.0) > 1e-9:
        return None, "remaining position is not explicitly accounted for"

    if not any_execution:
        return None, "no explicit execution evidence"
    if abs(total_qty - 100.0) > 1e-9 and remaining_pct is None:
        return None, "execution quantities do not account for 100%"

    return round(sum((qty / 100.0) * r for qty, r in parts), 6), ""


def _terminal_realized_r(signal):
    if signal.get("status") not in RESOLVED_STATUSES:
        return None
    raw = _number(signal.get("realized_r"))
    if raw is not None:
        return raw
    return None


def _legacy_realized_r(signal):
    if signal.get("status") not in RESOLVED_STATUSES:
        return None
    direction = signal.get("direction")
    if direction not in VALID_DIRECTIONS:
        return None

    entry = _number(signal.get("entry"))
    exit_price = _number(signal.get("exit_price"))
    initial_sl = _number(signal.get("initial_sl") or signal.get("sl"))
    if None in (entry, exit_price, initial_sl):
        return None
    risk = abs(entry - initial_sl)
    if risk <= 0.0:
        return None
    if direction == "LONG":
        return (exit_price - entry) / risk
    return (entry - exit_price) / risk


def calculate_canonical_trade_r(signal):
    """Resolve one trade using explicit execution, terminal R, then legacy R."""
    explicit_r, reason = _explicit_execution(signal)
    if explicit_r is not None:
        return CanonicalOutcome(True, explicit_r, "explicit_execution")

    terminal_r = _terminal_realized_r(signal)
    if terminal_r is not None:
        return CanonicalOutcome(True, terminal_r, "terminal_realized_r")

    legacy_r = _legacy_realized_r(signal)
    if legacy_r is not None and isfinite(legacy_r):
        return CanonicalOutcome(True, legacy_r, "legacy_calculation")

    return CanonicalOutcome(False, None, "unresolved", reason)
