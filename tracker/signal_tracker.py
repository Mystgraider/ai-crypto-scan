"""
Signal Tracker — V6.4
==================================
Tracks active signals and persists lifecycle events.

Lifecycle:
    OPEN -> OPEN_TP1 -> OPEN_TP2 -> TP3_HIT
    OPEN/OPEN_TP1/OPEN_TP2 -> SL_HIT

After TP1, SL moves to breakeven and the signal remains active.
Phase 1B also records event timestamps/prices and terminal realized R.

Phase 2D-H.4 adds explicit execution-evidence recording. TP1/TP2/TP3
price milestones do not imply that an order was actually filled.
"""

from datetime import datetime, timezone, timedelta
from storage.signal_logger import (
    load_signals,
    update_signal_tracking,
    record_execution_event,
)
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

    def record_partial_execution(
        self,
        symbol: str,
        direction: str,
        entry: float,
        execution_level: str,
        qty_pct: float,
        exit_price: float,
        realized_r: float,
        event_at: str | None = None,
        remaining_position_pct: float | None = None,
    ) -> bool:
        """Record explicit execution evidence without inferring or changing status."""
        return record_execution_event(
            symbol=symbol,
            direction=direction,
            entry=entry,
            execution_level=execution_level,
            qty_pct=qty_pct,
            exit_price=exit_price,
            realized_r=realized_r,
            event_at=event_at,
            remaining_position_pct=remaining_position_pct,
        )

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
                candle = df.iloc[-1]
                price = float(candle["close"])
                high = float(candle["high"])
                low = float(candle["low"])
            except Exception as e:
                print(f"  ⚠️  {symbol}: price fetch failed — {e}")
                continue

            result = self._check(
                direction,
                price,
                entry,
                sl,
                tp1,
                tp2,
                tp3,
                status,
                high=high,
                low=low,
            )
            if not result:
                continue

            new_status = result["status"]
            new_sl = result.get("sl")
            event_price = result.get("event_price", price)
            terminal = new_status in {"TP3_HIT", "SL_HIT"}
            realized_r = None
            if terminal:
                if new_status == "TP3_HIT":
                    realized_r = self._realized_r(direction, entry, initial_sl, event_price)
                else:
                    # If SL is breakeven after TP1, terminal R is 0 here.
                    # The current schema has no partial-exit quantity, so
                    # partial TP1/TP2 P&L is intentionally not fabricated.
                    realized_r = self._realized_r(direction, entry, sl, event_price)

            updated = update_signal_tracking(
                symbol, direction, entry, new_status,
                new_sl=new_sl,
                event_at=now.isoformat(),
                event_price=event_price,
                realized_r=realized_r,
            )

            if updated:
                suffix = f" | SL→{new_sl}" if new_sl is not None else ""
                r_suffix = f" | R={realized_r:.2f}" if realized_r is not None else ""
                print(f"  🔄 {symbol} {direction} → {new_status} @ {event_price:.4f}{suffix}{r_suffix}")

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

    def _check(
        self,
        direction,
        price,
        entry,
        sl,
        tp1,
        tp2,
        tp3,
        status="OPEN",
        high=None,
        low=None,
    ) -> dict | None:
        """Check lifecycle milestones using candle high/low when available.

        OHLC extremes detect intrabar level touches that the candle close can
        miss. When high/low are omitted, the method preserves its legacy
        close-only behavior and return shape for existing callers/tests.

        SL remains checked first to preserve the existing conservative
        behavior when one candle spans both a stop and a target and exact
        tick ordering is unavailable.
        """
        if direction == "LONG":
            sl_hit = self._long_sl_hit
            tp_hit = self._long_tp_hit
        elif direction == "SHORT":
            sl_hit = self._short_sl_hit
            tp_hit = self._short_tp_hit
        else:
            return None

        has_ohlc = high is not None and low is not None
        candle_high = price if high is None else high
        candle_low = price if low is None else low

        def level_hit(level):
            if direction == "LONG":
                return candle_high >= level
            return candle_low <= level

        def result(status_name, event_price=None, sl_value=None):
            outcome = {"status": status_name}
            if sl_value is not None:
                outcome["sl"] = sl_value
            if has_ohlc:
                outcome["event_price"] = price if event_price is None else event_price
            return outcome

        if sl_hit(candle_low if direction == "LONG" else candle_high, sl):
            return result("SL_HIT", sl)

        if status == "OPEN":
            if level_hit(tp3):
                return result("TP3_HIT", tp3)
            if level_hit(tp2):
                return result("OPEN_TP2", tp2, entry)
            if level_hit(tp1):
                return result("OPEN_TP1", tp1, entry)
        elif status == "OPEN_TP1":
            if level_hit(tp3):
                return result("TP3_HIT", tp3)
            if level_hit(tp2):
                return result("OPEN_TP2", tp2)
        elif status == "OPEN_TP2":
            if level_hit(tp3):
                return result("TP3_HIT", tp3)

        return None


if __name__ == "__main__":
    SignalTracker().run()
