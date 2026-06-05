CONFIG = {

    # Exchange
    "exchange": "okx",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,

    # Signal thresholds
    # trend_score + quality_score both must pass min_score
    # Lower = more signals but lower quality
    # Higher = fewer signals but higher quality
    "min_score": 65,           # was 70 — allow slightly more candidates
    "signal_score_s": 90,      # Grade S
    "signal_score_a": 80,      # Grade A
    "signal_score_b": 70,      # Grade B
    "signal_score_c": 65,      # Grade C (minimum fired)

    # ADX — hard gate in trend_engine (no trend = no signal)
    "adx_min": 20,             # documented here for reference

    # Risk
    "min_rr": 2.0,
    "min_sl_pct": 0.005,
    "sl_atr_mult": 1.5,
    "tp1_atr_mult": 2.0,
    "tp2_atr_mult": 3.0,
    "tp3_atr_mult": 5.0,

    # Cooldown — same symbol won't fire again within this window
    "signal_cooldown_hours": 12,

    # Max signals per scan cycle (prevent spam)
    "max_signals_per_run": 5,

    # Versions
    "db_version": "1.0.0",
    "config_version": "1.1.0",
    "strategy_version": "5.1.0",
}
