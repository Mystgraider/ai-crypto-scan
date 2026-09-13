"""
Relative Strength Engine — Phase 5
=====================================
Measures a coin's performance vs BTC over the last N candles.

A coin that UP more than BTC = strong relative performance.
A coin that DOWN less than BTC = strong relative performance.
A coin that moves against BTC is evaluated by relative performance,
not by the sign of the raw return ratio.

RS Score 0-100:
  > 70 = STRONG  (outperforming BTC — high priority)
  50-70 = NEUTRAL (in-line with BTC — allowed)
  < 50  = WEAK   (underperforming — deprioritize)

Used by AI ranker to boost strong coins and penalize weak ones.
"""

import math


class RelativeStrengthEngine:

    _NEUTRAL = {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}

    @staticmethod
    def _is_valid_price(value) -> bool:
        """Accept only finite, strictly positive numeric prices."""
        try:
            return math.isfinite(value) and value > 0
        except (TypeError, ValueError):
            return False

    def calculate(
        self,
        coin_closes: list[float],
        btc_closes: list[float],
        periods: int = 20,
    ) -> dict:
        """
        Compare coin return vs BTC return over the last N periods.

        Relative performance is measured as the ratio of ending wealth:

            rs_ratio = (1 + coin_return) / (1 + btc_return)

        The starting candle is N periods before the final candle, so N
        periods require at least N + 1 closing prices.
        """
        if periods <= 0:
            return self._NEUTRAL.copy()

        if len(coin_closes) < periods + 1 or len(btc_closes) < periods + 1:
            return self._NEUTRAL.copy()

        # N periods means N intervals between the starting and ending close.
        start_index = -(periods + 1)
        coin_start = coin_closes[start_index]
        btc_start = btc_closes[start_index]
        coin_end = coin_closes[-1]
        btc_end = btc_closes[-1]

        if not all(
            self._is_valid_price(value)
            for value in (coin_start, coin_end, btc_start, btc_end)
        ):
            return self._NEUTRAL.copy()

        coin_return = (coin_end - coin_start) / coin_start
        btc_return = (btc_end - btc_start) / btc_start

        if not math.isfinite(coin_return) or not math.isfinite(btc_return):
            return self._NEUTRAL.copy()

        btc_growth = 1.0 + btc_return
        coin_growth = 1.0 + coin_return

        if btc_growth <= 0 or coin_growth <= 0:
            return self._NEUTRAL.copy()

        rs_ratio = coin_growth / btc_growth
        if not math.isfinite(rs_ratio):
            return self._NEUTRAL.copy()

        # Normalize ratio to 0-100 score.
        # ratio 2.0 = score 100 (coin's ending wealth is 2x BTC's)
        # ratio 1.0 = score 60 (in-line)
        # ratio 0.5 = score 30 (coin underperformed BTC)
        rs_score = min(100.0, max(0.0, rs_ratio * 60))
        rs_score = round(rs_score, 2)

        if rs_score >= 70:
            label = "STRONG"
        elif rs_score >= 50:
            label = "NEUTRAL"
        else:
            label = "WEAK"

        return {
            "rs_score": rs_score,
            "rs_label": label,
            "rs_ratio": round(rs_ratio, 3),
            "coin_ret": round(coin_return * 100, 2),
            "btc_ret": round(btc_return * 100, 2),
        }
