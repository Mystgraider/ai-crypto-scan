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
            swings.loc[1, "swing_low"] = 107.0
            swings.loc[3, "swing_low"] = 107.0
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