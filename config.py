CONFIG = {

    # Exchange
    "exchange": "bitget",
    "top_coins_limit": 100,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 100,

    # Signal thresholds
    "min_score": 70,
    "signal_score_s": 95,
    "signal_score_a": 82,
    "signal_score_b": 70,
    "signal_score_c": 65,
    # 84+ remains a deliberate overextension safety ceiling; S is diagnostic.
    "signal_score_ceiling": 84,

    # Direction policy: LONG and SHORT are independently eligible.
    "require_trend_gate": False,
    "require_quality_engine": False,
    "scan_time_budget_sec": 480,
    "adx_min": 20,

    # BTC is market context/safety, not the source of coin direction.
    "btc_symbol": "BTC/USDT:USDT",
    "btc_filter_enabled": True,
    "btc_rsi_short_floor": 42,
    "btc_rsi_long_ceil": 72,
    "btc_require_4h_bear_for_short": True,

    "mtf_enabled": True,
    "mtf_reject_counter_trend": False,
    "short_requires_resistance": True,
    "short_resistance_max_pct": 5.0,

    # BTC RANGE only selects the RANGE RRCE profile. It must not impose a
    # TrendEngine score gate on otherwise independent coin directions.

    # RRCE is the sole production authority for structural SL/TP levels.
    "min_rr": 2.0,

    "signal_cooldown_hours": 4,
    "max_signals_per_run": 3,
    "max_daily_losses": 3,
    "rs_max_ratio": 8.0,
    "vol_max_ratio": 1.5,
    "max_entry_drift_pct": 0.6,
    "rrce_entry_max_deviation_pct": 0.4,
    "rrce_default_patience_bars": 6,
    "rrce_range_patience_bars": 8,
    # Stage-3 tuning: allow a bounded delayed CHOCH/FVG confirmation.
    # The FVG must still belong to the exact CHOCH candle.
    "rrce_stage3_confirmation_bars": 3,
    "rrce_default_eq_tolerance_pct": 0.15,
    "rrce_range_eq_tolerance_pct": 0.20,
    "rrce_watchlist_hours": 4,
    "funding_enabled": True,
    "funding_short_block_above": 0.0001,
    "funding_long_block_below": -0.0005,
    "beta_filter_enabled": True,
    "beta_short_block_above": 1.5,
    "oi_enabled": True,
    "db_version": "1.0.0",
    "config_version": "2.2.0",
    "strategy_version": "6.2.0",
}
