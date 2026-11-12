import json
from pathlib import Path

import tools.short_event_aligned_audit as audit


def row(**overrides):
    base = {
        "direction": "SHORT",
        "outcome": "TP3_HIT",
        "entry": 100.0,
        "sl": 98.0,
        "rrce_stage3_passed": True,
        "rrce_stage1_range_width_pct": 12.0,
        "rrce_stage1_position_pct": 60.0,
        "rrce_stage2_pool_level": 100.0,
        "rrce_stage2_sweep_extreme": 100.1,
        "rrce_stage3_choch_level": 99.7,
        "rrce_stage3_fvg_bottom": 99.8,
        "rrce_stage3_fvg_top": 99.9,
        "replay_time": "2026-01-01T00:00:00+00:00",
        "symbol": "BTC/USDT:USDT",
    }
    base.update(overrides)
    return base


def test_event_features_are_entry_available():
    features = audit.event_features(row())
    assert round(features["range_width_to_initial_sl"], 6) == 6.0
    assert round(features["sweep_depth_pct"], 6) == 0.1
    assert round(features["choch_displacement_pct"], 6) == 0.3
    assert round(features["fvg_width_pct"], 6) == 0.1


def test_sl_distance_is_planned_geometry():
    assert audit.sl_distance(row()) == 2.0


def test_candidate_range_width_to_sl():
    predicate = audit.candidate_predicates()["range_width_to_initial_sl_ge_5"]
    assert predicate(audit.event_features(row()))
    assert not predicate(audit.event_features(row(rrce_stage1_range_width_pct=9.9)))


def test_stats_excludes_expired_from_tp3_denominator():
    rows = [row(), row(outcome="SL_HIT"), row(outcome="EXPIRED")]
    result = audit.stats(rows)
    assert result["signals"] == 3
    assert result["resolved"] == 2
    assert result["tp3_rate_pct"] == 50.0


def test_symbol_concentration():
    rows = [
        row(symbol="A", outcome="TP3_HIT"),
        row(symbol="A", outcome="TP3_HIT"),
        row(symbol="B", outcome="TP3_HIT"),
        row(symbol="B", outcome="SL_HIT"),
    ]
    result = audit.symbol_concentration(rows)
    assert result["symbol_count"] == 2
    assert result["largest_symbol_tp3_share_pct"] == 66.67
