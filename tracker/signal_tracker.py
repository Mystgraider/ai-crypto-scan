from storage.signal_logger import load_signals, update_signal_status
from loaders.market_data_loader import MarketDataLoader


class SignalTracker:
    """
    Loads all OPEN signals from storage and checks current price
    against each signal's SL / TP levels to update their status.
    Direction-aware: LONG and SHORT use opposite comparison logic.
    """

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
                print(f"  ⚠️  {symbol}: could not fetch price — {e}")
                continue

            new_status = self._check(direction, price, sl, tp1, tp2, tp3)

            if new_status and new_status != sig["status"]:
                update_signal_status(symbol, direction, entry, new_status)
                print(f"  🔄 {symbol} {direction} → {new_status} @ {price}")

    # ── helpers ─────────────────────────────────────────────────────────

    @staticmethod
    def _above(price, level):
        return price >= level

    @staticmethod
    def _below(price, level):
        return price <= level

    def _check(self, direction, price, sl, tp1, tp2, tp3) -> str | None:

        is_long = direction == "LONG"
        hit     = self._above if is_long else self._below
        sl_hit  = self._below if is_long else self._above

        if sl_hit(price, sl):
            return "SL_HIT"

        if hit(price, tp3):
            return "TP3_HIT"

        if hit(price, tp2):
            return "TP2_HIT"

        if hit(price, tp1):
            return "TP1_HIT"

        return None
