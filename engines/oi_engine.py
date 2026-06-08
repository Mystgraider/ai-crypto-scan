"""
Open Interest Engine — V5.8.3
===============================
Fixed: float(None) crash — Bitget OI API returns different structure.
Now fully fail-safe: any error = NEUTRAL (never crashes scanner).
"""


class OIEngine:

    def analyze(
        self,
        current_oi:   float,
        previous_oi:  float,
        price_change: float,
        direction:    str,
    ) -> dict:

        if previous_oi == 0 or current_oi == 0:
            return self._result("NEUTRAL", 0, 0.0)

        oi_change_pct = ((current_oi - previous_oi) / previous_oi) * 100

        oi_rising  = oi_change_pct >  0.5
        oi_falling = oi_change_pct < -0.5
        price_down = price_change   < -0.1
        price_up   = price_change   >  0.1

        if direction == "SHORT":
            if price_down and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            elif price_down and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            elif price_up and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)
        else:  # LONG
            if price_up and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            elif price_up and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            elif price_down and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)

        return self._result("NEUTRAL", 0, oi_change_pct)

    @staticmethod
    def _result(label, score_adj, oi_change_pct):
        return {
            "oi_signal":     label,
            "score_adj":     score_adj,
            "oi_change_pct": round(oi_change_pct, 2),
        }

    def fetch_oi(self, exchange, symbol: str) -> dict:
        """
        Fetch OI from exchange. Fully fail-safe.
        Returns available=False on any error — scanner continues normally.
        """
        try:
            # fetch_open_interest returns a dict
            oi_data = exchange.fetch_open_interest(symbol)

            # Bitget and OKX both return openInterestValue but
            # sometimes it's nested in 'info' or returned as None
            current_oi = (
                oi_data.get("openInterestValue") or
                oi_data.get("openInterest") or
                oi_data.get("info", {}).get("holdVol") or
                oi_data.get("info", {}).get("oi") or
                None
            )

            if current_oi is None:
                return {"current_oi": 0, "previous_oi": 0, "available": False}

            current_oi = float(current_oi)

            # Try to get history for previous value
            try:
                history = exchange.fetch_open_interest_history(
                    symbol, timeframe="1h", limit=2
                )
                if history and len(history) >= 2:
                    prev_raw = (
                        history[-2].get("openInterestValue") or
                        history[-2].get("openInterest") or
                        None
                    )
                    previous_oi = float(prev_raw) if prev_raw is not None else current_oi
                else:
                    previous_oi = current_oi
            except Exception:
                previous_oi = current_oi

            return {
                "current_oi":  current_oi,
                "previous_oi": previous_oi,
                "available":   True,
            }

        except Exception:
            # Silent fail — OI is a bonus, not required
            return {"current_oi": 0, "previous_oi": 0, "available": False}
