import numpy as np
import pandas as pd

from engines.rrce_engine import RRCEEngine


def test_stage1_exposes_range_diagnostics():
    engine = RRCEEngine()

    df = pd.DataFrame({
        "high": [100.0] * 40,
        "low": [90.0] * 40,
        "timestamp": pd.date_range("2026-09-19", periods=40, freq="15min", tz="UTC"),
    })
    swings = df.copy()
    swings["swing_high"] = np.nan
    swings["swing_low"] = np.nan
    swings.loc[10, "swing_high"] = 110.0
    swings.loc[20, "swing_low"] = 90.0
    engine._find_swings = lambda _: swings

    result = engine.stage1_range(df, "LONG", 95.0)

    assert result["range_high"] == 110.0
    assert result["range_low"] == 90.0
    assert result["range_width_pct"] > 0
    assert result["range_high_time"] is not None
    assert result["range_low_time"] is not None
    assert result["range_high_index"] == "10"
    assert result["range_low_index"] == "20"
    assert result["price_above_range_high_pct"] < 0
    assert result["price_below_range_low_pct"] < 0


def test_stage2_exposes_pool_and_sweep_window_diagnostics():
    engine = RRCEEngine()

    df = pd.DataFrame({
        "high": [101, 102, 101, 102, 100, 102, 100, 102],
        "low": [99, 100, 99, 100, 98, 100, 98, 100],
        "close": [100, 101, 100, 101, 99, 101, 99, 101],
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="15min", tz="UTC"),
    })
    swings = df.copy()
    swings["swing_high"] = np.nan
    swings["swing_low"] = np.nan
    swings.loc[1, "swing_low"] = 99.0
    swings.loc[3, "swing_low"] = 99.0
    engine._find_swings = lambda _: swings

    result = engine.stage2_retail_liquidity(
        df, "LONG", range_low=99.0, range_high=102.0, patience_bars=3
    )

    assert result["all_pool_count"] >= 1
    assert result["near_pool_count"] >= 1
    assert result["pool_distance_from_range_extreme_pct"] == 0.0
    assert result["patience_bars"] == 3
    assert result["sweep_window_start"] is not None
    assert result["sweep_window_end"] is not None
