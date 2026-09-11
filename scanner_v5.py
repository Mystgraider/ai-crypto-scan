"""
Elite Futures Scanner V6.2
==============================
V6.2 Fixes:
  - Vol > 2.0x now hard-blocked in main scan loop (was only in QualityEngine
    at 3.0x). BA/USDT at 3.06x fired Grade S and hit SL — confirmed kill.
  - Signal tracker now expires OPEN signals >72h as EXPIRED status.
    Prevents stale signals (6-day-old OPEN) from polluting analytics.
  - Restored signals history from archive (V6.1.3 had reset signals.csv).

V6.1.1 Fix (no strategy changes):
  - quality_engine.score() now accepts stoch_k, bb_pct_b, macd_hist
    (was crashing with "unexpected keyword argument" on every symbol
    in V6.1 -> 0 candidates every scan). Params accepted but unused —
    scoring formula is identical to V6.1.

V6.1 (data-driven, unchanged):
  - RSI 55-60 / Vol 1.0-1.5x sweet spots from 16 closed signals
  - Vol > 3.0x hard block (extreme spike = reversal risk)
"""

from loaders.top_symbols_loader  import TopSymbolsLoader
from loaders.market_data_loader  import MarketDataLoader
from indicators.indicators       import Indicators
from engines.trend_engine        import TrendEngine
from engines.quality_engine      import QualityEngine
from engines.validator           import SignalValidator
from engines.btc_filter          import BTCFilter
from engines.multiframe_engine   import MultiFrameEngine
from engines.volume_spike        import VolumeSpikeEngine
from engines.relative_strength   import RelativeStrengthEngine
from engines.support_resistance  import SupportResistanceEngine
from engines.volume_profile      import VolumeProfileEngine
from engines.rrce_engine         import RRCEEngine
from engines.position_sizer      import PositionSizer
from engines.live_entry_integrity import revalidate as revalidate_live_entry
from engines.funding_engine      import FundingEngine
from engines.beta_filter         import BetaFilter
from engines.oi_engine           import OIEngine
from engines.circuit_breaker     import check as circuit_check
from alerts.telegram_alerts      import send_telegram_alert, format_signal
from storage.signal_logger       import save_signal
from storage.cooldown_manager    import is_on_cooldown, set_cooldown
from storage.rrce_watchlist      import active_count, record_stage2_setup
from tracker.signal_tracker      import SignalTracker
from reports.analytics_engine    import AnalyticsEngine
from ai.signal_ranker            import AISignalRanker
from ai.confidence_engine        import ConfidenceEngine
from config                      import CONFIG


def grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]: return "S"
    if score >= CONFIG["signal_score_a"]: return "A"
    if score >= CONFIG["signal_score_b"]: return "B"
    if score >= CONFIG["signal_score_c"]: return "C"
    return "D"


def is_dated_futures(symbol: str) -> bool:
    return "-" in symbol.split(":")[-1] if ":" in symbol else False


STOCK_TOKENS = {
    "NIO/USDT:USDT", "NVDA/USDT:USDT", "AAPL/USDT:USDT",
    "TSLA/USDT:USDT", "AMZN/USDT:USDT", "GOOGL/USDT:USDT",
    "MSFT/USDT:USDT", "META/USDT:USDT", "PLTR/USDT:USDT",
    "ARQQ/USDT:USDT", "AXTI/USDT:USDT", "EWY/USDT:USDT",
    "ASML/USDT:USDT", "AMAT/USDT:USDT", "CRWD/USDT:USDT",
    "ADBE/USDT:USDT", "TWLO/USDT:USDT", "SPIR/USDT:USDT",
    "MDB/USDT:USDT",  "IWM/USDT:USDT",  "SATSSTOCK/USDT:USDT",
    "SATL/USDT:USDT", "DXYZ/USDT:USDT", "QNTSTOCK/USDT:USDT",
    "BX/USDT:USDT",   "AWE/USDT:USDT",  "SLX/USDT:USDT",
    "C/USDT:USDT",    "MORPHO/USDT:USDT",
    # Meme coins — 0% WR, too volatile
    "SHIB/USDT:USDT", "DOGE/USDT:USDT", "PEPE/USDT:USDT",
    "BONK/USDT:USDT", "WIF/USDT:USDT",  "FLOKI/USDT:USDT",
    "NEIRO/USDT:USDT","MEME/USDT:USDT", "PEOPLE/USDT:USDT",
}


def is_stock_token(symbol: str) -> bool:
    return symbol in STOCK_TOKENS


def main():

    print("=" * 55)
    print("🚀 Elite Futures Scanner V6.1.3")
    print("=" * 55)

    import time as _time
    _scan_start_time = _time.time()
    # V6.9.6: GH Actions workflow timeout is 10 min. Now that
    # require_trend_gate=False lets far more symbols reach RRCE
    # (which does 2 extra API fetches per direction tried, up to 4 per
    # symbol), a full 300-symbol scan risks blowing the timeout with
    # zero results committed. Stop starting new symbols past this
    # budget so whatever's already found still gets saved.
    _scan_time_budget_sec = CONFIG.get("scan_time_budget_sec", 480)

    market_loader  = MarketDataLoader()
    exchange       = market_loader.exchange
    trend_engine   = TrendEngine()
    quality_engine = QualityEngine()
    validator      = SignalValidator()
    btc_filter     = BTCFilter()
    mtf_engine     = MultiFrameEngine()
    spike_engine   = VolumeSpikeEngine()
    rs_engine      = RelativeStrengthEngine()
    sr_engine      = SupportResistanceEngine()
    vp_engine      = VolumeProfileEngine()
    rrce_engine = RRCEEngine(
        eq_tolerance_pct=CONFIG["rrce_default_eq_tolerance_pct"]
    )
    range_rrce_engine = RRCEEngine(
        eq_tolerance_pct=CONFIG["rrce_range_eq_tolerance_pct"]
    )

    # V6.9.20 (EXPERIMENT ONLY): a second, isolated RRCE instance on
    # 4H/1H timeframes with a wider Equal-High/Low tolerance (0.15%
    # was tuned for 15m; 4H needs more room since price moves further
    # between swing points at that scale). This does NOT feed into
    # candidates, signals.csv, or Telegram — it only writes its own
    # observation log so we can see if 4H can find setups at all
    # without risking the verified 15m/5m live system.
    experiment_4h_engine = RRCEEngine(swing_lookback=10, eq_tolerance_pct=0.6)
    experiment_4h_log = []

    sizer          = PositionSizer()
    funding_engine = FundingEngine()
    beta_filter    = BetaFilter()
    oi_engine      = OIEngine()

    # ── Step 1: BTC Regime ─────────────────────────────────────────────────
    print("\n[1/8] BTC Market Filter...")

    btc_regime = {
        "regime": "UNKNOWN", "allow_long": True, "allow_short": True,
        "adx": 0, "rsi": 50, "reason": "BTC filter disabled"
    }
    btc_closes = []

    if CONFIG["btc_filter_enabled"]:
        try:
            btc_1h     = market_loader.get_1h(CONFIG["btc_symbol"], limit=100)
            btc_1h     = Indicators.apply(btc_1h)
            btc_closes = btc_1h["close"].tolist()

            btc_4h = None
            try:
                _btc_4h_raw = market_loader.get_4h(CONFIG["btc_symbol"], limit=100)
                btc_4h = Indicators.apply(_btc_4h_raw)
            except Exception:
                btc_4h = None

            btc_regime = btc_filter.analyze(btc_1h, btc_4h)
            print(f"      BTC: {btc_regime['regime']} | ADX:{btc_regime['adx']} | RSI:{btc_regime['rsi']}")
            print(f"      LONG:{btc_regime['allow_long']} | SHORT:{btc_regime['allow_short']}")
            print(f"      Reason: {btc_regime['reason']}")
        except Exception as e:
            import traceback
            print(f"      ⚠️ BTC filter failed: {type(e).__name__}: {e}")
            print(f"      {traceback.format_exc().splitlines()[-1]}")
            print(f"      Allowing all signals")

    # ── Step 1b: Circuit Breaker ───────────────────────────────────────────
    print("\n[1b] Circuit Breaker...")
    breaker = circuit_check()
    if breaker["is_tripped"]:
        print(f"      🔴 TRIPPED — {breaker['losses_today']} losses today. Signals paused.")
        return
    print(f"      ✅ OK — {breaker['losses_today']}/{breaker['max_losses']} losses today")

    # ── Step 2: Load Symbols ───────────────────────────────────────────────
    print("\n[2/8] Loading top symbols...")
    symbols = TopSymbolsLoader().get_top_symbols()
    print(f"      ✅ {len(symbols)} symbols loaded")

    if not symbols:
        print("      ❌ No symbols — check exchange config")
        return

    # ── Step 3: Scan ───────────────────────────────────────────────────────
    print(f"\n[3/8] Scanning {len(symbols)} symbols...")

    candidates = []
    stage1_position_samples = []  # V6.9.19: real position_pct values on Stage 1 failures
    stage2_pool_counts = []       # V6.9.23: how many Equal High/Low pools were found (even when unswept)

    TRACE_SYMBOLS = {"ETH/USDT:USDT", "SOL/USDT:USDT", "BNB/USDT:USDT", "XRP/USDT:USDT", "LTC/USDT:USDT"}
    symbol_trace_log = []
    def _trace(sym, stage, **extra):
        if sym in TRACE_SYMBOLS:
            symbol_trace_log.append({"symbol": sym, "stage": stage, **extra})
    skip = {
        "cooldown": 0, "dated": 0, "btc": 0, "trend": 0,
        "funding": 0, "high_beta": 0, "sr_no_ceil": 0,
        "weak_rs": 0, "mtf": 0, "quality": 0, "risk": 0,
        "d_grade": 0, "overextended": 0, "rrce_invalid": 0,
        "rrce_stage1_passed": 0, "rrce_stage2_passed": 0,
        "rrce_stage3_passed": 0, "rrce_stage4_valid": 0,
        "rrce_entry_away": 0, "rrce_entry_invalid": 0,
        "time_budget_stop": 0, "errors": 0
    }

    for symbol in symbols:

        if _time.time() - _scan_start_time > _scan_time_budget_sec:
            print(f"      ⏱️  Time budget ({_scan_time_budget_sec}s) reached — "
                  f"stopping early with {len(candidates)} candidate(s) found so far, "
                  f"{symbols.index(symbol)}/{len(symbols)} symbols processed.")
            skip["time_budget_stop"] = len(symbols) - symbols.index(symbol)
            break

        if symbol == CONFIG["btc_symbol"]:
            continue
        if is_dated_futures(symbol):
            skip["dated"] += 1
            _trace(symbol, "dated_or_stock_token")
            continue
        if is_stock_token(symbol):
            skip["dated"] += 1
            _trace(symbol, "dated_or_stock_token")
            continue
        if is_on_cooldown(symbol):
            skip["cooldown"] += 1
            _trace(symbol, "cooldown")
            continue

        try:
            df_1h  = market_loader.get_1h(symbol)
            df_1h  = Indicators.apply(df_1h)

            if len(df_1h) < 2:
                skip["errors"] += 1
                continue

            live = df_1h.iloc[-1]
            prev = df_1h.iloc[-2]

            req = ["close","ema_20","ema_50","atr","adx","rsi","roc","rel_volume",
                   "macd","macd_sig","macd_hist","bb_pct_b","stoch_k","stoch_d"]
            if prev[req].isnull().any():
                skip["errors"] += 1
                continue

            price      = float(live["close"])
            ema20      = float(prev["ema_20"])
            ema50      = float(prev["ema_50"])
            atr        = float(prev["atr"])
            adx        = float(prev["adx"])
            rsi        = float(prev["rsi"])
            roc        = float(prev["roc"])
            rel_volume = float(prev["rel_volume"])
            macd       = float(prev["macd"])
            macd_sig   = float(prev["macd_sig"])
            macd_hist  = float(prev["macd_hist"])
            bb_pct_b   = float(prev["bb_pct_b"])
            stoch_k    = float(prev["stoch_k"])
            stoch_d    = float(prev["stoch_d"])

            trend = trend_engine.analyze(
                price=price, ema20=ema20, ema50=ema50,
                adx=adx, roc=roc,
                macd=macd, macd_sig=macd_sig, macd_hist=macd_hist,
                stoch_k=stoch_k, stoch_d=stoch_d,
                bb_pct_b=bb_pct_b,
            )
            trend_score = trend["score"]

            if CONFIG.get("require_trend_gate", True):
                if trend["direction"] == "NONE":
                    skip["trend"] += 1
                    _trace(symbol, "trend_none_and_gate_required")
                    reason_key = f"trend_reason_{trend.get('filters', 'unknown')}"
                    skip[reason_key] = skip.get(reason_key, 0) + 1
                    continue
                candidate_directions = [trend["direction"]]
            else:
                if trend["direction"] == "NONE":
                    candidate_directions = ["LONG", "SHORT"]
                else:
                    candidate_directions = [trend["direction"]]

            for direction in candidate_directions:

                if not CONFIG.get("require_trend_gate", True) and trend["direction"] == "NONE":
                    effective_trend_score = CONFIG["min_score"]
                else:
                    effective_trend_score = trend_score

                if CONFIG["btc_filter_enabled"]:
                    if direction == "LONG"  and not btc_regime["allow_long"]:
                        skip["btc"] += 1
                        _trace(symbol, "btc_regime_block", direction=direction, regime=btc_regime.get("regime"))
                        continue
                    if direction == "SHORT" and not btc_regime["allow_short"]:
                        skip["btc"] += 1
                        _trace(symbol, "btc_regime_block", direction=direction, regime=btc_regime.get("regime"))
                        continue

                if CONFIG.get("block_bear_regime", True) and btc_regime["regime"] in ("BEAR", "BEAR_CAUTION"):
                    skip["btc"] += 1
                    _trace(symbol, "btc_regime_block", direction=direction, regime=btc_regime.get("regime"))
                    continue
                if CONFIG.get("pause_shorts", True) and direction == "SHORT":
                    skip["btc"] += 1
                    _trace(symbol, "btc_regime_block", direction=direction, regime=btc_regime.get("regime"))
                    continue

                if btc_regime["regime"] == "RANGE" and trend["direction"] != "NONE":
                    if effective_trend_score < CONFIG.get("range_regime_min_score", 85):
                        skip["btc"] += 1
                        _trace(symbol, "btc_regime_block", direction=direction, regime=btc_regime.get("regime"))
                        continue

                funding_result = {"funding_pct": 0.0, "funding_pct_raw": 0.0, "short_score_adj": 0}
                if CONFIG["funding_enabled"]:
                    fr = funding_engine.fetch_funding(exchange, symbol)
                    funding_result = funding_engine.analyze(fr)
                    funding_result["funding_pct_raw"] = fr
                    if direction == "LONG"  and not funding_result["long_ok"]:
                        skip["funding"] += 1
                        _trace(symbol, "funding_block", direction=direction)
                        continue
                    if direction == "SHORT" and not funding_result["short_ok"]:
                        skip["funding"] += 1
                        _trace(symbol, "funding_block", direction=direction)
                        continue

                beta_result = {"beta_label": "N/A", "beta": 1.0}
                if CONFIG["beta_filter_enabled"] and direction == "SHORT":
                    coin_closes_beta = df_1h["close"].tolist()
                    beta_result = beta_filter.evaluate(
                        symbol=symbol, direction=direction,
                        coin_closes=coin_closes_beta, btc_closes=btc_closes
                    )
                    if not beta_result["short_ok"]:
                        skip["high_beta"] += 1
                        _trace(symbol, "beta_block", direction=direction)
                        continue

                sr_levels = sr_engine.find_levels(df_1h)
                sr_bonus  = sr_engine.score_bonus(direction, sr_levels)

                bb_width_pctile = float(df_1h["bb_width_pctile"].iloc[-2]) \
                    if "bb_width_pctile" in df_1h.columns else 1.0
                squeeze_bonus = 8 if bb_width_pctile <= 0.2 else 0

                vp_profile = vp_engine.build_profile(df_1h)
                vp_bonus   = vp_engine.score_bonus(direction, price, vp_profile)

                rrce_bonus = 0.0
                rrce_result = None
                try:
                    _df_rrce_15m_raw = market_loader.get_15m(symbol)
                    _df_rrce_15m = Indicators.apply(_df_rrce_15m_raw)
                    _df_rrce_5m_raw = market_loader.get_5m(symbol)
                    _df_rrce_5m = Indicators.apply(_df_rrce_5m_raw)

                    if len(_df_rrce_15m) >= 20 and len(_df_rrce_5m) >= 20:
                        is_range_regime = btc_regime["regime"] == "RANGE"
                        active_rrce_engine = range_rrce_engine if is_range_regime else rrce_engine
                        patience_bars = (
                            CONFIG["rrce_range_patience_bars"] if is_range_regime
                            else CONFIG["rrce_default_patience_bars"]
                        )
                        rrce_result = active_rrce_engine.evaluate(
                            df_htf=_df_rrce_15m, df_mtf=_df_rrce_15m,
                            df_ltf_confirm=_df_rrce_5m, df_ltf_exec=_df_rrce_5m,
                            direction=direction, price=price,
                            patience_bars=patience_bars,
                        )
                        rrce_bonus = rrce_result["bonus"]
                except Exception as _rrce_e:
                    print(f"      ⚠️  {symbol} RRCE multi-TF fetch/eval failed: {_rrce_e}")

                try:
                    _exp_4h_raw = market_loader.get_4h(symbol)
                    _exp_4h = Indicators.apply(_exp_4h_raw)
                    _exp_1h = Indicators.apply(df_1h.copy())
                    if len(_exp_4h) >= 20 and len(_exp_1h) >= 20:
                        _exp_result = experiment_4h_engine.evaluate(
                            df_htf=_exp_4h, df_mtf=_exp_4h,
                            df_ltf_confirm=_exp_1h, df_ltf_exec=_exp_1h,
                            direction=direction, price=price,
                        )
                        experiment_4h_log.append({
                            "symbol": symbol, "direction": direction,
                            "valid": _exp_result.get("valid"),
                            "failed_at": _exp_result.get("failed_at"),
                            "stage1_position_pct": (_exp_result.get("stage1") or {}).get("position_pct"),
                        })
                except Exception as _exp_e:
                    experiment_4h_log.append({"symbol": symbol, "direction": direction, "error": str(_exp_e)})

                if rrce_result:
                    s1_data = rrce_result.get("stage1")
                    s2_data = rrce_result.get("stage2")
                    s3_data = rrce_result.get("stage3")
                    if s1_data and s1_data.get("passed"):
                        skip["rrce_stage1_passed"] += 1
                    if s2_data:
                        pools = s2_data.get("pools")
                        if pools is not None:
                            stage2_pool_counts.append(len(pools))
                        if s2_data.get("passed"):
                            skip["rrce_stage2_passed"] += 1
                            try:
                                watchlist_count = record_stage2_setup(
                                    symbol=symbol, direction=direction,
                                    regime=btc_regime["regime"], stage1=s1_data,
                                    stage2=s2_data, ttl_hours=CONFIG["rrce_watchlist_hours"],
                                )
                                skip["rrce_watchlist_active"] = watchlist_count
                            except Exception as watchlist_error:
                                print(f"      ⚠️  RRCE watchlist write failed: {watchlist_error}")
                    if s3_data and s3_data.get("passed"):
                        skip["rrce_stage3_passed"] += 1
                    if rrce_result.get("valid"):
                        skip["rrce_stage4_valid"] += 1

                if not rrce_result or not rrce_result.get("valid"):
                    skip["rrce_invalid"] = skip.get("rrce_invalid", 0) + 1
                    _trace(symbol, "rrce_invalid", direction=direction)
                    fail_stage = rrce_result.get("failed_at", "no_data") if rrce_result else "fetch_error"
                    stage_key = f"rrce_fail_{fail_stage}"
                    skip[stage_key] = skip.get(stage_key, 0) + 1
                    if fail_stage == "stage1_range" and rrce_result:
                        s1_data = rrce_result.get("stage1")
                        if s1_data and "position_pct" in s1_data:
                            stage1_position_samples.append(s1_data["position_pct"])
                    if fail_stage == "stage2_retail_liquidity" and rrce_result:
                        s2_data = rrce_result.get("stage2")
                        if s2_data:
                            reason = s2_data.get("reason", "pool_found_not_swept")
                            skip[f"s2_reason_{reason}"] = skip.get(f"s2_reason_{reason}", 0) + 1
                    if fail_stage == "stage3_confirmation" and rrce_result:
                        s3_data = rrce_result.get("stage3")
                        if s3_data:
                            reason = s3_data.get("reason", "unknown")
                            skip[f"s3_reason_{reason}"] = skip.get(f"s3_reason_{reason}", 0) + 1
                    continue

                rrce_risk = active_rrce_engine.live_entry_levels(
                    direction=direction,
                    live_price=price,
                    stage4=rrce_result["stage4"],
                    max_deviation_pct=CONFIG["rrce_entry_max_deviation_pct"],
                    min_rr=CONFIG["min_rr"],
                )
                if not rrce_risk["valid"]:
                    if rrce_risk["reason"] == "price_away_from_rrce_entry":
                        skip["rrce_entry_away"] += 1
                    else:
                        skip["rrce_entry_invalid"] += 1
                    _trace(symbol, "rrce_entry_block", direction=direction,
                           reason=rrce_risk["reason"])
                    continue

                if direction == "SHORT" and CONFIG["short_requires_resistance"]:
                    if not sr_engine.short_has_ceiling(sr_levels, CONFIG["short_resistance_max_pct"]):
                        skip["sr_no_ceil"] += 1
                        _trace(symbol, "sr_no_ceiling", direction=direction)
                        continue

                coin_closes = df_1h["close"].tolist()
                if len(btc_closes) >= 21:
                    rs = rs_engine.calculate(coin_closes, btc_closes)
                else:
                    rs = {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}

                if rs["rs_label"] == "WEAK":
                    skip["weak_rs"] += 1
                    _trace(symbol, "weak_rs", direction=direction)
                    continue

                rs_max = CONFIG.get("rs_max_ratio", 10.0)
                if rs.get("rs_ratio", 1.0) > rs_max:
                    skip["weak_rs"] += 1
                    _trace(symbol, "weak_rs", direction=direction)
                    continue

                vol_max = CONFIG.get("vol_max_ratio", 2.0)
                if rel_volume > vol_max:
                    skip["quality"] += 1
                    _trace(symbol, "quality_block", direction=direction)
                    continue

                spike = spike_engine.analyze(rel_volume)

                mtf_status     = "SKIPPED"
                mtf_multiplier = 1.0
                mtf_4h_dir     = "UNKNOWN"
                mtf_15m_dir    = "UNKNOWN"

                if CONFIG["mtf_enabled"]:
                    trend_15m = None
                    try:
                        _df_15m_raw = market_loader.get_15m(symbol) if hasattr(market_loader, "get_15m") else None
                        if _df_15m_raw is not None:
                            df_15m = Indicators.apply(_df_15m_raw)
                            if len(df_15m) >= 2 and not df_15m.iloc[-2][["ema_20","ema_50","adx"]].isnull().any():
                                trend_15m   = mtf_engine.analyze_15m(df_15m)
                                mtf_15m_dir = trend_15m["direction"]
                    except Exception:
                        trend_15m = None

                    for _attempt in range(2):
                        try:
                            _df_4h_raw = market_loader.get_4h(symbol)
                            df_4h      = Indicators.apply(_df_4h_raw)
                            if len(df_4h) >= 2 and not df_4h.iloc[-2][["ema_20","ema_50","adx"]].isnull().any():
                                tf4         = mtf_engine.analyze_4h(df_4h)
                                mtf_4h_dir  = tf4["direction"]
                                mtf_4h_rsi  = tf4.get("rsi", 50.0)
                                confirm     = mtf_engine.confirm(direction, tf4, trend_15m)
                                mtf_status     = confirm["status"]
                                mtf_multiplier = confirm["multiplier"]
                                break
                        except Exception:
                            if _attempt == 1:
                                if adx >= 30:
                                    mtf_status     = "ALLOWED"
                                    mtf_multiplier = 0.95
                                    mtf_4h_dir     = "PROXY"
                                else:
                                    mtf_status     = "SKIPPED"
                                    mtf_multiplier = 1.0

                if CONFIG["mtf_reject_counter_trend"] and mtf_status in ("REJECTED", "SKIPPED"):
                    skip["mtf"] += 1
                    _trace(symbol, "mtf_block", direction=direction)
                    continue

                quality_score = quality_engine.score(
                    rel_volume=rel_volume, rsi=rsi, direction=direction,
                    stoch_k=stoch_k, bb_pct_b=bb_pct_b, macd_hist=macd_hist,
                )
                effective_quality_score = quality_score
                if not CONFIG.get("require_quality_engine", True) and quality_score < CONFIG["min_score"]:
                    effective_quality_score = CONFIG["min_score"]

                oi_result = {"oi_signal": "NEUTRAL", "score_adj": 0, "oi_change_pct": 0}
                if CONFIG["oi_enabled"]:
                    try:
                        oi_data = oi_engine.fetch_oi(exchange, symbol)
                        if oi_data["available"]:
                            price_chg = float(df_1h["close"].pct_change().iloc[-1] * 100)
                            oi_result = oi_engine.analyze(
                                current_oi=oi_data["current_oi"],
                                previous_oi=oi_data["previous_oi"],
                                price_change=price_chg,
                                direction=direction,
                            )
                    except Exception:
                        pass

                risk = rrce_risk

                if not validator.validate(direction, effective_trend_score, effective_quality_score, risk):
                    if risk is None:
                        skip["risk"] += 1
                        _trace(symbol, "risk_none", direction=direction)
                    else:
                        skip["quality"] += 1
                        _trace(symbol, "quality_block", direction=direction)
                    continue

                oi_adj    = oi_result["score_adj"]
                fund_adj  = funding_result.get("short_score_adj", 0) if direction == "SHORT" else 0
                base      = effective_trend_score * 0.6 + effective_quality_score * 0.4
                composite = min(100.0, max(0.0, round(
                    (base + sr_bonus + oi_adj + fund_adj + squeeze_bonus + vp_bonus + rrce_bonus) * mtf_multiplier, 2
                )))
                g = grade_score(composite)

                if g == "D":
                    skip["d_grade"] += 1
                    _trace(symbol, "d_grade_block", direction=direction)
                    continue

                if composite >= CONFIG.get("signal_score_ceiling", 84):
                    skip["overextended"] = skip.get("overextended", 0) + 1
                    continue

                _trace(symbol, "CANDIDATE_FOUND", direction=direction)
                candidates.append({
                    "symbol":          symbol,
                    "direction":       direction,
                    "trend_score":     effective_trend_score,
                    "quality_score":   effective_quality_score,
                    "rs_score":        rs["rs_score"],
                    "rs_label":        rs["rs_label"],
                    "rs_ratio":        rs.get("rs_ratio", 1.0),
                    "sr_bonus":        sr_bonus,
                    "sr_support":      sr_levels["nearest_support"],
                    "sr_resistance":   sr_levels["nearest_resistance"],
                    "composite":       composite,
                    "grade":           g,
                    "rr":              risk["rr"],
                    "entry":           risk["entry"],
                    "sl":              risk["sl"],
                    "tp1":             risk["tp1"],
                    "tp2":             risk["tp2"],
                    "tp3":             risk["tp3"],
                    "_rrce_stage4":   rrce_result["stage4"],
                    "_rrce_engine_mode": "range" if is_range_regime else "default",
                    "rsi":             round(rsi, 2),
                    "adx":             round(adx, 2),
                    "rel_volume":      round(rel_volume, 2),
                    "spike_tier":      spike["tier"],
                    "macd_hist":       round(macd_hist, 6),
                    "stoch_k":         round(stoch_k, 2),
                    "bb_pct_b":        round(bb_pct_b, 3),
                    "mtf_status":      mtf_status,
                    "mtf_4h":          mtf_4h_dir,
                    "mtf_15m":         mtf_15m_dir,
                    "btc_regime":      btc_regime["regime"],
                    "funding_pct":     str(funding_result.get("funding_pct", 0)),
                    "funding_pct_raw": funding_result.get("funding_pct_raw", 0.0),
                    "oi_signal":      oi_result["oi_signal"],
                    "beta_label":      beta_result.get("beta_label", "N/A"),
                })

        except Exception as e:
            skip["errors"] += 1
            if "Insufficient candles" not in str(e) and "NaN" not in str(e):
                print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate(s)")
    print(
        f"      📊 cd:{skip['cooldown']} dated:{skip['dated']} "
        f"btc:{skip['btc']} trend:{skip['trend']} "
        f"fund:{skip['funding']} beta:{skip['high_beta']} "
        f"mtf:{skip['mtf']} sr:{skip['sr_no_ceil']} "
        f"rs:{skip['weak_rs']} q:{skip['quality']} "
        f"risk:{skip['risk']} d:{skip['d_grade']} "
        f"overext:{skip['overextended']} rrce:{skip['rrce_invalid']} "
        f"rrce_away:{skip['rrce_entry_away']} "
        f"budget_stop:{skip['time_budget_stop']} err:{skip['errors']}"
    )

    try:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        debug_row = {
            "ts": _dt.now(_tz.utc).isoformat(),
            "symbols_scanned": len(symbols),
            "candidates": len(candidates),
            "btc_regime_label": btc_regime.get("regime"),
            "btc_regime_allow_long": btc_regime.get("allow_long"),
            "btc_regime_allow_short": btc_regime.get("allow_short"),
            "btc_regime_adx": btc_regime.get("adx"),
            "btc_regime_rsi": btc_regime.get("rsi"),
            "btc_regime_reason": btc_regime.get("reason"),
            "stage1_position_pct_count": len(stage1_position_samples),
            "stage1_position_pct_min": round(min(stage1_position_samples), 1) if stage1_position_samples else None,
            "stage1_position_pct_max": round(max(stage1_position_samples), 1) if stage1_position_samples else None,
            "stage1_position_pct_avg": round(sum(stage1_position_samples)/len(stage1_position_samples), 1) if stage1_position_samples else None,
            "stage1_position_pct_median": round(sorted(stage1_position_samples)[len(stage1_position_samples)//2], 1) if stage1_position_samples else None,
            "stage2_pool_count_avg": round(sum(stage2_pool_counts)/len(stage2_pool_counts), 2) if stage2_pool_counts else None,
            "stage2_zero_pool_pct": round(sum(1 for c in stage2_pool_counts if c == 0) / len(stage2_pool_counts) * 100, 1) if stage2_pool_counts else None,
            "rrce_watchlist_active": active_count(CONFIG["rrce_watchlist_hours"]),
            **skip,
        }
        debug_path = "storage/scan_debug_log.jsonl"
        with open(debug_path, "a") as f:
            f.write(_json.dumps(debug_row) + "\n")
    except Exception as _e:
        print(f"      ⚠️  debug log write failed: {_e}")

    try:
        exp_valid = sum(1 for r in experiment_4h_log if r.get("valid"))
        exp_row = {
            "ts": _dt.now(_tz.utc).isoformat(),
            "total_checked": len(experiment_4h_log),
            "valid_count": exp_valid,
            "results": experiment_4h_log,
        }
        with open("storage/experiment_4h_log.jsonl", "a") as f:
            f.write(_json.dumps(exp_row) + "\n")
    except Exception as _e:
        print(f"      ⚠️  experiment log write failed: {_e}")

    try:
        trace_row = {"ts": _dt.now(_tz.utc).isoformat(), "trace": symbol_trace_log}
        with open("storage/symbol_trace_log.jsonl", "a") as f:
            f.write(_json.dumps(trace_row) + "\n")
    except Exception as _e:
        print(f"      ⚠️  trace log write failed: {_e}")

    print("\n[4/8] AI Ranking...")
    analytics = AnalyticsEngine().compute()
    hist_wr   = analytics["win_rate"]
    conf_eng  = ConfidenceEngine()

    ranked = AISignalRanker().rank(candidates)
    ranked = ranked[:CONFIG["max_signals_per_run"]]
    print(f"      ✅ {len(ranked)} signal(s) to fire")

    print(f"\n[5/8] Sending {len(ranked)} alert(s)...")

    for sig in ranked:

        try:
            fresh_price = float(exchange.fetch_ticker(sig["symbol"])["last"])
            drift_pct = abs(fresh_price - sig["entry"]) / sig["entry"] * 100
            max_drift = CONFIG.get("max_entry_drift_pct", 0.6)
            if drift_pct > max_drift:
                print(f"  ⏭️  {sig['symbol']} {sig['direction']} skipped — "
                      f"price drifted {drift_pct:.2f}% since detection "
                      f"(entry {sig['entry']} → now {fresh_price})")
                continue

            live_rrce_engine = (
                range_rrce_engine
                if sig.get("_rrce_engine_mode") == "range"
                else rrce_engine
            )
            live_risk = revalidate_live_entry(
                rrce_engine=live_rrce_engine,
                direction=sig["direction"],
                live_price=fresh_price,
                stage4=sig.get("_rrce_stage4"),
                max_deviation_pct=max_drift,
                min_rr=CONFIG["min_rr"],
            )
            if not live_risk.get("valid"):
                print(f"  ⏭️  {sig['symbol']} {sig['direction']} skipped — "
                      f"live RRCE revalidation failed: {live_risk.get('reason', 'unknown')}")
                continue

            # Replace the complete executable risk set before sizing, Telegram,
            # or persistence uses the signal.
            sig["entry"] = live_risk["entry"]
            sig["sl"] = live_risk["sl"]
            sig["tp1"] = live_risk["tp1"]
            sig["tp2"] = live_risk["tp2"]
            sig["tp3"] = live_risk["tp3"]
            sig["rr"] = live_risk["rr"]
        except Exception as e:
            print(f"  ⚠️  {sig['symbol']} live entry validation failed ({e}) — skipping signal")
            continue

        confidence = conf_eng.estimate(
            trend_score=sig["trend_score"],
            quality_score=sig["quality_score"],
            historical_wr=hist_wr
        )

        sizing = sizer.calculate(
            grade=sig["grade"], confidence=confidence,
            entry=sig["entry"], sl=sig["sl"],
        )

        mtf_icon = {
            "CONFIRMED_STRONG": "✅✅",
            "CONFIRMED":        "✅",
            "ALLOWED":          "🟡",
            "ALLOWED_WEAK":     "🟠",
            "SKIPPED":          "⬜"
        }.get(sig["mtf_status"], "⬜")

        btc_icon = {
            "BULL":"🟢","BEAR":"🔴","RANGE":"🟡",
            "BULL_CAUTION":"🟡","BEAR_CAUTION":"🟡",
            "EXTREME_BULL":"🔥","EXTREME_BEAR":"🧊"
        }.get(sig["btc_regime"],"⬜")
        rs_icon = {"STRONG":"💪","NEUTRAL":"➡️"}.get(sig["rs_label"],"➡️")

        key_level = ""
        if sig["direction"] == "SHORT" and sig["sr_resistance"]:
            key_level = f"\n🔒 Resistance: <code>{sig['sr_resistance']}</code>"
        elif sig["direction"] == "LONG" and sig["sr_support"]:
            key_level = f"\n🛡 Support: <code>{sig['sr_support']}</code>"

        message = format_signal(
            symbol=sig["symbol"], direction=sig["direction"],
            score=sig["composite"], entry=sig["entry"],
            sl=sig["sl"], tp1=sig["tp1"], tp2=sig["tp2"], tp3=sig["tp3"],
            rr=sig["rr"], grade=sig["grade"],
        )

        message += (
            f"{key_level}\n\n"
            f"📊 <i>ADX:{sig['adx']} | RSI:{sig['rsi']} | StochK:{sig['stoch_k']} | Vol:{sig['rel_volume']}x ({sig['spike_tier']})</i>\n"
            f"📈 <i>MACD hist:{sig['macd_hist']} | BB%B:{sig['bb_pct_b']}</i>\n"
            f"{mtf_icon} MTF: <i>{sig['mtf_4h']} 4H / {sig['mtf_15m']} 15M ({sig['mtf_status']})</i>\n"
            f"{btc_icon} BTC: <i>{sig['btc_regime']}</i>\n"
            f"{rs_icon} RS: <i>{sig['rs_label']} ({sig['rs_ratio']}x BTC)</i>\n"
            f"💸 Funding: <i>{sig['funding_pct']}%</i> | "
            f"OI: <i>{sig['oi_signal']}</i> | "
            f"Beta: <i>{sig['beta_label']}</i>\n"
            f"🤖 Confidence: <b>{confidence}%</b>\n\n"
            f"{sizer.format_recommendation(sizing)}"
        )

        send_telegram_alert(message)

        sig.pop("_rrce_stage4", None)
        sig.pop("_rrce_engine_mode", None)

        save_signal(
            symbol=sig["symbol"],        direction=sig["direction"],
            entry=sig["entry"],          sl=sig["sl"],
            tp1=sig["tp1"],              tp2=sig["tp2"],        tp3=sig["tp3"],
            score=sig["composite"],      grade=sig["grade"],    rr=sig["rr"],
            adx=sig["adx"],              rsi=sig["rsi"],
            rel_volume=sig["rel_volume"], spike_tier=sig["spike_tier"],
            mtf_status=sig["mtf_status"], btc_regime=sig["btc_regime"],
            rs_label=sig["rs_label"],
            funding_pct=sig["funding_pct"],
            oi_signal=sig["oi_signal"],
            beta_label=sig["beta_label"],
        )

        set_cooldown(sig["symbol"])

        print(
            f"  ✅ {sig['symbol']} {sig['direction']} | "
            f"Grade:{sig['grade']} Score:{sig['composite']} | "
            f"RSI:{sig['rsi']} StochK:{sig['stoch_k']} Vol:{sig['rel_volume']}x | "
            f"MTF:{sig['mtf_status']} BTC:{sig['btc_regime']}"
        )

    print("\n[6/8] Running signal tracker...")
    SignalTracker().run()

    print("\n[7/8] Analytics...")
    s = AnalyticsEngine().compute()
    print(f"      {s['total_signals']} total | {s['open']} open | WR:{s['win_rate']}% | PF:{s['profit_factor']}")

    print("\n[8/8] Done ✅")
    print("=" * 55)


if __name__ == "__main__":
    main()
