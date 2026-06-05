"""
Elite Futures Scanner V5.1
==========================
Orchestrator — blueprint workflow:

  GitHub Actions (every 5min)
  -> Load Top 300 Symbols (by volume)
  -> Load OHLCV (1H candles)
  -> Apply Indicators (EMA20/50, RSI, ATR, ADX, ROC, RelVol)
  -> Trend Engine (direction + score, ADX gate)
  -> Quality Engine (volume + RSI score)
  -> Risk Engine (Entry, SL, TP1/2/3, RR validation)
  -> Signal Validator (all gates must pass)
  -> AI Ranker (sort by composite score)
  -> Telegram Alert (HTML formatted)
  -> Signal Logger (CSV)
  -> Signal Tracker (update open signals)
  -> Analytics summary (win rate, PF)
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


# ── helpers ───────────────────────────────────────────────────────────────────

def grade_score(score: float) -> str:
    if score >= CONFIG["signal_score_s"]: return "S"
    if score >= CONFIG["signal_score_a"]: return "A"
    if score >= CONFIG["signal_score_b"]: return "B"
    return "C"


# ── main ──────────────────────────────────────────────────────────────────────

def main():

    print("=" * 55)
    print("🚀 Elite Futures Scanner V5.1 — Starting")
    print("=" * 55)

    # ── Step 1: Load Symbols ───────────────────────────────────────────────
    print("\n[1/7] Loading top symbols...")
    symbols = TopSymbolsLoader().get_top_symbols()
    print(f"      ✅ {len(symbols)} symbols loaded")

    if not symbols:
        print("      ❌ No symbols loaded — check exchange config")
        return

    # ── Step 2: Scan ───────────────────────────────────────────────────────
    market_loader  = MarketDataLoader()
    trend_engine   = TrendEngine()
    quality_engine = QualityEngine()
    risk_engine    = RiskEngine()
    validator      = SignalValidator()

    print(f"\n[2/7] Scanning {len(symbols)} symbols...")

    candidates   = []
    skipped_cd   = 0
    skipped_trend = 0
    skipped_qual  = 0
    skipped_risk  = 0
    errors        = 0

    for symbol in symbols:

        # Cooldown check
        if is_on_cooldown(symbol):
            skipped_cd += 1
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

            # Trend (includes ADX gate — returns NONE if ADX < 20)
            trend       = trend_engine.analyze(price=price, ema20=ema20, ema50=ema50, adx=adx, roc=roc)
            direction   = trend["direction"]
            trend_score = trend["score"]

            if direction == "NONE":
                skipped_trend += 1
                continue

            # Quality
            quality_score = quality_engine.score(rel_volume=rel_volume, rsi=rsi, direction=direction)

            # Risk levels
            risk = risk_engine.calculate(direction, price, atr)

            # Final validation gate
            if not validator.validate(direction, trend_score, quality_score, risk):
                if risk is None:
                    skipped_risk += 1
                else:
                    skipped_qual += 1
                continue

            composite = round(trend_score * 0.6 + quality_score * 0.4, 2)
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
                "rsi":           round(rsi, 2),
                "adx":           round(adx, 2),
                "rel_volume":    round(rel_volume, 2),
            })

        except Exception as e:
            errors += 1
            print(f"  ⚠️  {symbol}: {e}")

    print(f"      ✅ {len(candidates)} candidate(s) found")
    print(f"      📊 Skipped — cooldown:{skipped_cd} | no trend:{skipped_trend} | low quality:{skipped_qual} | bad risk:{skipped_risk} | errors:{errors}")

    # ── Step 3: AI Ranking ─────────────────────────────────────────────────
    print("\n[3/7] AI Ranking...")

    analytics = AnalyticsEngine().compute()
    hist_wr   = analytics["win_rate"]

    ranker = AISignalRanker()
    ranked = ranker.rank(candidates)

    # Cap signals per run to avoid spam
    max_signals = CONFIG["max_signals_per_run"]
    ranked = ranked[:max_signals]

    print(f"      ✅ {len(ranked)} signal(s) to fire (max {max_signals} per run)")

    # ── Step 4: Alert + Log ────────────────────────────────────────────────
    print(f"\n[4/7] Sending {len(ranked)} alert(s)...")

    conf_eng = ConfidenceEngine()

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

        message += (
            f"\n\n📊 <i>ADX: {sig['adx']} | RSI: {sig['rsi']} | Vol: {sig['rel_volume']}x</i>"
            f"\n🤖 Confidence: <b>{confidence}%</b>"
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

        print(f"  ✅ {sig['symbol']} {sig['direction']} | Grade {sig['grade']} | Score {sig['composite']} | ADX {sig['adx']}")

    # ── Step 5: Track open signals ─────────────────────────────────────────
    print("\n[5/7] Running signal tracker...")
    SignalTracker().run()

    # ── Step 6: Analytics ──────────────────────────────────────────────────
    print("\n[6/7] Analytics...")
    stats = AnalyticsEngine().compute()
    print(
        f"      Signals: {stats['total_signals']} total | "
        f"{stats['open']} open | "
        f"WR: {stats['win_rate']}% | "
        f"PF: {stats['profit_factor']}"
    )

    print("\n[7/7] Done ✅")
    print("=" * 55)


if __name__ == "__main__":
    main()
