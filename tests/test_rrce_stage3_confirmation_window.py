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


def _patched_swings(df):
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


def test_stage3_does_not_accept_choch_before_sweep():
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


def test_stage3_window_is_bounded():
    engine = RRCEEngine()
    engine._find_swings = _patched_swings

    result = engine.stage3_confirmation(
        _ltf_fixture(),
        "LONG",
        sweep_time=pd.Timestamp("2026-09-19 00:20:00", tz="UTC"),
        confirmation_bars=1,
    )

    assert result["passed"] is False
    assert result["reason"] == "no_choch"


def test_stage3_tuning_is_configured_and_scanner_wires_it():
    from pathlib import Path

    scanner = (Path(__file__).resolve().parents[1] / "scanner_v5.py").read_text(
        encoding="utf-8"
    )

    assert CONFIG["rrce_stage3_confirmation_bars"] == 3
    assert 'confirmation_bars=CONFIG["rrce_stage3_confirmation_bars"]' in scanner
