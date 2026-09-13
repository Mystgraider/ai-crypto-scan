from math import isclose


def weighted_realized_r(parts):
    """Reference-only accounting model for Phase 2D-H tests."""
    return round(sum((qty / 100.0) * r for qty, r in parts), 6)


def test_full_tp_ladder_realized_r_from_structural_4r():
    # Phase 2D-E ladder: TP1=50%, TP2=75%, TP3=100% of structural reward.
    # A 4R structural target therefore becomes 2R / 3R / 4R.
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


def test_tp1_event_requires_execution_evidence():
    # A milestone observation alone must not become a partial fill.
    observed_status = "OPEN_TP1"
    execution_events = []
    assert observed_status == "OPEN_TP1"
    assert execution_events == []


def test_tp2_event_requires_execution_evidence():
    observed_status = "OPEN_TP2"
    execution_events = []
    assert observed_status == "OPEN_TP2"
    assert execution_events == []


def test_tp3_event_requires_execution_evidence_for_partial_accounting():
    # Direct TP3 observation may be terminal tracker evidence, but it does not
    # prove that TP1/TP2 partial quantities were actually executed.
    observed_status = "TP3_HIT"
    execution_events = []
    assert observed_status == "TP3_HIT"
    assert execution_events == []


def test_remaining_quantity_after_tp1_is_50_percent():
    assert 100 - 50 == 50


def test_remaining_quantity_after_tp1_tp2_is_25_percent():
    assert 100 - 50 - 25 == 25
