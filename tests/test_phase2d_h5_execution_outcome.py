from math import isclose

from reports.execution_outcome import calculate_canonical_trade_r


BASE = {
    "status": "TP3_HIT",
    "direction": "LONG",
    "entry": 100.0,
    "exit_price": 106.0,
    "initial_sl": 98.0,
    "realized_r": 3.0,
}


def test_full_explicit_execution_has_priority_over_terminal_realized_r():
    signal = {
        **BASE,
        "tp1_qty_pct": 50,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
        "tp2_qty_pct": 25,
        "tp2_exit_price": 106,
        "tp2_realized_r": 3,
        "tp2_executed_at": "2026-09-13T02:00:00Z",
        "remaining_position_pct": 25,
        "remaining_position_exit_r": 4,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "explicit_execution"
    assert isclose(outcome.realized_r, 2.75)


def test_partial_explicit_execution_does_not_invent_remaining_quantity():
    signal = {
        **BASE,
        "tp1_qty_pct": 50,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "terminal_realized_r"
    assert isclose(outcome.realized_r, 3.0)


def test_complete_tp1_then_breakeven_uses_explicit_execution():
    signal = {
        **BASE,
        "tp1_qty_pct": 50,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
        "remaining_position_pct": 50,
        "remaining_position_exit_r": 0,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "explicit_execution"
    assert isclose(outcome.realized_r, 1.0)


def test_terminal_realized_r_falls_back_to_legacy_when_missing():
    signal = {**BASE, "realized_r": ""}
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "legacy_calculation"
    assert isclose(outcome.realized_r, 3.0)


def test_unresolved_when_no_terminal_or_legacy_outcome_exists():
    signal = {
        "status": "EXPIRED",
        "direction": "LONG",
        "entry": 100.0,
        "initial_sl": 98.0,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "unresolved"
    assert outcome.realized_r is None


def test_execution_after_terminal_lifecycle_is_still_authoritative():
    signal = {
        **BASE,
        "status": "SL_HIT",
        "realized_r": -1.0,
        "tp1_qty_pct": 50,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
        "remaining_position_pct": 50,
        "remaining_position_exit_r": 0,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "explicit_execution"
    assert isclose(outcome.realized_r, 1.0)


def test_invalid_explicit_execution_does_not_get_partially_aggregated():
    signal = {
        **BASE,
        "tp1_qty_pct": 60,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
        "remaining_position_pct": 30,
        "remaining_position_exit_r": 0,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "terminal_realized_r"
    assert isclose(outcome.realized_r, 3.0)


def test_full_execution_with_zero_remaining_does_not_require_remaining_r():
    signal = {
        **BASE,
        "tp1_qty_pct": 100,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T01:00:00Z",
        "remaining_position_pct": 0,
        "remaining_position_exit_r": "",
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "explicit_execution"
    assert isclose(outcome.realized_r, 2.0)


def test_non_terminal_stored_realized_r_is_not_authoritative():
    signal = {
        "status": "OPEN",
        "direction": "LONG",
        "entry": 100.0,
        "initial_sl": 98.0,
        "realized_r": 3.0,
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "unresolved"
    assert outcome.realized_r is None


def test_malformed_direction_does_not_fall_back_to_short_legacy_r():
    signal = {
        **BASE,
        "direction": "SIDEWAYS",
        "realized_r": "",
    }
    outcome = calculate_canonical_trade_r(signal)
    assert outcome.source == "unresolved"
    assert outcome.realized_r is None
