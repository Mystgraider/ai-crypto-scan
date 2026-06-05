CONFIG = {

    # Exchange
    "exchange": "okx",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds
    "min_score": 65,
    "signal_score_s": 90,
    "signal_score_a": 80,
    "signal_score_b": 70,
    "signal_score_c": 65,

    # ADX gate (documented — enforced in trend_engine)
    "adx_min": 20,

    # BTC Filter
    "btc_symbol": "BTC/USDT:USDT",   # OKX perp swap
    "btc_filter_enabled": True,

    # Multi-timeframe
    "mtf_enabled": True,
    "mtf_reject_counter_trend": True,  # reject signals against 4H

    # Volume spike
    "volume_spike_min_tier": "NORMAL",  # WEAK | NORMAL | ELEVATED | HIGH | EXTREME

    # Risk
    "min_rr": 2.0,
    "min_sl_pct": 0.005,
    "sl_atr_mult": 1.5,
    "tp1_atr_mult": 2.0,
    "tp2_atr_mult": 3.0,
    "tp3_atr_mult": 5.0,

    # Cooldown
    "signal_cooldown_hours": 12,

    # Max signals per scan run (anti-spam)
    "max_signals_per_run": 5,

    # Versions
    "db_version": "1.0.0",
    "config_version": "1.2.0",
    "strategy_version": "5.2.0",
}
