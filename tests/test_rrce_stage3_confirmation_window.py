import numpy as np
import pandas as pd

from config import CONFIG
from engines.rrce_engine import RRCEEngine


def _ltf_fixture():
    timestamps = pd.date_range("2026-09-19 00:00:00", periods=9, freq="5min", tz="UTC")
    rows = [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (89, 90, 88, 89),
        (95, 101, 94, 100),
        (98, 106, 97, 105),  # delayed CHOCH + FVG candle
        (104, 105, 103, 104),
        (100, 101, 99, 99),   # latest closed candle no longer breaks structure
        (99, 100, 98, 99),    # incomplete candle; excluded
    ]
    return pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
        index=range(len(rows)),
    ).assign(timestamp=timestamps)


def _patched_swings(df, n=None):
    d = df.copy()
    d["swing_high"] = np.nan
    d["swing_low"] = np.nan
    d.loc[4, "swing_high"] = 100.0
    d.loc[2, "swing_low"] = 90.0
    return d


def test_stage3_accepts_delayed_choch_with_fvg_on_break_candle():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is True
    assert result["break_idx"] == 5
    assert result["fvg"]["break_idx"] == 5


def test_stage3_ignores_choch_before_sweep():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:30:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "no_choch"


def test_stage3_window_is_bounded_after_sweep():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=1,
    )

    # The first closed candle after the sweep is the CHOCH candle, so a
    # one-bar post-sweep window is sufficient and must be accepted.
    assert result["passed"] is True
    assert result["break_idx"] == 5



def test_stage3_continues_after_choch_without_fvg():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    fixture = _ltf_fixture().copy()
    fixture.loc[4, "close"] = 102.0

    result = engine.stage3_confirmation(
        fixture,
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is True
    assert result["break_idx"] == 5
    assert result["fvg"]["break_idx"] == 5


def test_stage3_uses_structure_available_before_each_candidate_break():
    engine = RRCEEngine()

    def _temporal_swings(df, n=None):
        d = df.copy()
        d["swing_high"] = np.nan
        d["swing_low"] = np.nan
        if len(df) <= 6:
            d.loc[4, "swing_high"] = 100.0
        else:
            d.loc[4, "swing_high"] = 100.0
            d.loc[6, "swing_high"] = 105.0
        d.loc[2, "swing_low"] = 90.0
        return d

    engine._find_swings = _temporal_swings
    fixture = _ltf_fixture().copy()
    fixture.loc[5, "close"] = 102.0

    result = engine.stage3_confirmation(
        fixture,
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is True
    assert result["break_idx"] == 5
    assert result["choch_level"] == 100.0

def test_stage3_handoff_waits_for_late_confirmed_post_sweep_structure():
    engine = RRCEEngine()

    timestamps = pd.date_range(
        "2026-09-19 00:00:00", periods=10, freq="5min", tz="UTC"
    )
    rows = [
        (100, 101, 99, 100),
        (89, 90, 88, 89),      # sweep candle
        (95, 99, 94, 98),
        (98, 100, 97, 99),
        (99, 100, 98, 100),    # post-sweep swing high
        (100, 101, 99, 100),
        (100, 100, 99, 100),
        (100, 101, 99, 100),
        (100, 110, 106, 108),  # late CHOCH + exact break-candle FVG
        (108, 109, 107, 108),  # incomplete
    ]
    fixture = pd.DataFrame(
        rows,
        columns=["open", "high", "low", "close"],
    ).assign(timestamp=timestamps)

    def _late_swings(df, n=None):
        d = df.copy()
        d["swing_high"] = np.nan
        d["swing_low"] = np.nan
        if len(df) > 7:
            d.loc[4, "swing_high"] = 100.0
        return d

    engine._find_swings = _late_swings

    result = engine.stage3_confirmation(
        fixture,
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:05:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is True
    assert result["break_idx"] == 8
    assert result["structure_handoff"] is True
    assert result["fvg"]["break_idx"] == 8


def test_stage3_tuning_is_configured_and_scanner_wires_it():
    from pathlib import Path

    scanner = (Path(__file__).resolve().parents[1] / "scanner_v5.py").read_text(
        encoding="utf-8"
    )

    assert CONFIG["rrce_stage3_confirmation_bars"] == 6
    assert 'confirmation_bars=CONFIG["rrce_stage3_confirmation_bars"]' in scanner


def test_stage3_window_is_anchored_to_sweep_without_post_sweep_structure():
    engine = RRCEEngine()

    def _pre_sweep_only_swings(df, n=None):
        d = df.copy()
        d["swing_high"] = np.nan
        d["swing_low"] = np.nan
        d.loc[0, "swing_high"] = 100.0
        d.loc[2, "swing_low"] = 90.0
        return d

    engine._find_swings = _pre_sweep_only_swings

    fixture = _ltf_fixture().copy()
    # The CHOCH occurs after the primary window, but there is no confirmed
    # post-sweep structure to authorize a structural handoff.
    result = engine.stage3_confirmation(
        fixture,
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:05:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "no_choch"


def test_stage3_rejects_invalid_sweep_timestamp_fail_closed():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time="not-a-timestamp",
        confirmation_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "invalid_sweep_timestamp"


def test_stage3_rejects_duplicate_ltf_timestamps():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    fixture = _ltf_fixture().copy()
    fixture.loc[6, "timestamp"] = fixture.loc[5, "timestamp"]

    result = engine.stage3_confirmation(
        fixture,
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "duplicate_ltf_timestamps"


def test_stage3_rejects_choch_inside_unclosed_15m_sweep_candle():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    # A 15m sweep candle opening at 00:15 closes at 00:30. A 5m CHOCH at
    # 00:25 is inside that sweep candle and must not count as post-sweep
    # confirmation.
    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:30:00", tz="UTC"),
        confirmation_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "no_choch"


def test_raw_v69_stage3_shadow_replays_latest_closed_candle():
    engine = RRCEEngine()
    timestamps = pd.date_range("2026-09-19 00:00:00", periods=5, freq="15min", tz="UTC")
    rows = [
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 101, 99, 100),
        (100, 106, 105, 105),
        (105, 106, 104, 105),
    ]
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"]).assign(timestamp=timestamps)
    def swings(d, n=None):
        x = d.copy()
        x["swing_high"] = np.nan
        x["swing_low"] = np.nan
        x.loc[2, "swing_high"] = 100.0
        return x
    engine._find_swings_v69_shadow = swings
    result = engine.stage3_v69_shadow(df, "LONG")
    assert result["passed"] is True
    assert result["break_idx"] == 3
