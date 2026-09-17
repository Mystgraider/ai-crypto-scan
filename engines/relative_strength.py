"""
Relative Strength Engine — Phase 5
=====================================
Measures a coin's performance vs BTC over the last N candles.

A coin that goes UP more than BTC in a bull run = strong
A coin that goes DOWN less than BTC in a bear run = strong

RS Score 0-100:
  > 70 = STRONG  (outperforming BTC — high priority)
  50-70 = NEUTRAL (in-line with BTC — allowed)
  < 50  = WEAK   (underperforming — deprioritize)

Used by AI ranker to boost strong coins and penalize weak ones.
"""


class RelativeStrengthEngine:

    def calculate(
        self,
        coin_closes: list[float],
        btc_closes:  list[float],
        periods:     int = 20,
    ) -> dict:
        """
        Compare coin return vs BTC return over last N periods.
        Returns RS score 0-100 and label.
        """

        if len(coin_closes) < periods + 1 or len(btc_closes) < periods + 1:
            return {"rs_score": 50.0, "rs_label": "NEUTRAL", "rs_ratio": 1.0}

        # Return over last N periods
        coin_return = (coin_closes[-1] - coin_closes[-periods]) / coin_closes[-periods]
        btc_return  = (btc_closes[-1]  - btc_closes[-periods])  / btc_closes[-periods]

        # RS ratio: coin return / BTC return
        # > 1.0 = coin outperforming BTC
        # < 1.0 = coin underperforming BTC
        if btc_return == 0:
            rs_ratio = 1.0
        else:
            rs_ratio = coin_return / btc_return if btc_return > 0 else (
                btc_return / coin_return if coin_return != 0 else 1.0
            )

        # Normalize ratio to 0-100 score
        # ratio 2.0+ = score 100 (coin 2x stronger than BTC)
        # ratio 1.0  = score 60  (in-line)
        # ratio 0.5  = score 30  (half BTC strength)
        # ratio 0.0  = score 0

        rs_score = min(100.0, max(0.0, rs_ratio * 60))
        rs_score = round(rs_score, 2)

        if rs_score >= 70:
            label = "STRONG"
        elif rs_score >= 50:
            label = "NEUTRAL"
        else:
            label = "WEAK"

        return {
            "rs_score":  rs_score,
            "rs_label":  label,
            "rs_ratio":  round(rs_ratio, 3),
            "coin_ret":  round(coin_return * 100, 2),
            "btc_ret":   round(btc_return  * 100, 2),
        }
