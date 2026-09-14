CONFIG = {

    # Exchange
    "exchange": "bitget",

    # Scanning
    # Keep the universe small enough for the 5-minute schedule. Each symbol
    # can require several multi-timeframe exchange requests, so scanning 300
    # symbols regularly ran into the scan budget before completing.
    "top_coins_limit": 100,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds
    "min_score": 70,
    "signal_score_s": 95,
    "signal_score_a": 82,
    "signal_score_b": 70,
    "signal_score_c": 65,
    "signal_score_ceiling": 84,

    # Direction policy
    # LONG and SHORT are independently eligible. BTC is context, not the
    # source of direction. Keep legacy global direction pauses disabled.
    "pause_shorts": False,
    "block_bear_regime": False,

    # Legacy indicator gates are disabled so RRCE remains the primary
    # structural validator. Their scores remain available as supporting
    # evidence/ranking inputs.
    "require_trend_gate": False,
    "require_quality_engine": False,

    # GitHub Actions scan budget
    "scan_time_budget_sec": 480,

    # Indicator settings retained for supporting evidence
    "adx_min": 20,

    # BTC market context
    "btc_symbol":        "BTC/USDT:USDT",
    "btc_filter_enabled": True,
    "btc_rsi_short_floor": 42,
    "btc_rsi_long_ceil":   72,
    "btc_require_4h_bear_for_short": True,

    # Multi-timeframe supporting evidence
    "mtf_enabled": True,
    "mtf_reject_counter_trend": False,

    # Support/resistance
    "short_requires_resistance": True,
    "short_resistance_max_pct":  5.0,

    # BTC RANGE context: require stronger auxiliary trend evidence when an
    # asset already has a directional TrendEngine signal in a range regime.
    "range_regime_min_score": 85,

    # Risk
    "min_rr":     2.0,
    "min_sl_pct": 0.003,

    # LONG risk
    "sl_atr_mult":   1.0,
    "tp1_atr_mult":  2.5,
    "tp2_atr_mult":  4.0,
    "tp3_atr_mult":  6.0,

    # SHORT risk
    "short_sl_atr_mult":  2.0,
    "short_tp1_atr_mult": 4.5,
    "short_tp2_atr_mult": 6.0,
    "short_tp3_atr_mult": 8.0,

    # Cooldown / output limits
    "signal_cooldown_hours": 4,
    "max_signals_per_run": 3,

    # Safety
    "max_daily_losses": 3,

    # Relative strength / volume guards
    "rs_max_ratio": 8.0,
    "vol_max_ratio": 1.5,

    # Entry freshness
    "max_entry_drift_pct": 0.6,
    "rrce_entry_max_deviation_pct": 0.4,

    # RRCE tuning
    "rrce_default_patience_bars": 6,
    "rrce_range_patience_bars":   8,
    "rrce_default_eq_tolerance_pct": 0.15,
    "rrce_range_eq_tolerance_pct":   0.20,
    "rrce_watchlist_hours": 4,

    # Funding
    "funding_enabled":           True,
    "funding_short_block_above":  0.0001,
    "funding_long_block_below":  -0.0005,

    # Beta
    "beta_filter_enabled":     True,
    "beta_short_block_above":  1.5,

    # OI
    "oi_enabled": True,

    # Versions
    "db_version":       "1.0.0",
    "config_version":   "2.2.0",
    "strategy_version": "6.2.0",
}
