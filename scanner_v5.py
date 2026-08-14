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
from engines.risk_engine         import RiskEngine
from engines.validator           import SignalValidator
from engines.btc_filter          import BTCFilter
from engines.multiframe_engine   import MultiFrameEngine
from engines.volume_spike        import VolumeSpikeEngine
from engines.relative_strength   import RelativeStrengthEngine
from engines.support_resistance  import SupportResistanceEngine
from engines.volume_profile      import VolumeProfileEngine
from engines.rrce_engine         import RRCEEngine
from engines.position_sizer      import PositionSizer
from engines.funding_engine      import FundingEngine
from engines.beta_filter         import BetaFilter
from engines.oi_engine           import OIEngine
from engines.circuit_breaker     import check as circuit_check
from alerts.telegram_alerts      import send_telegram_alert, format_signal
from storage.signal_logger       import save_signal
from storage.cooldown_manager    import is_on_cooldown, set_cooldown
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
    risk_engine    = RiskEngine()
    validator      = SignalValidator()
    btc_filter     = BTCFilter()
    mtf_engine     = MultiFrameEngine()
    spike_engine   = VolumeSpikeEngine()
    rs_engine      = RelativeStrengthEngine()
    sr_engine      = SupportResistanceEngine()
    vp_engine      = VolumeProfileEngine()
    rrce_engine    = RRCEEngine()
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
    skip = {
        "cooldown": 0, "dated": 0, "btc": 0, "trend": 0,
        "funding": 0, "high_beta": 0, "sr_no_ceil": 0,
        "weak_rs": 0, "mtf": 0, "quality": 0, "risk": 0,
        "d_grade": 0, "overextended": 0, "rrce_invalid": 0, "time_budget_stop": 0, "errors": 0
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
            continue
        if is_stock_token(symbol):
            skip["dated"] += 1
            continue
        if is_on_cooldown(symbol):
            skip["cooldown"] += 1
            continue

        try:
            # ── 1H data ───────────────────────────────────────────────
            df_1h  = market_loader.get_1h(symbol)
            df_1h  = Indicators.apply(df_1h)

            if len(df_1h) < 2:
                skip["errors"] += 1
                continue

            # V6.1.2 fix: scanner runs every 5min but timeframe is 1H, so
            # df.iloc[-1] is a STILL-FORMING candle — its indicators
            # (RSI/MACD/EMA/ADX/Stoch/BB/ATR) repaint until candle close.
            # Use the last CLOSED candle (iloc[-2]) for all indicators,
            # and the live candle (iloc[-1]) only for current price/entry.
            live = df_1h.iloc[-1]    # forming candle — price/entry only
            prev = df_1h.iloc[-2]    # last closed candle — all indicators

            # NaN guard — now includes new indicators
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

            # ── Trend (V6 — with MACD + Stoch + BB) ───────────────────
            trend = trend_engine.analyze(
                price=price, ema20=ema20, ema50=ema50,
                adx=adx, roc=roc,
                macd=macd, macd_sig=macd_sig, macd_hist=macd_hist,
                stoch_k=stoch_k, stoch_d=stoch_d,
                bb_pct_b=bb_pct_b,
            )
            trend_score = trend["score"]

            # V6.9.4: trend gate can now be bypassed so RRCE (structure-
            # based) can act as the sole hard gate instead of stacking
            # with the indicator-based trend_engine (ADX/EMA/MACD/Stoch/
            # BB), which was rejecting 80-90%+ of symbols on its own.
            if CONFIG.get("require_trend_gate", True):
                if trend["direction"] == "NONE":
                    skip["trend"] += 1
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

                # V6.9.4: when the trend gate is bypassed and the
                # indicator engine found NONE (trend_score=0), that 0
                # would otherwise auto-fail the validator's min_score
                # check regardless of RRCE — silently re-imposing the
                # same gate we just turned off. Substitute a neutral
                # baseline so RRCE (already a hard gate above) is what
                # actually decides, not indicator trend strength.
                if not CONFIG.get("require_trend_gate", True) and trend["direction"] == "NONE":
                    effective_trend_score = CONFIG["min_score"]
                else:
                    effective_trend_score = trend_score

                # ── BTC Regime Filter ──────────────────────────────────────
                if CONFIG["btc_filter_enabled"]:
                    if direction == "LONG"  and not btc_regime["allow_long"]:
                        skip["btc"] += 1
                        continue
                    if direction == "SHORT" and not btc_regime["allow_short"]:
                        skip["btc"] += 1
                        continue

                # V6.5: Data-driven hard blocks from 88-trade closed-signal
                # review — BEAR/BEAR_CAUTION regime produced ~0-12% WR (1/18)
                # vs 32% in BULL. SHORT direction produced 5.6% WR (1/18)
                # vs 30% for LONG. Gaps are large relative to sample size,
                # so block outright rather than just downweight, pending
                # more data.
                if CONFIG.get("block_bear_regime", True) and btc_regime["regime"] in ("BEAR", "BEAR_CAUTION"):
                    skip["btc"] += 1
                    continue
                if CONFIG.get("pause_shorts", True) and direction == "SHORT":
                    skip["btc"] += 1
                    continue

                if btc_regime["regime"] == "RANGE":
                    if effective_trend_score < CONFIG.get("range_regime_min_score", 85):
                        skip["btc"] += 1
                        continue

                # ── Funding Rate ───────────────────────────────────────────
                funding_result = {"funding_pct": 0.0, "funding_pct_raw": 0.0, "short_score_adj": 0}
                if CONFIG["funding_enabled"]:
                    fr = funding_engine.fetch_funding(exchange, symbol)
                    funding_result = funding_engine.analyze(fr)
                    funding_result["funding_pct_raw"] = fr
                    if direction == "LONG"  and not funding_result["long_ok"]:
                        skip["funding"] += 1
                        continue
                    if direction == "SHORT" and not funding_result["short_ok"]:
                        skip["funding"] += 1
                        continue

                # ── Beta Filter (SHORT only) ───────────────────────────────
                beta_result = {"beta_label": "N/A", "beta": 1.0}
                if CONFIG["beta_filter_enabled"] and direction == "SHORT":
                    coin_closes_beta = df_1h["close"].tolist()
                    beta_result = beta_filter.evaluate(
                        symbol=symbol, direction=direction,
                        coin_closes=coin_closes_beta, btc_closes=btc_closes
                    )
                    if not beta_result["short_ok"]:
                        skip["high_beta"] += 1
                        continue

                # ── S/R Levels ─────────────────────────────────────────────
                sr_levels = sr_engine.find_levels(df_1h)
                sr_bonus  = sr_engine.score_bonus(direction, sr_levels)

                # ── Pre-breakout bonus (leading, not confirming) ────────────
                # Squeeze: bb_width near its own 20-bar low = volatility
                # coiled, move likely hasn't happened yet.
                bb_width_pctile = float(df_1h["bb_width_pctile"].iloc[-2]) \
                    if "bb_width_pctile" in df_1h.columns else 1.0
                squeeze_bonus = 8 if bb_width_pctile <= 0.2 else 0

                # ── Volume Profile Zone bonus ────────────────────────────────
                # High Volume Nodes (HVN) = historical price zones with the
                # most traded volume — tend to act as stronger reaction
                # zones than plain swing S/R. Concept observed from external
                # chart review (volume-box annotations), reimplemented here
                # as a proper volume profile (POC/HVN/LVN), not copied.
                vp_profile = vp_engine.build_profile(df_1h)
                vp_bonus   = vp_engine.score_bonus(direction, price, vp_profile)

                # ── RRCE (full multi-timeframe validator) ────────────────────
                # V6.9.2 timeframe lock (per explicit instruction):
                #   Setup / Sweep (Range + Retail Liquidity)  -> 15m
                #   CHOCH / Confirmation / Entry (Confirm+Exec) -> 5m
                # Strict sequential gate — every stage must pass, in order.
                rrce_bonus = 0.0
                rrce_result = None
                try:
                    _df_rrce_15m_raw = market_loader.get_15m(symbol)
                    _df_rrce_15m = Indicators.apply(_df_rrce_15m_raw)
                    _df_rrce_5m_raw = market_loader.get_5m(symbol)
                    _df_rrce_5m = Indicators.apply(_df_rrce_5m_raw)

                    if len(_df_rrce_15m) >= 20 and len(_df_rrce_5m) >= 20:
                        rrce_result = rrce_engine.evaluate(
                            df_htf=_df_rrce_15m, df_mtf=_df_rrce_15m,
                            df_ltf_confirm=_df_rrce_5m, df_ltf_exec=_df_rrce_5m,
                            direction=direction, price=price,
                        )
                        rrce_bonus = rrce_result["bonus"]
                except Exception as _rrce_e:
                    print(f"      ⚠️  {symbol} RRCE multi-TF fetch/eval failed: {_rrce_e}")

                # V6.9.1: RRCE is now a HARD REQUIREMENT, not just a bonus.
                # A candidate must pass all 4 stages (Range -> Retail
                # Liquidity -> Confirmation -> Execution) or it is rejected
                # outright — no exceptions, regardless of how good the rest
                # of the score looks.
                if not rrce_result or not rrce_result.get("valid"):
                    skip["rrce_invalid"] = skip.get("rrce_invalid", 0) + 1
                    continue

                if direction == "SHORT" and CONFIG["short_requires_resistance"]:
                    if not sr_engine.short_has_ceiling(sr_levels, CONFIG["short_resistance_max_pct"]):
                        skip["sr_no_ceil"] += 1
                        continue

                # ── Relative Strength ──────────────────────────────────────
                coin_closes = df_1h["close"].tolist()
                if len(btc_closes) >= 21:
                    rs = rs_engine.calculate(coin_closes, btc_closes)
                else:
                    rs = {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}

                if rs["rs_label"] == "WEAK":
                    skip["weak_rs"] += 1
                    continue

                rs_max = CONFIG.get("rs_max_ratio", 10.0)
                if rs.get("rs_ratio", 1.0) > rs_max:
                    skip["weak_rs"] += 1
                    continue

                # ── Volume hard cap (config: vol_max_ratio) ────────────────
                # Vol > 2.0x = coin already moved, chasing = bad outcome
                # BA/USDT at 3.06x (Grade S!) hit SL — confirmed by live data
                vol_max = CONFIG.get("vol_max_ratio", 2.0)
                if rel_volume > vol_max:
                    skip["quality"] += 1
                    continue

                # ── Volume Spike ───────────────────────────────────────────
                spike = spike_engine.analyze(rel_volume)

                # ── Multi-Timeframe: 4H + 15M ──────────────────────────────
                mtf_status     = "SKIPPED"
                mtf_multiplier = 1.0
                mtf_4h_dir     = "UNKNOWN"
                mtf_15m_dir    = "UNKNOWN"

                if CONFIG["mtf_enabled"]:
                    trend_15m = None

                    # Try 15M first (entry precision)
                    try:
                        _df_15m_raw = market_loader.get_15m(symbol) if hasattr(market_loader, "get_15m") else None
                        if _df_15m_raw is not None:
                            df_15m = Indicators.apply(_df_15m_raw)
                            if len(df_15m) >= 2 and not df_15m.iloc[-2][["ema_20","ema_50","adx"]].isnull().any():
                                trend_15m   = mtf_engine.analyze_15m(df_15m)
                                mtf_15m_dir = trend_15m["direction"]
                    except Exception:
                        trend_15m = None

                    # 4H confirmation
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
                    continue

                # ── Quality Engine (V6 — with Stoch + BB + MACD) ──────────
                quality_score = quality_engine.score(
                    rel_volume=rel_volume, rsi=rsi, direction=direction,
                    stoch_k=stoch_k, bb_pct_b=bb_pct_b, macd_hist=macd_hist,
                )

                # ── OI Engine ──────────────────────────────────────────────
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

                # ── Risk Engine ────────────────────────────────────────────
                risk = risk_engine.calculate(direction, price, atr)

                # ── Validator ──────────────────────────────────────────────
                if not validator.validate(direction, effective_trend_score, quality_score, risk):
                    if risk is None:
                        skip["risk"] += 1
                    else:
                        skip["quality"] += 1
                    continue

                # ── Composite Score ────────────────────────────────────────
                oi_adj    = oi_result["score_adj"]
                fund_adj  = funding_result.get("short_score_adj", 0) if direction == "SHORT" else 0
                base      = effective_trend_score * 0.6 + quality_score * 0.4
                composite = min(100.0, max(0.0, round(
                    (base + sr_bonus + oi_adj + fund_adj + squeeze_bonus + vp_bonus + rrce_bonus) * mtf_multiplier, 2
                )))
                g = grade_score(composite)

                # V6.1.2: D-grade gate. Validator already requires
                # trend_score >= min_score AND quality_score >= min_score
                # individually, but the MTF multiplier (e.g. ALLOWED_WEAK
                # = 0.92x) can drag the composite below signal_score_c —
                # landing it in "D". Config intent treats D as effectively
                # blocked ("below min_score"), so don't fire these.
                if g == "D":
                    skip["d_grade"] += 1
                    continue

                # V6.3: Hard ceiling — composite >= 84 means the move likely
                # already confirmed (score paradox: B (70-82) historically
                # outperformed A/S). Block outright, don't just deprioritize,
                # so these never fire even if no B-grade candidate exists
                # that run.
                if composite >= CONFIG.get("signal_score_ceiling", 84):
                    skip["overextended"] = skip.get("overextended", 0) + 1
                    continue

                candidates.append({
                    "symbol":          symbol,
                    "direction":       direction,
                    "trend_score":     effective_trend_score,
                    "quality_score":   quality_score,
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
                    "oi_signal":       oi_result["oi_signal"],
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
        f"budget_stop:{skip['time_budget_stop']} err:{skip['errors']}"
    )

    # V6.7.3: persist skip counters every run (even with 0 candidates)
    # so signal droughts can be diagnosed after the fact — GH Actions
    # log storage isn't reliably reachable from outside, so this needs
    # to live in the repo itself.
    try:
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        debug_row = {
            "ts": _dt.now(_tz.utc).isoformat(),
            "symbols_scanned": len(symbols),
            "candidates": len(candidates),
            **skip,
        }
        debug_path = "storage/scan_debug_log.jsonl"
        with open(debug_path, "a") as f:
            f.write(_json.dumps(debug_row) + "\n")
    except Exception as _e:
        print(f"      ⚠️  debug log write failed: {_e}")

    # ── Step 4: AI Ranking ─────────────────────────────────────────────────
    print("\n[4/8] AI Ranking...")
    analytics = AnalyticsEngine().compute()
    hist_wr   = analytics["win_rate"]
    conf_eng  = ConfidenceEngine()

    ranked = AISignalRanker().rank(candidates)
    ranked = ranked[:CONFIG["max_signals_per_run"]]
    print(f"      ✅ {len(ranked)} signal(s) to fire")

    # ── Step 5: Alert + Log ────────────────────────────────────────────────
    print(f"\n[5/8] Sending {len(ranked)} alert(s)...")

    for sig in ranked:

        # ── Price Staleness Guard ────────────────────────────────────────
        # Between candidate detection and alert send, real time has passed
        # (scan of up to top_coins_limit symbols, MTF calls, AI ranking).
        # Re-check live price right before firing — if it already ran too
        # far from the computed entry, the signal is stale (we'd be
        # chasing, not catching early). Skip rather than send a late entry.
        try:
            fresh_price = float(exchange.fetch_ticker(sig["symbol"])["last"])
            drift_pct = abs(fresh_price - sig["entry"]) / sig["entry"] * 100
            max_drift = CONFIG.get("max_entry_drift_pct", 0.6)
            if drift_pct > max_drift:
                print(f"  ⏭️  {sig['symbol']} {sig['direction']} skipped — "
                      f"price drifted {drift_pct:.2f}% since detection "
                      f"(entry {sig['entry']} → now {fresh_price})")
                continue
            # Use the freshest price as the actual entry reference
            sig["entry"] = fresh_price
        except Exception as e:
            print(f"  ⚠️  {sig['symbol']} staleness check failed ({e}) — sending with original entry")

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

    # ── Steps 6-8 ──────────────────────────────────────────────────────────
    print("\n[6/8] Running signal tracker...")
    SignalTracker().run()

    print("\n[7/8] Analytics...")
    s = AnalyticsEngine().compute()
    print(f"      {s['total_signals']} total | {s['open']} open | WR:{s['win_rate']}% | PF:{s['profit_factor']}")

    print("\n[8/8] Done ✅")
    print("=" * 55)


if __name__ == "__main__":
    main()
