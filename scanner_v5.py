"""
Elite Futures Scanner V5
========================
Orchestrator — follows the blueprint workflow:

  GitHub Actions
  -> Load Symbols
  -> Load Market Data
  -> Indicators
  -> Trend Engine
  -> Quality Engine
  -> Risk Engine
  -> Signal Validator
  -> AI Ranker
  -> Telegram Alert
  -> Signal Logger
  -> Tracker
  -> Analytics
"""

from loaders.top_symbols_loader  import TopSymbolsLoader
from loaders.market_data_loader  import MarketDataLoader
from indicators.indicators       import Indicators
from engines.trend_engine        import TrendEngine
from engines.quality_engine      import QualityEngine
from engines.risk_engine         import RiskEngine
from engines.validator           import SignalValidator
from alerts.telegram_alerts      import send_telegram_alert, format_signal
from storage.signal_logger       import save_signal
from storage.cooldown_manager    import is_on_cooldown, set_cooldown
from tracker.signal_tracker      import SignalTracker
from reports.analytics_engine    import AnalyticsEngine
from ai.signal_ranker            import AISignalRanker
from ai.confidence_engine        import ConfidenceEngine
from config                      import CONFIG


# ── grade helper ──────────────────────────────────────────────────────────────

def grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]:
        return "S"
    if score >= CONFIG["signal_score_a"]:
        return "A"
    if score >= CONFIG["signal_score_b"]:
        return "B"
    return "C"


# ── main ──────────────────────────────────────────────────────────────────────

def main():

    print("=" * 50)
    print("🚀 Elite Futures Scanner V5 — Starting")
    print("=" * 50)

    # ── Phase 1: Load Symbols ──────────────────────────────────────────────

    print("\n[1/7] Loading top symbols...")
    symbols = TopSymbolsLoader().get_top_symbols()
    print(f"      ✅ {len(symbols)} symbols loaded")

    # ── Phase 2: Scan each symbol ─────────────────────────────────────────

    market_loader   = MarketDataLoader()
    trend_engine    = TrendEngine()
    quality_engine  = QualityEngine()
    risk_engine     = RiskEngine()
    validator       = SignalValidator()

    print(f"\n[2/7] Scanning {len(symbols)} symbols...")

    candidates = []

    for symbol in symbols:

        if is_on_cooldown(symbol):
            continue

        try:
            df     = market_loader.get_ohlcv(symbol)
            df     = Indicators.apply(df)
            latest = df.iloc[-1]

            price      = float(latest["close"])
            ema20      = float(latest["ema_20"])
            ema50      = float(latest["ema_50"])
            atr        = float(latest["atr"])
            adx        = float(latest["adx"])
            rsi        = float(latest["rsi"])
            roc        = float(latest["roc"])
            rel_volume = float(latest["rel_volume"])

            # Trend
            trend = trend_engine.analyze(
                price=price, ema20=ema20, ema50=ema50,
                adx=adx, roc=roc
            )

            direction   = trend["direction"]
            trend_score = trend["score"]

            if direction == "NONE":
                continue

            # Quality
            quality_score = quality_engine.score(
                rel_volume=rel_volume,
                rsi=rsi,
                direction=direction
            )

            # Risk
            risk = risk_engine.calculate(direction, price, atr)

            # Validate
            if not validator.validate(direction, trend_score, quality_score, risk):
                continue

            # Composite score for grading
            composite = trend_score * 0.6 + quality_score * 0.4
            g         = grade_score(composite)

            candidates.append({
                "symbol":        symbol,
                "direction":     direction,
                "trend_score":   trend_score,
                "quality_score": quality_score,
                "composite":     composite,
                "grade":         g,
                "rr":            risk["rr"],
                "entry":         risk["entry"],
                "sl":            risk["sl"],
                "tp1":           risk["tp1"],
                "tp2":           risk["tp2"],
                "tp3":           risk["tp3"],
                "rsi":           rsi,
            })

        except Exception as e:
            print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate signal(s) found")

    # ── Phase 3: AI Ranking ────────────────────────────────────────────────

    print("\n[3/7] AI Ranking...")

    ranker    = AISignalRanker()
    conf_eng  = ConfidenceEngine()
    analytics = AnalyticsEngine().compute()
    hist_wr   = analytics["win_rate"]

    ranked = ranker.rank(candidates)

    # Only fire grade B and above
    ranked = [c for c in ranked if c["grade"] in ("S", "A", "B")]

    print(f"      ✅ {len(ranked)} signal(s) after AI ranking")

    # ── Phase 4: Alert + Log ───────────────────────────────────────────────

    print(f"\n[4/7] Sending {len(ranked)} alert(s)...")

    for sig in ranked:

        confidence = conf_eng.estimate(
            trend_score=sig["trend_score"],
            quality_score=sig["quality_score"],
            historical_wr=hist_wr
        )

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

        # Append confidence to message
        message += f"\n🤖 Confidence: <b>{confidence}%</b>"

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

        print(f"  ✅ {sig['symbol']} {sig['direction']} | Grade {sig['grade']} | Score {sig['composite']}")

    # ── Phase 5: Track open signals ────────────────────────────────────────

    print("\n[5/7] Running signal tracker...")
    SignalTracker().run()

    # ── Phase 6: Analytics summary ─────────────────────────────────────────

    print("\n[6/7] Analytics...")
    stats = AnalyticsEngine().compute()
    print(
        f"      Signals: {stats['total_signals']} total | "
        f"{stats['open']} open | "
        f"WR: {stats['win_rate']}% | "
        f"PF: {stats['profit_factor']}"
    )

    print("\n[7/7] Done ✅")
    print("=" * 50)


if __name__ == "__main__":
    main()
