CONFIG = {

    # Exchange
    "exchange": "bitget",

    # Scanning
    # Keep the universe small enough for the 5-minute schedule.  Each symbol
    # can require several multi-timeframe exchange requests, so scanning 300
    # symbols regularly ran into the 8-minute scan budget before completing.
    # The 100 most-liquid USDT futures retain broad market coverage while
    # allowing a complete run to finish substantially sooner.
    "top_coins_limit": 100,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds — V5.6 values (relaxed, proven to generate signals)
    "min_score": 70,
    "signal_score_s": 95,
    "signal_score_a": 82,
    "signal_score_b": 70,
    "signal_score_c": 65,

    # Hard safety ceiling. Scores >= 84 are rejected as overextended/chasing.
    # This intentionally leaves S (>=95) diagnostic-only until historical
    # evidence justifies changing the ceiling.
    "signal_score_ceiling": 84,

    # SHORT re-enabled for independent direction discovery.
    "pause_shorts": False,

    # TrendEngine is evidence only; it must not be a production hard gate.
    "require_trend_gate": False,

    # QualityEngine is evidence only; it must not be a production hard gate.
    "require_quality_engine": False,

    # Stop starting new symbols after this many seconds.
    "scan_time_budget_sec": 480,

    # BTC is market context/safety, not the signal generator.
    "block_bear_regime": False,

    # ADX gate (enforced in trend_engine)
    "adx_min": 20,

    # BTC Filter — market context/safety only
    "btc_symbol":        "BTC/USDT:USDT",
    "btc_filter_enabled": True,
    "btc_rsi_short_floor": 42,
    "btc_rsi_long_ceil":   72,
    "btc_require_4h_bear_for_short": True,

    # Multi-timeframe — NEUTRAL = ALLOWED
    "mtf_enabled": True,
    "mtf_reject_counter_trend": False,

    # S/R
    "short_requires_resistance": True,
    "short_resistance_max_pct":  5.0,

    # BTC RANGE selects the RRCE range profile only. It must not impose
    # an indicator-score gate on coin-level signal discovery.
    "range_regime_min_score": 0,

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

    # Cooldown
    "signal_cooldown_hours": 4,

    # Max signals per run
    "max_signals_per_run": 3,

    # Circuit breaker
    "max_daily_losses": 3,

    # RS cap
    "rs_max_ratio": 8.0,
    "vol_max_ratio": 1.5,

    # Price staleness guard
    "max_entry_drift_pct": 0.6,

    # RRCE executable-entry deviation guard
    "rrce_entry_max_deviation_pct": 0.4,

    # RANGE-regime RRCE tuning
    "rrce_default_patience_bars": 6,
    "rrce_range_patience_bars":   8,
    "rrce_default_eq_tolerance_pct": 0.15,
    "rrce_range_eq_tolerance_pct":   0.20,

    # Persist swept Stage-2 setups while waiting for Stage 3/4.
    "rrce_watchlist_hours": 4,

    # Funding rate
    "funding_enabled":           True,
    "funding_short_block_above":  0.0001,
    "funding_long_block_below":  -0.0005,

    # Beta filter
    "beta_filter_enabled":     True,
    "beta_short_block_above":  1.5,

    # OI confirmation — supporting evidence, never a signal generator.
    "oi_enabled": True,

    # Versions
    "db_version":       "1.0.0",
    "config_version":   "2.1.0",
    "strategy_version": "6.1.0",
}
