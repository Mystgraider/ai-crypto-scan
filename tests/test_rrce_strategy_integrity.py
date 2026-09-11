import pandas as pd

from engines.rrce_engine import RRCEEngine


def _ltf_frame(prev_down=True):
    timestamps = pd.date_range("2026-09-11 00:00:00", periods=7, freq="5min")
    rows = [
        {"open": 91, "high": 95, "low": 90, "close": 92},
        {"open": 95, "high": 100, "low": 94, "close": 98},
        {"open": 96, "high": 97, "low": 93, "close": 95},
        {"open": 97, "high": 100, "low": 94, "close": 99},
        {"open": 98, "high": 98, "low": 95, "close": 96},
        {"open": 99, "high": 103, "low": 101, "close": 102},
        {"open": 102, "high": 103, "low": 100, "close": 102},
    ]
    if not prev_down:
        rows[4] = {"open": 95, "high": 98, "low": 95, "close": 97}
    return pd.DataFrame(rows).assign(timestamp=timestamps)


def test_structure_ignores_current_incomplete_candle():
    df = pd.DataFrame(
        {
            "high": [1.0, 3.0, 1.0, 5.0, 1.0],
            "low": [0.0, 1.0, 0.0, 1.0, 0.0],
            "close": [0.5, 2.0, 0.5, 4.0, 0.5],
            "open": [0.5, 1.5, 0.5, 1.5, 0.5],
        }
    )
    result = RRCEEngine(swing_lookback=1)._find_swings(df)
    assert len(result) == 4
    assert pd.isna(result.iloc[-1]["swing_high"])


def test_stage3_requires_fvg_on_the_choch_break_candle():
    engine = RRCEEngine(swing_lookback=1)
    df = _ltf_frame()

    result = engine.stage3_confirmation(df, "LONG", sweep_time=df["timestamp"].iloc[4])
    assert result["passed"] is True
    assert result["break_idx"] == 5
    assert result["fvg"]["break_idx"] == 5

    broken = df.copy()
    broken.loc[5, "low"] = 99.0
    result = engine.stage3_confirmation(broken, "LONG", sweep_time=broken["timestamp"].iloc[4])
    assert result["passed"] is False
    assert result["reason"] == "choch_without_break_fvg"


def test_stage3_rejects_choch_that_happens_before_sweep():
    engine = RRCEEngine(swing_lookback=1)
    df = _ltf_frame()
    result = engine.stage3_confirmation(df, "LONG", sweep_time=df["timestamp"].iloc[5])
    assert result["passed"] is False
    assert result["reason"] == "choch_not_after_sweep"


def test_stage4_requires_anchored_order_block():
    engine = RRCEEngine(swing_lookback=1)
    df = _ltf_frame(prev_down=False)
    result = engine.stage4_execution(
        df_exec=df,
        direction="LONG",
        fvg={"top": 101.0, "bottom": 100.0},
        sweep_extreme=90.0,
        opposite_pool_level=110.0,
        break_idx=5,
    )
    assert result["valid"] is False
    assert result["reason"] == "no_anchored_order_block"
