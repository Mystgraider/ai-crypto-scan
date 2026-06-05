"""
Elite Futures Scanner V5.3 — Phase 5
======================================
Full pipeline:

  GitHub Actions (every 5min)
  -> BTC Market Filter (regime gate)
  -> Load Top 300 Symbols (by volume)
  -> Per symbol:
       1H OHLCV + Indicators
       Trend Engine (ADX >= 20 gate)
       BTC Regime Filter
       Relative Strength vs BTC
       Support/Resistance levels
       Volume Spike classification
       4H MTF confirmation
       Quality Engine
       Risk Engine (Entry/SL/TP/RR)
       Signal Validator
  -> AI Ranker (trend + quality + RS + SR + RR)
  -> Dynamic Position Sizing
  -> Telegram Alert (all data + position recommendation)
  -> Signal Logger
  -> Signal Tracker (TP/SL hit + trailing stop)
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
from engines.relative_strength   import RelativeStrengthEngine
from engines.support_resistance  import SupportResistanceEngine
from engines.position_sizer      import PositionSizer
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
    print("🚀 Elite Futures Scanner V5.3 — Phase 5")
    print("=" * 55)

    market_loader  = MarketDataLoader()
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

    # ── Step 1: BTC Market Regime ──────────────────────────────────────────
    print("\n[1/8] BTC Market Filter...")

    btc_regime   = {"regime": "UNKNOWN", "allow_long": True, "allow_short": True, "adx": 0, "rsi": 50}
    btc_closes   = []

    if CONFIG["btc_filter_enabled"]:
        try:
            btc_df     = market_loader.get_1h(CONFIG["btc_symbol"], limit=100)
            btc_df     = Indicators.apply(btc_df)
            btc_closes = btc_df["close"].tolist()
            btc_regime = btc_filter.analyze(btc_df)
            print(f"      BTC: {btc_regime['regime']} | ADX: {btc_regime['adx']} | RSI: {btc_regime['rsi']}")
            print(f"      LONG allowed: {btc_regime['allow_long']} | SHORT allowed: {btc_regime['allow_short']}")
        except Exception as e:
            print(f"      ⚠️ BTC filter failed: {e} — allowing all signals")

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
    skip = {"cooldown": 0, "btc": 0, "trend": 0, "mtf": 0, "quality": 0, "risk": 0, "errors": 0}

    for symbol in symbols:

        if symbol == CONFIG["btc_symbol"]:
            continue

        if is_on_cooldown(symbol):
            skip["cooldown"] += 1
            continue

        try:
            # ── 1H ────────────────────────────────────────────────────
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

            # ── Relative Strength ──────────────────────────────────────
            coin_closes = df_1h["close"].tolist()
            rs = rs_engine.calculate(coin_closes, btc_closes)

            # Skip WEAK relative strength coins entirely
            if rs["rs_label"] == "WEAK":
                skip["quality"] += 1
                continue

            # ── Support / Resistance ───────────────────────────────────
            sr_levels = sr_engine.find_levels(df_1h)
            sr_bonus  = sr_engine.score_bonus(direction, sr_levels)

            # ── Volume Spike ───────────────────────────────────────────
            spike = spike_engine.analyze(rel_volume)

            # ── Multi-Timeframe ────────────────────────────────────────
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

            # ── Quality ────────────────────────────────────────────────
            quality_score = quality_engine.score(rel_volume=rel_volume, rsi=rsi, direction=direction)

            # ── Risk ───────────────────────────────────────────────────
            risk = risk_engine.calculate(direction, price, atr)

            # ── Validate ───────────────────────────────────────────────
            if not validator.validate(direction, trend_score, quality_score, risk):
                if risk is None:
                    skip["risk"] += 1
                else:
                    skip["quality"] += 1
                continue

            # ── Composite ─────────────────────────────────────────────
            base      = trend_score * 0.6 + quality_score * 0.4
            composite = round((base + sr_bonus) * mtf_multiplier, 2)
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
            })

        except Exception as e:
            skip["errors"] += 1
            print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate(s)")
    print(f"      📊 skip — cd:{skip['cooldown']} btc:{skip['btc']} "
          f"trend:{skip['trend']} mtf:{skip['mtf']} "
          f"q:{skip['quality']} risk:{skip['risk']} err:{skip['errors']}")

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
            grade=sig["grade"],
            confidence=confidence,
            entry=sig["entry"],
            sl=sig["sl"],
        )

        mtf_icon = {"CONFIRMED": "✅", "ALLOWED": "🟡", "SKIPPED": "⬜"}.get(sig["mtf_status"], "⬜")
        btc_icon = {"BULL": "🟢", "BEAR": "🔴", "RANGE": "🟡",
                    "EXTREME_BULL": "🔥", "EXTREME_BEAR": "🧊"}.get(sig["btc_regime"], "⬜")
        rs_icon  = {"STRONG": "💪", "NEUTRAL": "➡️", "WEAK": "👎"}.get(sig["rs_label"], "➡️")

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
            f"📊 <i>ADX:{sig['adx']} | RSI:{sig['rsi']} | Vol:{sig['rel_volume']}x ({sig['spike_tier']})</i>\n"
            f"{mtf_icon} 4H: <i>{sig['mtf_4h']} ({sig['mtf_status']})</i>\n"
            f"{btc_icon} BTC: <i>{sig['btc_regime']}</i>\n"
            f"{rs_icon} RS: <i>{sig['rs_label']} ({sig['rs_ratio']}x BTC)</i>\n"
            f"🤖 Confidence: <b>{confidence}%</b>\n\n"
            f"{sizer.format_recommendation(sizing)}"
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
            f"Grade:{sig['grade']} Score:{sig['composite']} | "
            f"RS:{sig['rs_label']} 4H:{sig['mtf_4h']} BTC:{sig['btc_regime']}"
        )

    # ── Step 6: Track signals ──────────────────────────────────────────────
    print("\n[6/8] Running signal tracker...")
    SignalTracker().run()

    # ── Step 7: Analytics ──────────────────────────────────────────────────
    print("\n[7/8] Analytics...")
    s = AnalyticsEngine().compute()
    print(f"      {s['total_signals']} total | {s['open']} open | WR:{s['win_rate']}% | PF:{s['profit_factor']}")

    print("\n[8/8] Done ✅")
    print("=" * 55)


if __name__ == "__main__":
    main()
