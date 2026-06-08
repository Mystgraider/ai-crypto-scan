"""
Open Interest Engine — V5.8
=============================
Confirms trend strength using OI data.

OI + Price analysis:
  Price DOWN + OI UP   = new shorts entering = confirmed downtrend ✅ SHORT
  Price DOWN + OI DOWN = longs closing (profit taking) = weak signal ⚠️
  Price UP   + OI UP   = new longs entering = confirmed uptrend ✅ LONG
  Price UP   + OI DOWN = shorts closing (covering) = weak signal ⚠️

Score bonus:
  CONFIRMED: +10 to composite score
  NEUTRAL:   0
  DIVERGING: -10 (price and OI disagree = trend may reverse)
"""


class OIEngine:

    def analyze(
        self,
        current_oi:   float,
        previous_oi:  float,
        price_change: float,   # % change in price
        direction:    str,
    ) -> dict:

        if previous_oi == 0:
            return self._result("NEUTRAL", 0, 0.0)

        oi_change_pct = ((current_oi - previous_oi) / previous_oi) * 100

        oi_rising  = oi_change_pct >  0.5   # OI grew > 0.5%
        oi_falling = oi_change_pct < -0.5   # OI fell > 0.5%
        price_down = price_change   < -0.1
        price_up   = price_change   >  0.1

        if direction == "SHORT":
            if price_down and oi_rising:
                # New shorts entering = strong confirmation
                return self._result("CONFIRMED", 10, oi_change_pct)
            elif price_down and oi_falling:
                # Just profit-taking, not real selling pressure
                return self._result("WEAK", -5, oi_change_pct)
            elif price_up and oi_rising:
                # New longs entering against our SHORT = danger
                return self._result("DIVERGING", -10, oi_change_pct)
            else:
                return self._result("NEUTRAL", 0, oi_change_pct)

        else:  # LONG
            if price_up and oi_rising:
                return self._result("CONFIRMED", 10, oi_change_pct)
            elif price_up and oi_falling:
                return self._result("WEAK", -5, oi_change_pct)
            elif price_down and oi_rising:
                return self._result("DIVERGING", -10, oi_change_pct)
            else:
                return self._result("NEUTRAL", 0, oi_change_pct)

    @staticmethod
    def _result(label, score_adj, oi_change_pct):
        return {
            "oi_signal":      label,
            "score_adj":      score_adj,
            "oi_change_pct":  round(oi_change_pct, 2),
        }

    def fetch_oi(self, exchange, symbol: str) -> dict:
        """
        Fetch current and previous OI from OKX.
        Returns dict with current, previous, and price_change.
        Fails safe (returns neutral) if API unavailable.
        """
        try:
            # OKX open interest
            oi_data = exchange.fetch_open_interest(symbol)
            current_oi = float(oi_data.get("openInterestValue", 0))

            # Get OI history for previous value (use 2 data points)
            history = exchange.fetch_open_interest_history(
                symbol, timeframe="1h", limit=2
            )
            if history and len(history) >= 2:
                previous_oi = float(history[-2].get("openInterestValue", current_oi))
            else:
                previous_oi = current_oi

            return {
                "current_oi":  current_oi,
                "previous_oi": previous_oi,
                "available":   True,
            }

        except Exception as e:
            print(f"  ⚠️  OI fetch failed: {e}")
            return {
                "current_oi":  0,
                "previous_oi": 0,
                "available":   False,
            }
