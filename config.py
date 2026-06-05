CONFIG = {

    # Exchange
    "exchange": "okx",

    # Scanning
    "top_coins_limit": 300,
    "timeframe": "1h",
    "ohlcv_limit": 100,
    "ohlcv_4h_limit": 50,

    # Signal thresholds
    "min_score": 60,           # both trend + quality must pass
    "signal_score_s": 90,
    "signal_score_a": 80,
    "signal_score_b": 70,
    "signal_score_c": 60,

    # ADX gate (enforced in trend_engine)
    "adx_min": 20,

    # BTC Filter
    "btc_symbol": "BTC/USDT:USDT",
    "btc_filter_enabled": True,

    # Multi-timeframe
    "mtf_enabled": True,
    "mtf_reject_counter_trend": True,

    # Volume spike minimum tier allowed
    "volume_spike_min_tier": "NORMAL",

    # ── Risk / RR ─────────────────────────────────────────────────────────
    # FIXED: SL=1.0x TP1=2.5x → RR = 2.5 (was 1.5/2.0 = RR 1.33, always failed)
    "min_rr":        2.0,
    "min_sl_pct":    0.003,    # lowered from 0.005 — allows low-volatility coins
    "sl_atr_mult":   1.0,      # 1× ATR stop loss (tighter, more precise)
    "tp1_atr_mult":  2.5,      # 2.5× ATR → RR = 2.5 ✅
    "tp2_atr_mult":  4.0,      # 4× ATR
    "tp3_atr_mult":  6.0,      # 6× ATR (runner target)

    # Cooldown
    "signal_cooldown_hours": 4,   # reduced from 12h — allow re-entry on new setups

    # Max signals per run (anti-spam)
    "max_signals_per_run": 5,

    # Versions
    "db_version":      "1.0.0",
    "config_version":  "1.4.0",
    "strategy_version": "5.4.0",
}
