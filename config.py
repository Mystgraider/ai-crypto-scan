CONFIG = {

    # Exchange
    "exchange": "bitget",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds — V5.6 values (relaxed, proven to generate signals)
    "min_score": 70,           # data: score 70-75 = 100% WR, 80+ = 0% WR
    "signal_score_s": 95,      # S grade rarely fires — only exceptional
    "signal_score_a": 82,      # A grade: 80-82 only (not 80-90)
    "signal_score_b": 70,      # B grade: 70-82 = best historical WR
    "signal_score_c": 65,      # C grade: below min_score, blocked

    # V6.3: Hard reject composite >= this value outright — score paradox
    # data shows B (70-82) outperformed A/S; 84+ = likely already-flown.
    "signal_score_ceiling": 84,

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
    "short_resistance_max_pct":  5.0,   # relaxed from 3% — allows shorts in strong downtrends

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
    "max_signals_per_run": 3,     # data: fewer better quality signals

    # Circuit breaker
    "max_daily_losses": 3,

    # RS cap — if coin already 10x+ vs BTC, it pumped already
    "rs_max_ratio": 8.0,          # tightened: 10x+ = chasing
    "vol_max_ratio": 1.5,          # tightened from 2.0: catch moves earlier,
                                    # before volume fully confirms (was letting
                                    # signals fire on coins that already flew)

    # Price staleness guard — reject alert if live price has drifted this
    # much (%) from the computed entry by the time we're about to send.
    # Prevents "sobrang late na" signals after a long scan cycle.
    "max_entry_drift_pct": 0.6,

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
    "config_version":   "2.1.0",
    "strategy_version": "6.1.0",
}
