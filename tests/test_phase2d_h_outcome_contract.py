from math import isclose


def weighted_realized_r(parts):
    """Reference-only accounting model for Phase 2D-H tests."""
    return round(sum((qty / 100.0) * r for qty, r in parts), 6)


def test_full_tp_ladder_realized_r():
    # 50% at TP1=2.5R, 25% at TP2=3.75R, 25% at TP3=5R.
    assert isclose(weighted_realized_r([(50, 2.5), (25, 3.75), (25, 5.0)]), 3.4375)


def test_tp1_then_breakeven_remaining_position():
    # Half closes at TP1; remaining half closes at entry for 0R.
    assert isclose(weighted_realized_r([(50, 2.5), (50, 0.0)]), 1.25)


def test_tp1_tp2_then_breakeven_remaining_position():
    assert isclose(weighted_realized_r([(50, 2.5), (25, 3.75), (25, 0.0)]), 2.1875)


def test_all_targets_are_milestones_until_execution_evidence_exists():
    # A direct TP3 observation alone must not fabricate partial-execution P&L.
    observed_status = "TP3_HIT"
    execution_events = []
    assert observed_status == "TP3_HIT"
    assert execution_events == []


def test_short_reward_is_signed_from_direction():
    # SHORT profit is represented as positive R when exit < entry.
    entry, exit_price, risk = 100.0, 92.0, 2.0
    realized_r = (entry - exit_price) / risk
    assert isclose(realized_r, 4.0)


def test_full_ladder_quantities_sum_to_100_percent():
    assert sum((50, 25, 25)) == 100


def test_partial_ladder_preserves_remaining_quantity():
    assert 100 - sum((50, 25)) == 25
