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


def test_stage3_ignores_choch_before_sweep():
    engine = RRCEEngine(swing_lookback=1)
    df = _ltf_frame()
    result = engine.stage3_confirmation(df, "LONG", sweep_time=df["timestamp"].iloc[5])
    assert result["passed"] is False
    assert result["reason"] == "no_choch"


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


def test_rrce_evaluate_rejects_stage3_stage4_break_timestamp_mismatch():
    import numpy as np
    from unittest.mock import patch

    engine = RRCEEngine()

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="5min", tz="UTC"),
        "open": np.arange(100, 108, dtype=float),
        "high": np.arange(101, 109, dtype=float),
        "low": np.arange(99, 107, dtype=float),
        "close": np.arange(100, 108, dtype=float),
        "atr": np.ones(8, dtype=float),
    })
    df_exec = df.copy()
    df_exec.loc[5, "timestamp"] = pd.Timestamp("2026-09-19 01:00:00", tz="UTC")

    s1 = {"passed": True, "range_low": 90.0, "range_high": 110.0}
    s2 = {"passed": True, "sweep_time": df["timestamp"].iloc[4], "sweep_extreme": 89.0}

    s3 = {
        "passed": True,
        "fvg": {"top": 103.0, "bottom": 102.0, "break_idx": 5},
        "break_idx": 5,
        "break_time": df["timestamp"].iloc[5],
    }

    with patch.object(engine, "stage1_range", return_value=s1),          patch.object(engine, "stage2_retail_liquidity", return_value=s2),          patch.object(engine, "stage3_confirmation", return_value=s3):
        result = engine.evaluate(
            df_htf=df,
            df_mtf=df,
            df_ltf_confirm=df,
            df_ltf_exec=df_exec,
            direction="LONG",
            price=100.0,
        )

    assert result["valid"] is False
    assert result["failed_at"] == "stage3_dataframe_alignment"
    assert result["stage3"]["reason"] == "break_candle_timestamp_mismatch"


def test_rrce_evaluate_accepts_matching_stage3_stage4_break_timestamp():
    import numpy as np
    from unittest.mock import patch

    engine = RRCEEngine()

    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="5min", tz="UTC"),
        "open": np.arange(100, 108, dtype=float),
        "high": np.arange(101, 109, dtype=float),
        "low": np.arange(99, 107, dtype=float),
        "close": np.arange(100, 108, dtype=float),
        "atr": np.ones(8, dtype=float),
    })

    s1 = {"passed": True, "range_low": 90.0, "range_high": 110.0}
    s2 = {"passed": True, "sweep_time": df["timestamp"].iloc[4], "sweep_extreme": 89.0}
    s3 = {
        "passed": True,
        "fvg": {"top": 103.0, "bottom": 102.0, "break_idx": 5},
        "break_idx": 5,
        "break_time": df["timestamp"].iloc[5],
    }
    s4 = {"valid": True, "entry": 101.0, "sl": 89.0, "tp": 110.0, "rr": 0.75}

    with patch.object(engine, "stage1_range", return_value=s1),          patch.object(engine, "stage2_retail_liquidity", return_value=s2),          patch.object(engine, "stage3_confirmation", return_value=s3),          patch.object(engine, "stage4_execution", return_value=s4):
        result = engine.evaluate(
            df_htf=df,
            df_mtf=df,
            df_ltf_confirm=df,
            df_ltf_exec=df.copy(),
            direction="LONG",
            price=100.0,
        )

    assert result["valid"] is True
    assert result["stage4"] == s4


def test_rrce_evaluate_rejects_break_candle_ohlc_mismatch():
    import numpy as np
    from unittest.mock import patch

    engine = RRCEEngine()
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="5min", tz="UTC"),
        "open": np.arange(100, 108, dtype=float),
        "high": np.arange(101, 109, dtype=float),
        "low": np.arange(99, 107, dtype=float),
        "close": np.arange(100, 108, dtype=float),
        "atr": np.ones(8, dtype=float),
    })
    df_exec = df.copy()
    df_exec.loc[5, "close"] = 999.0

    s1 = {"passed": True, "range_low": 90.0, "range_high": 110.0}
    s2 = {"passed": True, "sweep_time": df["timestamp"].iloc[4], "sweep_extreme": 89.0}
    s3 = {
        "passed": True,
        "fvg": {"top": 103.0, "bottom": 102.0, "break_idx": 5},
        "break_idx": 5,
        "break_time": df["timestamp"].iloc[5],
    }

    with patch.object(engine, "stage1_range", return_value=s1),          patch.object(engine, "stage2_retail_liquidity", return_value=s2),          patch.object(engine, "stage3_confirmation", return_value=s3):
        result = engine.evaluate(
            df_htf=df,
            df_mtf=df,
            df_ltf_confirm=df,
            df_ltf_exec=df_exec,
            direction="LONG",
            price=100.0,
        )

    assert result["valid"] is False
    assert result["failed_at"] == "stage3_dataframe_alignment"
    assert result["stage3"]["reason"] == "break_candle_data_mismatch"
    assert result["stage3"]["field"] == "close"


def test_rrce_evaluate_rejects_break_candle_atr_mismatch():
    import numpy as np
    from unittest.mock import patch

    engine = RRCEEngine()
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="5min", tz="UTC"),
        "open": np.arange(100, 108, dtype=float),
        "high": np.arange(101, 109, dtype=float),
        "low": np.arange(99, 107, dtype=float),
        "close": np.arange(100, 108, dtype=float),
        "atr": np.ones(8, dtype=float),
    })
    df_exec = df.copy()
    df_exec.loc[5, "atr"] = 2.0

    s1 = {"passed": True, "range_low": 90.0, "range_high": 110.0}
    s2 = {"passed": True, "sweep_time": df["timestamp"].iloc[4], "sweep_extreme": 89.0}
    s3 = {
        "passed": True,
        "fvg": {"top": 103.0, "bottom": 102.0, "break_idx": 5},
        "break_idx": 5,
        "break_time": df["timestamp"].iloc[5],
    }

    with patch.object(engine, "stage1_range", return_value=s1),          patch.object(engine, "stage2_retail_liquidity", return_value=s2),          patch.object(engine, "stage3_confirmation", return_value=s3):
        result = engine.evaluate(
            df_htf=df,
            df_mtf=df,
            df_ltf_confirm=df,
            df_ltf_exec=df_exec,
            direction="LONG",
            price=100.0,
        )

    assert result["valid"] is False
    assert result["failed_at"] == "stage3_dataframe_alignment"
    assert result["stage3"]["reason"] == "break_candle_atr_mismatch"


def test_stage3_post_sweep_structural_handoff_uses_confirmed_post_sweep_swing():
    engine = RRCEEngine(swing_lookback=10)
    timestamps = pd.date_range("2026-09-20 00:00:00", periods=14, freq="5min", tz="UTC")
    rows = [
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 99.0, "close": 100.0},
        {"open": 100.0, "high": 101.0, "low": 101.5, "close": 101.2},
        {"open": 101.2, "high": 101.4, "low": 100.8, "close": 101.1},
        {"open": 101.1, "high": 103.0, "low": 101.1, "close": 102.8},
        {"open": 102.8, "high": 103.0, "low": 102.0, "close": 102.5},
        {"open": 102.5, "high": 102.7, "low": 102.0, "close": 102.4},
    ]
    df = pd.DataFrame(rows).assign(timestamp=timestamps)

    result = engine.stage3_confirmation(
        df,
        "LONG",
        sweep_time=timestamps[8],
        confirmation_bars=3,
    )

    assert result["passed"] is True
    assert result["structure_handoff"] is True
    assert result["structure_lookback"] in (3, 5, 7)
    assert result["break_idx"] == 11
