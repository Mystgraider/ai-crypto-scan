class QualityEngine:
    """
    Scores signal quality based on volume confirmation and
    momentum (relative strength). Returns 0-100.
    """

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        vol_score = 0.0

        if rel_volume >= 2.5:
            vol_score = 100
        elif rel_volume >= 2.0:
            vol_score = 85
        elif rel_volume >= 1.5:
            vol_score = 70
        elif rel_volume >= 1.0:
            vol_score = 50
        else:
            vol_score = 20

        # RSI confirmation
        rsi_score = 0.0

        if direction == "LONG":
            # Ideal: RSI 45-60 (trending up but not overbought)
            if 45 <= rsi <= 60:
                rsi_score = 100
            elif 40 <= rsi < 45 or 60 < rsi <= 65:
                rsi_score = 70
            elif rsi < 40:
                rsi_score = 40   # oversold — risky for LONG entry
            else:
                rsi_score = 20   # overbought

        else:  # SHORT
            # Ideal: RSI 40-55 (trending down but not oversold)
            if 40 <= rsi <= 55:
                rsi_score = 100
            elif 35 <= rsi < 40 or 55 < rsi <= 60:
                rsi_score = 70
            elif rsi > 60:
                rsi_score = 40   # overbought — risky for SHORT entry
            else:
                rsi_score = 20   # oversold

        return round(vol_score * 0.6 + rsi_score * 0.4, 2)
