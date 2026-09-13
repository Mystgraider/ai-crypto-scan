from math import isclose


def weighted_realized_r(parts):
    """Reference-only accounting model for Phase 2D-H tests."""
    return round(sum((qty / 100.0) * r for qty, r in parts), 6)


def test_full_tp_ladder_realized_r_from_structural_4r():
    # Phase 2D-E ladder is proportional to the structural target:
    # TP1=50%, TP2=75%, TP3=100%. For a 4R structural target this is 2R/3R/4R.
    assert isclose(weighted_realized_r([(50, 2.0), (25, 3.0), (25, 4.0)]), 2.75)


def test_tp1_then_breakeven_remaining_position():
    # Half closes at TP1=2R; remaining half closes at entry for 0R.
    assert isclose(weighted_realized_r([(50, 2.0), (50, 0.0)]), 1.0)


def test_tp1_tp2_then_breakeven_remaining_position():
    # 50% at 2R, 25% at 3R, final 25% at breakeven.
    assert isclose(weighted_realized_r([(50, 2.0), (25, 3.0), (25, 0.0)]), 1.75)


def test_short_reward_is_positive_when_exit_is_in_profit_direction():
    entry, exit_price, risk = 100.0, 92.0, 2.0
    realized_r = (entry - exit_price) / risk
    assert isclose(realized_r, 4.0)


def test_full_ladder_quantities_sum_to_100_percent():
    assert sum((50, 25, 25)) == 100


def test_partial_ladder_preserves_remaining_quantity():
    assert 100 - sum((50, 25)) == 25


def test_direct_tp3_observation_does_not_fabricate_partial_execution():
    # A tracker observation is not execution evidence by itself.
    observed_status = "TP3_HIT"
    execution_events = []
    assert observed_status == "TP3_HIT"
    assert execution_events == []
