"""
Signal Tracker — V6.4
==================================
Tracks active signals and persists lifecycle events.

Lifecycle:
    OPEN -> OPEN_TP1 -> OPEN_TP2 -> TP3_HIT
    OPEN/OPEN_TP1/OPEN_TP2 -> SL_HIT

After TP1, SL moves to breakeven and the signal remains active.
Phase 1B also records event timestamps/prices and terminal realized R.

Note: realized R is terminal-outcome R, not partial-position P&L.
Partial exits are not represented by the current signal schema.
"""

from datetime import datetime, timezone, timedelta
from storage.signal_logger import load_signals, update_signal_tracking
from loaders.market_data_loader import MarketDataLoader

SIGNAL_EXPIRY_HOURS = 72
ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}


class SignalTracker:

    def __init__(self):
        self.loader = MarketDataLoader()

    @staticmethod
    def _realized_r(direction, entry, initial_sl, exit_price):
        risk = abs(entry - initial_sl)
        if risk <= 0:
            return 0.0
        if direction == "LONG":
            return (exit_price - entry) / risk
        return (entry - exit_price) / risk

    def run(self):
        all_active = [s for s in load_signals() if s.get("status") in ACTIVE_STATUSES]
        if not all_active:
            print("📊 Tracker: no active signals")
            return

        now = datetime.now(timezone.utc)
        expiry_cutoff = now - timedelta(hours=SIGNAL_EXPIRY_HOURS)
        signals = []

        for s in all_active:
            try:
                ts = datetime.fromisoformat(s["timestamp"])
                if ts < expiry_cutoff:
                    age_h = int((now - ts).total_seconds() / 3600)
                    update_signal_tracking(
                        s["symbol"], s["direction"], float(s["entry"]), "EXPIRED",
                        event_at=now.isoformat(),
                    )
                    print(f"  ⏰ {s['symbol']} {s['direction']} → EXPIRED (age: {age_h}h)")
                    continue
            except Exception:
                pass
            signals.append(s)

        if not signals:
            print("📊 Tracker: no active signals")
            return

        print(f"📊 Tracker: checking {len(signals)} active signal(s)")

        for sig in signals:
            symbol = sig["symbol"]
            direction = sig["direction"]
            entry = float(sig["entry"])
            sl = float(sig["sl"])
            initial_sl = float(sig.get("initial_sl") or sl)
            tp1 = float(sig["tp1"])
            tp2 = float(sig["tp2"])
            tp3 = float(sig["tp3"])
            status = sig.get("status", "OPEN")

            try:
                df = self.loader.get_ohlcv(symbol, limit=2)
                price = float(df.iloc[-1]["close"])
            except Exception as e:
                print(f"  ⚠️  {symbol}: price fetch failed — {e}")
                continue

            result = self._check(direction, price, entry, sl, tp1, tp2, tp3, status)
            if not result:
                continue

            new_status = result["status"]
            new_sl = result.get("sl")
            terminal = new_status in {"TP3_HIT", "SL_HIT"}
            realized_r = None
            if terminal:
                if new_status == "TP3_HIT":
                    realized_r = self._realized_r(direction, entry, initial_sl, price)
                else:
                    # If SL is breakeven after TP1, terminal R is 0 here.
                    # The current schema has no partial-exit quantity, so
                    # partial TP1/TP2 P&L is intentionally not fabricated.
                    realized_r = self._realized_r(direction, entry, sl, price)

            updated = update_signal_tracking(
                symbol, direction, entry, new_status,
                new_sl=new_sl,
                event_at=now.isoformat(),
                event_price=price,
                realized_r=realized_r,
            )

            if updated:
                suffix = f" | SL→{new_sl}" if new_sl is not None else ""
                r_suffix = f" | R={realized_r:.2f}" if realized_r is not None else ""
                print(f"  🔄 {symbol} {direction} → {new_status} @ {price:.4f}{suffix}{r_suffix}")

    @staticmethod
    def _long_sl_hit(price, sl):
        return price <= sl

    @staticmethod
    def _long_tp_hit(price, tp):
        return price >= tp

    @staticmethod
    def _short_sl_hit(price, sl):
        return price >= sl

    @staticmethod
    def _short_tp_hit(price, tp):
        return price <= tp

    def _check(self, direction, price, entry, sl, tp1, tp2, tp3, status="OPEN") -> dict | None:
        if direction == "LONG":
            sl_hit = self._long_sl_hit
            tp_hit = self._long_tp_hit
        else:
            sl_hit = self._short_sl_hit
            tp_hit = self._short_tp_hit

        if sl_hit(price, sl):
            return {"status": "SL_HIT"}

        if status == "OPEN":
            if tp_hit(price, tp3):
                return {"status": "TP3_HIT"}
            if tp_hit(price, tp2):
                return {"status": "OPEN_TP2", "sl": entry}
            if tp_hit(price, tp1):
                return {"status": "OPEN_TP1", "sl": entry}
        elif status == "OPEN_TP1":
            if tp_hit(price, tp3):
                return {"status": "TP3_HIT"}
            if tp_hit(price, tp2):
                return {"status": "OPEN_TP2"}
        elif status == "OPEN_TP2":
            if tp_hit(price, tp3):
                return {"status": "TP3_HIT"}

        return None


if __name__ == "__main__":
    SignalTracker().run()
