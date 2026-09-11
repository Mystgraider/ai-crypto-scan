"""
Open Interest Engine — V6.9.25
==============================
Calculates OI confirmation when data is available.

Unavailable OI is explicitly marked unavailable. It is not represented as
NEUTRAL because NEUTRAL means the market was actually observed and did not
meet a directional OI condition.
"""


class OIEngine:

    def analyze(
        self,
        current_oi: float,
        previous_oi: float,
        price_change: float,
        direction: str,
    ) -> dict:
        if previous_oi <= 0 or current_oi <= 0:
            return self._unavailable("invalid_oi_values")

        oi_change_pct = ((current_oi - previous_oi) / previous_oi) * 100
        oi_rising = oi_change_pct > 0.5
        oi_falling = oi_change_pct < -0.5
        price_down = price_change < -0.1
        price_up = price_change > 0.1

        if direction == "SHORT":
            if price_down and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            if price_down and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            if price_up and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)
        else:
            if price_up and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            if price_up and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            if price_down and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)

        return self._result("NEUTRAL", 0, oi_change_pct)

    @staticmethod
    def _result(label, score_adj, oi_change_pct):
        return {
            "available": True,
            "oi_signal": label,
            "score_adj": score_adj,
            "oi_change_pct": round(oi_change_pct, 2),
        }

    @staticmethod
    def _unavailable(reason):
        return {
            "available": False,
            "oi_signal": "UNAVAILABLE",
            "score_adj": 0,
            "oi_change_pct": None,
            "reason": reason,
        }

    def fetch_oi(self, exchange, symbol: str) -> dict:
        """Fetch current and previous OI, preserving explicit availability."""
        try:
            oi_data = exchange.fetch_open_interest(symbol)
            current_oi = (
                oi_data.get("openInterestValue") or
                oi_data.get("openInterest") or
                oi_data.get("info", {}).get("holdVol") or
                oi_data.get("info", {}).get("oi") or
                None
            )
            if current_oi is None:
                return {
                    "current_oi": 0,
                    "previous_oi": 0,
                    "available": False,
                    "reason": "current_oi_missing",
                }

            current_oi = float(current_oi)
            if current_oi <= 0:
                return {
                    "current_oi": current_oi,
                    "previous_oi": 0,
                    "available": False,
                    "reason": "invalid_current_oi",
                }

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
                    if prev_raw is not None:
                        previous_oi = float(prev_raw)
                    else:
                        return {
                            "current_oi": current_oi,
                            "previous_oi": 0,
                            "available": False,
                            "reason": "previous_oi_missing",
                        }
                else:
                    return {
                        "current_oi": current_oi,
                        "previous_oi": 0,
                        "available": False,
                        "reason": "oi_history_unavailable",
                    }
            except Exception:
                return {
                    "current_oi": current_oi,
                    "previous_oi": 0,
                    "available": False,
                    "reason": "oi_history_fetch_error",
                }

            if previous_oi <= 0:
                return {
                    "current_oi": current_oi,
                    "previous_oi": previous_oi,
                    "available": False,
                    "reason": "invalid_previous_oi",
                }

            return {
                "current_oi": current_oi,
                "previous_oi": previous_oi,
                "available": True,
            }

        except Exception as e:
            print(f"  ⚠️  OI fetch failed {symbol}: {e}")
            return {
                "current_oi": 0,
                "previous_oi": 0,
                "available": False,
                "reason": "fetch_error",
            }
