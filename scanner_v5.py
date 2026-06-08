"""
Elite Futures Scanner V5.6
============================
Fixes vs V5.5:
- WEAK volume (< 1.0x) = quality score 0 = blocked (was passing)
- SHORT coin RSI < 40 = quality score 0 = blocked (coin bounce risk)
- Composite score capped at 100.0 (was overflowing to 105)
- BTC dated futures contracts excluded (BTC-YYMMDD format)
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
from engines.position_sizer      import PositionSizer
from alerts.telegram_alerts      import send_telegram_alert, format_signal
from storage.signal_logger       import save_signal
from storage.cooldown_manager    import is_on_cooldown, set_cooldown
from tracker.signal_tracker      import SignalTracker
from reports.analytics_engine    import AnalyticsEngine
from ai.signal_ranker            import AISignalRanker
from engines.funding_engine      import FundingEngine
from engines.beta_filter         import BetaFilter
from engines.oi_engine           import OIEngine
from engines.circuit_breaker     import check as circuit_check
from ai.confidence_engine        import ConfidenceEngine
from config                      import CONFIG


def grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]: return "S"
    if score >= CONFIG["signal_score_a"]: return "A"
    if score >= CONFIG["signal_score_b"]: return "B"
    return "C"


def is_dated_futures(symbol: str) -> bool:
    """Exclude dated futures like BTC/USDT:USDT-260626 — behave differently from perps."""
    return "-" in symbol.split(":")[-1] if ":" in symbol else False


def main():

    print("=" * 55)
    print("🚀 Elite Futures Scanner V5.6")
    print("=" * 55)

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
    sizer          = PositionSizer()
    funding_engine = FundingEngine()
    beta_filter    = BetaFilter()
    oi_engine      = OIEngine()

    # ── Step 1: BTC Regime (1H + 4H) ──────────────────────────────────────
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
                btc_4h = market_loader.get_4h(CONFIG["btc_symbol"], limit=50)
                btc_4h = Indicators.apply(btc_4h)
            except Exception:
                pass

            btc_regime = btc_filter.analyze(btc_1h, btc_4h)

            print(f"      BTC: {btc_regime['regime']} | ADX:{btc_regime['adx']} | RSI:{btc_regime['rsi']}")
            print(f"      LONG:{btc_regime['allow_long']} | SHORT:{btc_regime['allow_short']}")
            print(f"      Reason: {btc_regime['reason']}")

        except Exception as e:
            print(f"      ⚠️ BTC filter failed: {e} — allowing all signals")

    # ── Step 1b: Circuit Breaker ──────────────────────────────────────────
    print("\n[1b] Circuit Breaker...")
    breaker = circuit_check()
    if breaker["is_tripped"]:
        print(f"      🔴 TRIPPED — {breaker['losses_today']} losses today. Signals paused.")
        return
    print(f"      ✅ OK — {breaker['losses_today']}/{breaker['max_losses']} losses today")

    # ── Step 2: Load Symbols ───────────────────────────────────────────────────
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
        "cooldown": 0, "dated_futures": 0, "btc": 0, "trend": 0,
        "mtf": 0, "sr_no_ceiling": 0, "weak_rs": 0,
        "quality": 0, "risk": 0, "errors": 0
    }

    for symbol in symbols:

        # Skip BTC perp itself
        if symbol == CONFIG["btc_symbol"]:
            continue

        # Skip dated futures contracts (e.g. BTC/USDT:USDT-260626)
        if is_dated_futures(symbol):
            skip["dated_futures"] += 1
            continue

        if is_on_cooldown(symbol):
            skip["cooldown"] += 1
            continue

        try:
            df_1h  = market_loader.get_1h(symbol)
            df_1h  = Indicators.apply(df_1h)
            latest = df_1h.iloc[-1]

            price      = float(latest["close"])
            ema20      = float(latest["ema_20"])
            ema50      = float(latest["ema_50"])
            atr        = float(latest["atr"])
            adx        = float(latest["adx"])
            rsi        = float(latest["rsi"])
            roc        = float(latest["roc"])
            rel_volume = float(latest["rel_volume"])

            # ── Trend ─────────────────────────────────────────────────
            trend       = trend_engine.analyze(price=price, ema20=ema20, ema50=ema50, adx=adx, roc=roc)
            direction   = trend["direction"]
            trend_score = trend["score"]

            if direction == "NONE":
                skip["trend"] += 1
                continue

            # ── BTC Regime Filter ──────────────────────────────────────
            if CONFIG["btc_filter_enabled"]:
                if direction == "LONG"  and not btc_regime["allow_long"]:
                    skip["btc"] += 1
                    continue
                if direction == "SHORT" and not btc_regime["allow_short"]:
                    skip["btc"] += 1
                    continue

            # ── Funding Rate ──────────────────────────────────────────────
            funding_result = {"long_ok": True, "short_ok": True,
                              "funding_pct": 0.0, "short_score_adj": 0}
            if CONFIG["funding_enabled"]:
                funding_rate   = funding_engine.fetch_funding(exchange, symbol)
                funding_result = funding_engine.analyze(funding_rate)
                if direction == "LONG"  and not funding_result["long_ok"]:
                    skip["funding"] = skip.get("funding", 0) + 1
                    continue
                if direction == "SHORT" and not funding_result["short_ok"]:
                    skip["funding"] = skip.get("funding", 0) + 1
                    continue

            # ── Beta Filter ────────────────────────────────────────────────
            beta_result = {"short_ok": True, "beta_label": "MEDIUM",
                           "beta": 1.0, "preferred": False}
            if CONFIG["beta_filter_enabled"] and direction == "SHORT":
                coin_closes_temp = df_1h["close"].tolist()
                beta_result = beta_filter.evaluate(
                    symbol=symbol, direction=direction,
                    coin_closes=coin_closes_temp, btc_closes=btc_closes
                )
                if not beta_result["short_ok"]:
                    skip["high_beta"] = skip.get("high_beta", 0) + 1
                    continue

            # ── S/R Levels ─────────────────────────────────────────────
            sr_levels = sr_engine.find_levels(df_1h)
            sr_bonus  = sr_engine.score_bonus(direction, sr_levels)

            if direction == "SHORT" and CONFIG["short_requires_resistance"]:
                if not sr_engine.short_has_ceiling(sr_levels, CONFIG["short_resistance_max_pct"]):
                    skip["sr_no_ceiling"] += 1
                    continue

            # ── Relative Strength ──────────────────────────────────────
            coin_closes = df_1h["close"].tolist()
            rs = rs_engine.calculate(coin_closes, btc_closes)

            if rs["rs_label"] == "WEAK":
                skip["weak_rs"] += 1
                continue

            # ── Volume Spike ───────────────────────────────────────────
            spike = spike_engine.analyze(rel_volume)

            # ── Multi-Timeframe (4H) ───────────────────────────────────
            mtf_status     = "SKIPPED"
            mtf_multiplier = 1.0
            mtf_4h_dir     = "UNKNOWN"

            if CONFIG["mtf_enabled"]:
                try:
                    df_4h      = market_loader.get_4h(symbol)
                    df_4h      = Indicators.apply(df_4h)
                    tf4        = mtf_engine.analyze_4h(df_4h)
                    mtf_4h_dir = tf4["direction"]
                    confirm    = mtf_engine.confirm(direction, mtf_4h_dir)
                    mtf_status     = confirm["status"]
                    mtf_multiplier = confirm["multiplier"]
                except Exception:
                    pass

            if CONFIG["mtf_reject_counter_trend"] and mtf_status == "REJECTED":
                skip["mtf"] += 1
                continue

            # ── Quality (WEAK vol = 0, SHORT RSI < 40 = 0) ────────────
            quality_score = quality_engine.score(
                rel_volume=rel_volume, rsi=rsi, direction=direction
            )

            # ── OI Confirmation ───────────────────────────────────────────
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

            # ── Risk ───────────────────────────────────────────────────
            risk = risk_engine.calculate(direction, price, atr)

            # ── Validate ───────────────────────────────────────────────
            if not validator.validate(direction, trend_score, quality_score, risk):
                if risk is None:
                    skip["risk"] += 1
                else:
                    skip["quality"] += 1
                continue

            # ── Composite — CAPPED at 100 ─────────────────────────────
            base      = trend_score * 0.6 + quality_score * 0.4
            oi_adj      = oi_result["score_adj"]
            fund_adj    = funding_result["short_score_adj"] if direction == "SHORT" else 0
            composite   = min(100.0, round((base + sr_bonus + oi_adj + fund_adj) * mtf_multiplier, 2))
            composite   = max(0.0, composite)
            g         = grade_score(composite)

            candidates.append({
                "symbol":        symbol,
                "direction":     direction,
                "trend_score":   trend_score,
                "quality_score": quality_score,
                "rs_score":      rs["rs_score"],
                "rs_label":      rs["rs_label"],
                "rs_ratio":      rs["rs_ratio"],
                "sr_bonus":      sr_bonus,
                "sr_support":    sr_levels["nearest_support"],
                "sr_resistance": sr_levels["nearest_resistance"],
                "composite":     composite,
                "grade":         g,
                "rr":            risk["rr"],
                "entry":         risk["entry"],
                "sl":            risk["sl"],
                "tp1":           risk["tp1"],
                "tp2":           risk["tp2"],
                "tp3":           risk["tp3"],
                "rsi":           round(rsi, 2),
                "adx":           round(adx, 2),
                "rel_volume":    round(rel_volume, 2),
                "spike_tier":    spike["tier"],
                "mtf_status":    mtf_status,
                "mtf_4h":        mtf_4h_dir,
                "btc_regime":    btc_regime["regime"],
                "funding_pct":   funding_result["funding_pct"],
                "oi_signal":     oi_result["oi_signal"],
                "beta_label":    beta_result["beta_label"],
                "beta":          beta_result.get("beta", 1.0),
            })

        except Exception as e:
            skip["errors"] += 1
            print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate(s)")
    print(
        f"      📊 cd:{skip.get('cooldown',0)} dated:{skip.get('dated_futures',0)} "
        f"btc:{skip.get('btc',0)} trend:{skip.get('trend',0)} "
        f"fund:{skip.get('funding',0)} beta:{skip.get('high_beta',0)} "
        f"mtf:{skip.get('mtf',0)} no_ceil:{skip.get('sr_no_ceiling',0)} "
        f"rs:{skip.get('weak_rs',0)} q:{skip.get('quality',0)} "
        f"risk:{skip.get('risk',0)} err:{skip.get('errors',0)}"
    )

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

        confidence = conf_eng.estimate(
            trend_score=sig["trend_score"],
            quality_score=sig["quality_score"],
            historical_wr=hist_wr
        )

        sizing = sizer.calculate(
            grade=sig["grade"], confidence=confidence,
            entry=sig["entry"], sl=sig["sl"],
        )

        mtf_icon = {"CONFIRMED": "✅", "ALLOWED": "🟡", "SKIPPED": "⬜"}.get(sig["mtf_status"], "⬜")
        btc_icon = {
            "BULL": "🟢", "BEAR": "🔴", "RANGE": "🟡",
            "BULL_CAUTION": "🟡", "BEAR_CAUTION": "🟡",
            "EXTREME_BULL": "🔥", "EXTREME_BEAR": "🧊"
        }.get(sig["btc_regime"], "⬜")
        rs_icon = {"STRONG": "💪", "NEUTRAL": "➡️"}.get(sig["rs_label"], "➡️")

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
            f"📊 <i>ADX:{sig['adx']} | RSI:{sig['rsi']} | Vol:{sig['rel_volume']}x ({sig['spike_tier']})</i>\n"
            f"{mtf_icon} 4H: <i>{sig['mtf_4h']} ({sig['mtf_status']})</i>\n"
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
            symbol=sig["symbol"],     direction=sig["direction"],
            entry=sig["entry"],       sl=sig["sl"],
            tp1=sig["tp1"],           tp2=sig["tp2"],       tp3=sig["tp3"],
            score=sig["composite"],   grade=sig["grade"],   rr=sig["rr"],
            adx=sig["adx"],           rsi=sig["rsi"],
            rel_volume=sig["rel_volume"], spike_tier=sig["spike_tier"],
            mtf_status=sig["mtf_status"], btc_regime=sig["btc_regime"],
            rs_label=sig["rs_label"],
        )
        set_cooldown(sig["symbol"])

        print(
            f"  ✅ {sig['symbol']} {sig['direction']} | "
            f"Grade:{sig['grade']} Score:{sig['composite']} | "
            f"Vol:{sig['rel_volume']}x RSI:{sig['rsi']} | "
            f"4H:{sig['mtf_4h']} BTC:{sig['btc_regime']}"
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
