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


def test_stage1_rejects_prices_outside_structural_range():
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

    long_below = engine.stage1_range(df, "LONG", 85.0)
    short_above = engine.stage1_range(df, "SHORT", 120.0)

    assert long_below["position_pct"] < 0
    assert long_below["passed"] is False
    assert short_above["position_pct"] > 100
    assert short_above["passed"] is False


def test_stage2_no_near_pool_still_exposes_population_diagnostics():
    engine = RRCEEngine()

    df = pd.DataFrame({
        "high": [110, 111, 110, 111, 110, 111, 110, 111],
        "low": [109, 110, 109, 110, 109, 110, 109, 110],
        "close": [110, 110, 110, 110, 110, 110, 110, 110],
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="15min", tz="UTC"),
    })
    swings = df.copy()
    swings["swing_high"] = np.nan
    swings["swing_low"] = np.nan
    swings.loc[1, "swing_low"] = 109.0
    swings.loc[3, "swing_low"] = 109.0
    engine._find_swings = lambda _: swings

    result = engine.stage2_retail_liquidity(
        df, "LONG", range_low=100.0, range_high=120.0, proximity_pct=5.0, patience_bars=3
    )

    assert result["passed"] is False
    assert result["reason"] == "no_equal_lows_near_range_low"
    assert result["all_pool_count"] == 1
    assert result["near_pool_count"] == 0
    assert result["proximity_pct"] == 5.0
    assert result["patience_bars"] == 3
    assert result["sweep_window_start"] is not None
    assert result["sweep_window_end"] is not None


def test_stage2_selects_a_swept_qualifying_pool_over_a_closer_unswept_pool():
    engine = RRCEEngine()

    df = pd.DataFrame({
        "high": [104, 104, 104, 104, 103, 104, 104, 104],
        "low": [101, 101, 101, 101, 101, 101, 101, 101],
        "close": [102, 102, 102, 102, 101, 103, 101, 101],
        "timestamp": pd.date_range("2026-09-19", periods=8, freq="15min", tz="UTC"),
    })
    engine._find_swings = lambda _: pd.DataFrame({
        "swing_high": [np.nan] * 8,
        "swing_low": [np.nan] * 8,
    })
    engine._equal_levels = lambda _: [
        {"level": 100.0, "touches": 2},
        {"level": 102.0, "touches": 2},
    ]

    result = engine.stage2_retail_liquidity(
        df, "LONG", range_low=100.0, range_high=110.0,
        proximity_pct=5.0, patience_bars=3,
    )

    assert result["passed"] is True
    assert result["pool_level"] == 102.0
    assert result["pool_distance_from_range_extreme_pct"] == 2.0
    assert result["sweep_time"] == df["timestamp"].iloc[5]

def test_stage2_pool_discovery_is_cut_off_before_sweep_window():
    engine = RRCEEngine()
    rows = 20
    df = pd.DataFrame({
        "high": [103.0] * rows,
        "low": [99.0] * rows,
        "close": [100.0] * rows,
        "timestamp": pd.date_range("2026-09-19", periods=rows, freq="15min", tz="UTC"),
    })
    # The final patience+1 candles form the sweep window. A future-only
    # liquidity pool must not be visible to Stage 2 pool discovery.
    df.loc[16:, "low"] = 99.0
    df.loc[16:, "close"] = 100.5

    observed_lengths = []

    def fake_find_swings(frame):
        observed_lengths.append(len(frame))
        level = 100.0 if len(frame) < rows else 101.0
        swings = frame.copy()
        swings["swing_high"] = np.nan
        swings["swing_low"] = np.nan
        if len(swings) >= 6:
            swings.loc[1, "swing_low"] = level
            swings.loc[3, "swing_low"] = level
        return swings

    engine._find_swings = fake_find_swings

    result = engine.stage2_retail_liquidity(
        df,
        "LONG",
        range_low=100.0,
        range_high=110.0,
        proximity_pct=5.0,
        patience_bars=3,
    )

    assert observed_lengths == [16]
    assert result["passed"] is True
    assert result["pool_level"] == 100.0
    assert result["sweep_time"] == df["timestamp"].iloc[-2]


def test_stage2_does_not_use_future_confirmed_swing_as_pool():
    engine = RRCEEngine()
    rows = 20
    df = pd.DataFrame({
        "high": [103.0] * rows,
        "low": [99.0] * rows,
        "close": [100.0] * rows,
        "timestamp": pd.date_range("2026-09-19", periods=rows, freq="15min", tz="UTC"),
    })
    # A pool appearing only inside the sweep window is deliberately returned
    # by the mocked full-history structure to model the look-ahead failure.
    df.loc[16:, "low"] = 98.5
    df.loc[16:, "close"] = 100.5

    def future_only_pool(frame):
        swings = frame.copy()
        swings["swing_high"] = np.nan
        swings["swing_low"] = np.nan
        if len(frame) == rows:
            swings.loc[17, "swing_low"] = 100.0
            swings.loc[18, "swing_low"] = 100.0
        else:
            swings.loc[1, "swing_low"] = 102.0
            swings.loc[3, "swing_low"] = 102.0
        return swings

    engine._find_swings = future_only_pool

    result = engine.stage2_retail_liquidity(
        df,
        "LONG",
        range_low=100.0,
        range_high=110.0,
        proximity_pct=5.0,
        patience_bars=3,
    )

    assert result["passed"] is False
    assert result["reason"] == "no_equal_lows_near_range_low"
