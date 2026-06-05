"""
Elite Futures Scanner V5.2 — Phase 4
======================================
Full pipeline:

  GitHub Actions (every 5min)
  -> Load Top 300 Symbols (by volume)
  -> BTC Market Filter (regime gate)
  -> Load OHLCV 1H + 4H per symbol
  -> Apply Indicators (EMA20/50, RSI, ATR, ADX, ROC, RelVol)
  -> Trend Engine (direction + score, ADX >= 20 gate)
  -> Volume Spike Detection
  -> Multi-Timeframe Confirmation (4H alignment)
  -> Quality Engine (volume + RSI score)
  -> Risk Engine (Entry, SL, TP1/2/3, RR)
  -> Signal Validator (all gates)
  -> AI Ranker (composite score sort)
  -> Telegram Alert (HTML, shows all filter values)
  -> Signal Logger (CSV)
  -> Signal Tracker (update open signals TP/SL hits)
  -> Analytics summary
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
from alerts.telegram_alerts      import send_telegram_alert, format_signal
from storage.signal_logger       import save_signal
from storage.cooldown_manager    import is_on_cooldown, set_cooldown
from tracker.signal_tracker      import SignalTracker
from reports.analytics_engine    import AnalyticsEngine
from ai.signal_ranker            import AISignalRanker
from ai.confidence_engine        import ConfidenceEngine
from config                      import CONFIG


# ── helpers ───────────────────────────────────────────────────────────────────

def grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]: return "S"
    if score >= CONFIG["signal_score_a"]: return "A"
    if score >= CONFIG["signal_score_b"]: return "B"
    return "C"


# ── main ──────────────────────────────────────────────────────────────────────

def main():

    print("=" * 55)
    print("🚀 Elite Futures Scanner V5.2 — Phase 4")
    print("=" * 55)

    market_loader   = MarketDataLoader()
    trend_engine    = TrendEngine()
    quality_engine  = QualityEngine()
    risk_engine     = RiskEngine()
    validator       = SignalValidator()
    btc_filter      = BTCFilter()
    mtf_engine      = MultiFrameEngine()
    spike_engine    = VolumeSpikeEngine()

    # ── Step 1: BTC Market Regime ──────────────────────────────────────────
    print("\n[1/8] BTC Market Filter...")

    btc_regime = {"regime": "UNKNOWN", "allow_long": True, "allow_short": True}

    if CONFIG["btc_filter_enabled"]:
        try:
            btc_df     = market_loader.get_1h(CONFIG["btc_symbol"], limit=100)
            btc_df     = Indicators.apply(btc_df)
            btc_regime = btc_filter.analyze(btc_df)
            print(
                f"      BTC Regime: {btc_regime['regime']} | "
                f"ADX: {btc_regime['adx']} | RSI: {btc_regime['rsi']}"
            )
            print(
                f"      Allow LONG: {btc_regime['allow_long']} | "
                f"Allow SHORT: {btc_regime['allow_short']}"
            )
        except Exception as e:
            print(f"      ⚠️ BTC filter failed: {e} — allowing all signals")

    # ── Step 2: Load Symbols ───────────────────────────────────────────────
    print("\n[2/8] Loading top symbols...")
    symbols = TopSymbolsLoader().get_top_symbols()
    print(f"      ✅ {len(symbols)} symbols loaded")

    if not symbols:
        print("      ❌ No symbols loaded — check exchange config")
        return

    # ── Step 3: Scan ───────────────────────────────────────────────────────
    print(f"\n[3/8] Scanning {len(symbols)} symbols...")

    candidates = []
    stats = {
        "cooldown": 0, "btc_filtered": 0, "no_trend": 0,
        "mtf_rejected": 0, "low_quality": 0, "bad_risk": 0, "errors": 0
    }

    for symbol in symbols:

        # Skip BTC itself from coin scanning
        if symbol == CONFIG["btc_symbol"]:
            continue

        # Cooldown
        if is_on_cooldown(symbol):
            stats["cooldown"] += 1
            continue

        try:
            # ── 1H data ───────────────────────────────────────────────
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

            # ── Trend (ADX gate inside) ────────────────────────────────
            trend       = trend_engine.analyze(price=price, ema20=ema20, ema50=ema50, adx=adx, roc=roc)
            direction   = trend["direction"]
            trend_score = trend["score"]

            if direction == "NONE":
                stats["no_trend"] += 1
                continue

            # ── BTC Regime Filter ──────────────────────────────────────
            if CONFIG["btc_filter_enabled"]:
                if direction == "LONG"  and not btc_regime["allow_long"]:
                    stats["btc_filtered"] += 1
                    continue
                if direction == "SHORT" and not btc_regime["allow_short"]:
                    stats["btc_filtered"] += 1
                    continue

            # ── Volume Spike ───────────────────────────────────────────
            spike = spike_engine.analyze(rel_volume)

            # ── Multi-Timeframe (4H) ───────────────────────────────────
            mtf_status = "SKIPPED"
            mtf_multiplier = 1.0
            mtf_4h_dir = "UNKNOWN"

            if CONFIG["mtf_enabled"]:
                try:
                    df_4h   = market_loader.get_4h(symbol)
                    df_4h   = Indicators.apply(df_4h)
                    tf4     = mtf_engine.analyze_4h(df_4h)
                    mtf_4h_dir = tf4["direction"]
                    confirm = mtf_engine.confirm(direction, mtf_4h_dir)
                    mtf_status     = confirm["status"]
                    mtf_multiplier = confirm["multiplier"]
                except Exception:
                    pass  # MTF fail = allow signal but no bonus

            # Reject counter-trend signals
            if CONFIG["mtf_reject_counter_trend"] and mtf_status == "REJECTED":
                stats["mtf_rejected"] += 1
                continue

            # ── Quality ────────────────────────────────────────────────
            quality_score = quality_engine.score(
                rel_volume=rel_volume,
                rsi=rsi,
                direction=direction
            )

            # ── Risk ───────────────────────────────────────────────────
            risk = risk_engine.calculate(direction, price, atr)

            # ── Validate ───────────────────────────────────────────────
            if not validator.validate(direction, trend_score, quality_score, risk):
                if risk is None:
                    stats["bad_risk"] += 1
                else:
                    stats["low_quality"] += 1
                continue

            # ── Composite score (with MTF multiplier) ──────────────────
            base_composite  = trend_score * 0.6 + quality_score * 0.4
            final_composite = round(base_composite * mtf_multiplier, 2)
            g               = grade_score(final_composite)

            candidates.append({
                "symbol":        symbol,
                "direction":     direction,
                "trend_score":   trend_score,
                "quality_score": quality_score,
                "composite":     final_composite,
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
            })

        except Exception as e:
            stats["errors"] += 1
            print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate(s)")
    print(
        f"      📊 cooldown:{stats['cooldown']} | "
        f"btc_filter:{stats['btc_filtered']} | "
        f"no_trend:{stats['no_trend']} | "
        f"mtf_reject:{stats['mtf_rejected']} | "
        f"low_quality:{stats['low_quality']} | "
        f"bad_risk:{stats['bad_risk']} | "
        f"errors:{stats['errors']}"
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

        mtf_icon = {"CONFIRMED": "✅", "ALLOWED": "🟡", "SKIPPED": "⬜"}.get(sig["mtf_status"], "⬜")
        btc_icon = {"BULL": "🟢", "BEAR": "🔴", "RANGE": "🟡", "EXTREME_BULL": "🔥", "EXTREME_BEAR": "🧊"}.get(sig["btc_regime"], "⬜")

        message = format_signal(
            symbol=sig["symbol"],
            direction=sig["direction"],
            score=sig["composite"],
            entry=sig["entry"],
            sl=sig["sl"],
            tp1=sig["tp1"],
            tp2=sig["tp2"],
            tp3=sig["tp3"],
            rr=sig["rr"],
            grade=sig["grade"],
        )

        message += (
            f"\n\n"
            f"📊 <i>ADX: {sig['adx']} | RSI: {sig['rsi']} | Vol: {sig['rel_volume']}x ({sig['spike_tier']})</i>\n"
            f"{mtf_icon} 4H: <i>{sig['mtf_4h']} ({sig['mtf_status']})</i>\n"
            f"{btc_icon} BTC: <i>{sig['btc_regime']}</i>\n"
            f"🤖 Confidence: <b>{confidence}%</b>"
        )

        send_telegram_alert(message)

        save_signal(
            symbol=sig["symbol"],
            direction=sig["direction"],
            entry=sig["entry"],
            sl=sig["sl"],
            tp1=sig["tp1"],
            tp2=sig["tp2"],
            tp3=sig["tp3"],
            score=sig["composite"],
            grade=sig["grade"],
            rr=sig["rr"],
        )

        set_cooldown(sig["symbol"])

        print(
            f"  ✅ {sig['symbol']} {sig['direction']} | "
            f"Grade {sig['grade']} | Score {sig['composite']} | "
            f"4H:{sig['mtf_4h']} | BTC:{sig['btc_regime']}"
        )

    # ── Step 6: Track open signals ─────────────────────────────────────────
    print("\n[6/8] Running signal tracker...")
    SignalTracker().run()

    # ── Step 7: Analytics ──────────────────────────────────────────────────
    print("\n[7/8] Analytics...")
    stats_out = AnalyticsEngine().compute()
    print(
        f"      Signals: {stats_out['total_signals']} total | "
        f"{stats_out['open']} open | "
        f"WR: {stats_out['win_rate']}% | "
        f"PF: {stats_out['profit_factor']}"
    )

    print("\n[8/8] Done ✅")
    print("=" * 55)


if __name__ == "__main__":
    main()
