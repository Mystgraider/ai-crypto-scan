class QualityEngine:
    """
    Signal quality score 0-100.

    Hard blocks:
      - rel_volume < 1.0        → no conviction
      - LONG  RSI > 70          → overbought hard block
      - SHORT RSI < 30          → extreme oversold hard block (was 40, too strict for BEAR)

    RSI 30-40 for SHORT: allowed but penalized
    (In BEAR markets coins stay in RSI 30-40 zone for extended periods)
    """

    MIN_VOLUME    = 1.0
    LONG_RSI_MAX  = 70
    SHORT_RSI_MIN = 30   # lowered from 40 — allows BEAR market shorts

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        # Hard block: weak volume
        if rel_volume < self.MIN_VOLUME:
            return 0.0

        # Hard block: extreme RSI
        if direction == "LONG" and rsi > self.LONG_RSI_MAX:
            return 0.0

        if direction == "SHORT" and rsi < self.SHORT_RSI_MIN:
            return 0.0  # extreme oversold — even in BEAR, bounce imminent

        # Volume score
        if rel_volume >= 3.0:   vol_score = 100
        elif rel_volume >= 2.0: vol_score = 90
        elif rel_volume >= 1.5: vol_score = 80
        elif rel_volume >= 1.2: vol_score = 70
        else:                   vol_score = 58

        # RSI score
        if direction == "LONG":
            if rsi > 65:              rsi_score = 20
            elif 45 <= rsi <= 60:     rsi_score = 100
            elif 40 <= rsi < 45:      rsi_score = 80
            elif 60 < rsi <= 65:      rsi_score = 80
            elif 35 <= rsi < 40:      rsi_score = 50
            else:                     rsi_score = 30

        else:  # SHORT
            if rsi < 30:              rsi_score = 0    # hard block above
            elif rsi < 35:            rsi_score = 30   # extreme — penalized
            elif rsi < 40:            rsi_score = 50   # oversold — penalized (was 0)
            elif 40 <= rsi <= 55:     rsi_score = 100  # ideal short zone
            elif 55 < rsi <= 60:      rsi_score = 80
            elif 60 < rsi <= 65:      rsi_score = 60
            elif rsi > 70:            rsi_score = 0    # overbought — squeeze risk
            else:                     rsi_score = 40

        return round(vol_score * 0.6 + rsi_score * 0.4, 2)
