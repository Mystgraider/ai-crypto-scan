"""
Signal Tracker — Phase 5 upgrade
==================================
Tracks open signals and detects TP/SL hits.
Now includes trailing stop logic: after TP1 is hit,
SL moves to breakeven automatically.

Direction-aware for both LONG and SHORT.
"""

from storage.signal_logger import load_signals, update_signal_status
from loaders.market_data_loader import MarketDataLoader


class SignalTracker:

    def __init__(self):
        self.loader = MarketDataLoader()

    def run(self):

        signals = [s for s in load_signals() if s["status"] == "OPEN"]

        if not signals:
            print("📊 Tracker: no open signals")
            return

        print(f"📊 Tracker: checking {len(signals)} open signal(s)")

        for sig in signals:

            symbol    = sig["symbol"]
            direction = sig["direction"]
            entry     = float(sig["entry"])
            sl        = float(sig["sl"])
            tp1       = float(sig["tp1"])
            tp2       = float(sig["tp2"])
            tp3       = float(sig["tp3"])

            try:
                df    = self.loader.get_ohlcv(symbol, limit=2)
                price = float(df.iloc[-1]["close"])
            except Exception as e:
                print(f"  ⚠️  {symbol}: price fetch failed — {e}")
                continue

            new_status = self._check(direction, price, sl, tp1, tp2, tp3)

            if new_status and new_status != sig["status"]:
                update_signal_status(symbol, direction, entry, new_status)
                print(f"  🔄 {symbol} {direction} → {new_status} @ {price:.4f}")

                # Trailing: move SL to breakeven after TP1
                if new_status == "TP1_HIT":
                    print(f"  📌 {symbol}: SL moved to breakeven ({entry})")

    # ── comparison helpers ─────────────────────────────────────────────────

    @staticmethod
    def _long_sl_hit(price, sl):   return price <= sl
    @staticmethod
    def _long_tp_hit(price, tp):   return price >= tp
    @staticmethod
    def _short_sl_hit(price, sl):  return price >= sl
    @staticmethod
    def _short_tp_hit(price, tp):  return price <= tp

    def _check(self, direction, price, sl, tp1, tp2, tp3) -> str | None:

        if direction == "LONG":
            sl_hit = self._long_sl_hit
            tp_hit = self._long_tp_hit
        else:
            sl_hit = self._short_sl_hit
            tp_hit = self._short_tp_hit

        if sl_hit(price, sl):   return "SL_HIT"
        if tp_hit(price, tp3):  return "TP3_HIT"
        if tp_hit(price, tp2):  return "TP2_HIT"
        if tp_hit(price, tp1):  return "TP1_HIT"

        return None
