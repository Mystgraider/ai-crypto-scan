CONFIG = {

    # Exchange
    "exchange": "okx",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds
    "min_score": 60,
    "signal_score_s": 90,
    "signal_score_a": 80,
    "signal_score_b": 70,
    "signal_score_c": 60,

    # ADX gate
    "adx_min": 20,

    # BTC Filter
    "btc_symbol":        "BTC/USDT:USDT",
    "btc_filter_enabled": True,
    # BTC RSI protection (anti dead-cat-bounce)
    "btc_rsi_short_floor": 42,   # block shorts if BTC RSI < 42 (bounce risk)
    "btc_rsi_long_ceil":   72,   # block longs  if BTC RSI > 72 (pullback risk)
    # BTC 4H must confirm BEAR before shorts allowed
    "btc_require_4h_bear_for_short": True,

    # Multi-timeframe
    "mtf_enabled": True,
    "mtf_reject_counter_trend": True,

    # S/R: SHORT requires resistance ceiling within this % above price
    "short_requires_resistance": True,
    "short_resistance_max_pct":  3.0,

    # ── Risk — direction-aware SL sizing ──────────────────────────────────
    # LONG: tight SL (trend should hold)
    "sl_atr_mult":   1.0,    # SL = 1× ATR below entry
    "tp1_atr_mult":  2.5,    # TP1 = 2.5× ATR → RR = 2.5
    "tp2_atr_mult":  4.0,
    "tp3_atr_mult":  6.0,

    # SHORT: wider SL (bear bounces are violent)
    "short_sl_atr_mult":  2.0,   # SL = 2× ATR above entry
    "short_tp1_atr_mult": 4.5,   # TP1 = 4.5× ATR → RR = 2.25
    "short_tp2_atr_mult": 6.0,
    "short_tp3_atr_mult": 8.0,

    "min_rr":     2.0,
    "min_sl_pct": 0.003,

    # Cooldown
    "signal_cooldown_hours": 4,

    # Max signals per run
    "max_signals_per_run": 5,

    # Versions
    "db_version":       "1.0.0",
    "config_version":   "1.5.0",
    "strategy_version": "5.5.0",
}
