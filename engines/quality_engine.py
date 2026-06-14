class QualityEngine:
    """
    Quality Engine V6.1 — Data-driven from 16 closed signals

    KEY FINDINGS:
    - RSI 55-60 = 75% WR (best zone)
    - RSI 60-65 = 40% WR (getting hot)
    - Vol 1.0-1.5x = 67-100% WR (sweet spot)
    - Vol > 2.0x = 0-33% WR (already moved = chasing)
    - Vol > 5.0x = 0% WR (extreme volume = reversal)

    Hard blocks:
    - LONG  RSI > 70: overbought
    - SHORT RSI < 30: extreme oversold
    - Vol > 3.0x: extreme spike = reversal risk
    """

    MIN_VOLUME = 1.0
    MAX_VOLUME = 3.0    # hard cap — extreme volume = reversal
    LONG_RSI_MAX  = 70
    SHORT_RSI_MIN = 30

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        # Hard blocks
        if rel_volume < self.MIN_VOLUME:
            return 0.0

        if rel_volume > self.MAX_VOLUME:
            return 0.0  # extreme volume spike = likely already reversed

        if direction == "LONG" and rsi > self.LONG_RSI_MAX:
            return 0.0

        if direction == "SHORT" and rsi < self.SHORT_RSI_MIN:
            return 0.0

        # Volume score — sweet spot is 1.2-1.8x
        if rel_volume >= 2.5:    vol_score = 40   # too high — penalized
        elif rel_volume >= 2.0:  vol_score = 55   # elevated — slightly penalized
        elif rel_volume >= 1.5:  vol_score = 85   # good
        elif rel_volume >= 1.2:  vol_score = 100  # ideal
        elif rel_volume >= 1.0:  vol_score = 75   # acceptable
        else:                    vol_score = 0

        # RSI score — data shows 55-60 is the sweet spot
        if direction == "LONG":
            if 55 <= rsi <= 60:       rsi_score = 100  # ideal: 75% WR
            elif 50 <= rsi < 55:      rsi_score = 85   # good
            elif 60 < rsi <= 63:      rsi_score = 70   # getting hot
            elif 45 <= rsi < 50:      rsi_score = 70   # slightly low
            elif 63 < rsi <= 67:      rsi_score = 45   # too hot
            elif 40 <= rsi < 45:      rsi_score = 50
            elif rsi > 67:            rsi_score = 20
            else:                     rsi_score = 30

        else:  # SHORT
            if 40 <= rsi <= 45:       rsi_score = 100  # ideal for short
            elif 45 < rsi <= 50:      rsi_score = 85
            elif 35 <= rsi < 40:      rsi_score = 70
            elif 50 < rsi <= 55:      rsi_score = 70
            elif 30 <= rsi < 35:      rsi_score = 45
            elif 55 < rsi <= 60:      rsi_score = 45
            elif rsi > 65:            rsi_score = 20
            else:                     rsi_score = 30

        return round(vol_score * 0.55 + rsi_score * 0.45, 2)
