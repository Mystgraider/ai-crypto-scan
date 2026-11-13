from datetime import datetime, timezone

import tools.short_cadence_audit as audit


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
        "rrce_stage2_sweep_time": "2026-01-01T00:00:00+00:00",
        "rrce_stage3_choch_level": 99.7,
        "rrce_stage3_break_time": "2026-01-01T00:15:00+00:00",
        "rrce_stage3_fvg_bottom": 99.8,
        "rrce_stage3_fvg_top": 99.9,
        "rrce_stage4_entry_zone": "OB",
        "replay_time": "2026-01-01T00:30:00+00:00",
        "symbol": "BTC/USDT:USDT",
    }
    base.update(overrides)
    return base


def test_episode_first_keeps_earliest_row():
    rows = [
        row(replay_time="2026-01-01T00:35:00+00:00", outcome="SL_HIT"),
        row(replay_time="2026-01-01T00:30:00+00:00", outcome="TP3_HIT"),
    ]
    selected, sizes = audit.episode_first(rows)
    assert len(selected) == 1
    assert selected[0]["replay_time"] == "2026-01-01T00:30:00+00:00"
    assert selected[0]["outcome"] == "TP3_HIT"
    assert sizes == [2]


def test_cooldown_suppresses_same_symbol_within_four_hours():
    rows = [
        row(replay_time="2026-01-01T00:30:00+00:00"),
        row(
            replay_time="2026-01-01T02:30:00+00:00",
            rrce_stage2_sweep_time="2026-01-01T02:00:00+00:00",
            rrce_stage3_break_time="2026-01-01T02:15:00+00:00",
        ),
        row(
            replay_time="2026-01-01T05:00:00+00:00",
            rrce_stage2_sweep_time="2026-01-01T04:30:00+00:00",
            rrce_stage3_break_time="2026-01-01T04:45:00+00:00",
        ),
    ]
    selected, meta = audit.cooldown_first(rows)
    assert [r["replay_time"] for r in selected] == [
        "2026-01-01T00:30:00+00:00",
        "2026-01-01T05:00:00+00:00",
    ]
    assert meta["cooldown_suppressed"] == 1
    assert meta["cooldown_hours"] == 4.0


def test_cooldown_is_per_symbol():
    rows = [
        row(replay_time="2026-01-01T00:30:00+00:00", symbol="BTC"),
        row(
            replay_time="2026-01-01T01:00:00+00:00",
            symbol="ETH",
            rrce_stage2_sweep_time="2026-01-01T00:30:00+00:00",
            rrce_stage3_break_time="2026-01-01T00:45:00+00:00",
        ),
    ]
    selected, meta = audit.cooldown_first(rows)
    assert len(selected) == 2
    assert meta["cooldown_suppressed"] == 0


def test_candidate_predicates_are_frozen():
    p = audit.candidate_predicates()
    features = audit.event_features(row())
    assert p["range_width_to_initial_sl_ge_5"](features)
    assert p["range_width_to_initial_sl_ge_6"](features)
    assert p["sweep_depth_le_0_15pct"](features)
    assert p["choch_displacement_le_0_40pct"](features)
    assert p["fvg_width_le_0_10pct"](features)


def test_stats_keeps_expired_out_of_tp3_denominator():
    rows = [row(), row(outcome="SL_HIT"), row(outcome="EXPIRED")]
    result = audit.stats(rows)
    assert result["signals"] == 3
    assert result["resolved"] == 2
    assert result["tp3_rate_pct"] == 50.0
