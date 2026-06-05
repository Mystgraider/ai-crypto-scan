class QualityEngine:
    """
    Signal quality score 0-100.

    Based on two factors:
    1. Relative Volume (60% weight) — confirms breakout/move is real
    2. RSI positioning (40% weight) — confirms momentum alignment

    Anti-fake-signal rules:
    - Overbought LONG (RSI > 70): score capped (chasing pump)
    - Oversold SHORT (RSI < 30): score capped (chasing dump)
    - Volume below average: heavily penalized
    """

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        # ── Volume score ───────────────────────────────────────────────
        if rel_volume >= 3.0:
            vol_score = 100
        elif rel_volume >= 2.0:
            vol_score = 90
        elif rel_volume >= 1.5:
            vol_score = 80
        elif rel_volume >= 1.2:
            vol_score = 70
        elif rel_volume >= 1.0:
            vol_score = 60
        elif rel_volume >= 0.8:
            vol_score = 40
        else:
            vol_score = 20

        # ── RSI score ──────────────────────────────────────────────────
        if direction == "LONG":
            if 45 <= rsi <= 60:
                rsi_score = 100   # ideal: trending up, not overbought
            elif 40 <= rsi < 45:
                rsi_score = 80    # slightly low, okay
            elif 60 < rsi <= 65:
                rsi_score = 80    # slightly elevated, okay
            elif 35 <= rsi < 40:
                rsi_score = 60    # oversold bounce risk
            elif 65 < rsi <= 70:
                rsi_score = 50    # getting hot
            elif rsi > 70:
                rsi_score = 20    # overbought — likely chasing, fake signal risk
            else:
                rsi_score = 40    # rsi < 35, deep oversold

        else:  # SHORT
            if 40 <= rsi <= 55:
                rsi_score = 100   # ideal: trending down, not oversold
            elif 55 < rsi <= 60:
                rsi_score = 80
            elif 35 <= rsi < 40:
                rsi_score = 80
            elif 60 < rsi <= 65:
                rsi_score = 60
            elif 30 <= rsi < 35:
                rsi_score = 50
            elif rsi < 30:
                rsi_score = 20    # oversold — chasing dump, fake signal risk
            else:
                rsi_score = 40    # rsi > 65

        return round(vol_score * 0.6 + rsi_score * 0.4, 2)
