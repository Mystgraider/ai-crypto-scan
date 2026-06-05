CONFIG = {

    # Exchange
    "exchange": "okx",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,

    # Signal thresholds
    "min_score": 70,
    "signal_score_s": 90,
    "signal_score_a": 80,
    "signal_score_b": 70,

    # Risk
    "min_rr": 2.0,
    "min_sl_pct": 0.005,
    "sl_atr_mult": 1.5,
    "tp1_atr_mult": 2.0,
    "tp2_atr_mult": 3.0,
    "tp3_atr_mult": 5.0,

    # Cooldown
    "signal_cooldown_hours": 12,

    # Versions
    "db_version": "1.0.0",
    "config_version": "1.0.0",
    "strategy_version": "5.0.0",
}
