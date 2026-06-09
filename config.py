CONFIG = {

    # Exchange
    "exchange": "bitget",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds — V5.6 values (relaxed, proven to generate signals)
    "min_score": 65,
    "signal_score_s": 90,
    "signal_score_a": 80,
    "signal_score_b": 70,
    "signal_score_c": 65,

    # ADX gate (enforced in trend_engine)
    "adx_min": 20,

    # BTC Filter — V5.5 values
    "btc_symbol":        "BTC/USDT:USDT",
    "btc_filter_enabled": True,
    "btc_rsi_short_floor": 42,
    "btc_rsi_long_ceil":   72,
    "btc_require_4h_bear_for_short": True,

    # Multi-timeframe — V5.6: NEUTRAL = ALLOWED (not rejected)
    "mtf_enabled": True,
    "mtf_reject_counter_trend": True,   # only REJECTED is blocked, NEUTRAL allowed

    # S/R
    "short_requires_resistance": True,
    "short_resistance_max_pct":  3.0,

    # BTC RANGE regime — require higher score
    "range_regime_min_score": 85,  # raised: BTC RANGE = risky, need stronger signal

    # Risk — V5.4 proven values
    "min_rr":     2.0,
    "min_sl_pct": 0.003,

    # LONG risk
    "sl_atr_mult":   1.0,
    "tp1_atr_mult":  2.5,
    "tp2_atr_mult":  4.0,
    "tp3_atr_mult":  6.0,

    # SHORT risk — wider SL for bounces
    "short_sl_atr_mult":  2.0,
    "short_tp1_atr_mult": 4.5,
    "short_tp2_atr_mult": 6.0,
    "short_tp3_atr_mult": 8.0,

    # Cooldown
    "signal_cooldown_hours": 4,

    # Max signals per run
    "max_signals_per_run": 5,

    # Circuit breaker
    "max_daily_losses": 3,

    # RS cap — if coin already 10x+ vs BTC, it pumped already
    "rs_max_ratio": 10.0,

    # Funding rate
    "funding_enabled":           True,
    "funding_short_block_above":  0.0001,
    "funding_long_block_below":  -0.0005,

    # Beta filter
    "beta_filter_enabled":     True,
    "beta_short_block_above":  1.5,

    # OI confirmation
    "oi_enabled": True,

    # Versions
    "db_version":       "1.0.0",
    "config_version":   "1.9.0",
    "strategy_version": "5.9.0",
}
