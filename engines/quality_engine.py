class QualityEngine:
    """
    Signal quality score 0-100.

    Volume score (60% weight):
      >= 3.0x = EXTREME  = 100
      >= 2.0x = HIGH     = 90
      >= 1.5x = ELEVATED = 80
      >= 1.2x = NORMAL   = 70
      >= 1.0x = BASELINE = 58
      <  1.0x = WEAK     = 0  ← BLOCKED (no conviction)

    RSI score (40% weight):
      LONG ideal: 45-60 (trending, not overbought)
      SHORT ideal: 40-55 (trending, not oversold)

    Anti-fake-signal rules:
      LONG  RSI > 70 → score 0 (chasing pump)
      SHORT RSI < 40 → score 0 (coin already low = bounce risk)
      SHORT RSI < 42 → score 20 (borderline, penalized)
    """

    # Minimum rel_volume to allow any signal
    MIN_VOLUME = 1.0

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        # ── Hard block: WEAK volume = no conviction ────────────────────
        if rel_volume < self.MIN_VOLUME:
            return 0.0

        # ── Volume score ───────────────────────────────────────────────
        if rel_volume >= 3.0:
            vol_score = 100
        elif rel_volume >= 2.0:
            vol_score = 90
        elif rel_volume >= 1.5:
            vol_score = 80
        elif rel_volume >= 1.2:
            vol_score = 70
        else:
            vol_score = 58   # 1.0-1.2x — baseline, barely acceptable

        # ── RSI score ──────────────────────────────────────────────────
        if direction == "LONG":
            if rsi > 70:
                rsi_score = 0     # overbought — hard block
            elif rsi > 65:
                rsi_score = 20    # hot — heavily penalized
            elif 45 <= rsi <= 60:
                rsi_score = 100   # ideal
            elif 40 <= rsi < 45 or 60 < rsi <= 65:
                rsi_score = 80
            elif 35 <= rsi < 40:
                rsi_score = 50
            else:
                rsi_score = 30    # very oversold — bounce risk for long too

        else:  # SHORT
            if rsi < 40:
                rsi_score = 0     # coin RSI too low = bounce imminent — HARD BLOCK
            elif rsi < 42:
                rsi_score = 20    # borderline — heavily penalized
            elif 42 <= rsi <= 55:
                rsi_score = 100   # ideal short zone
            elif 55 < rsi <= 60:
                rsi_score = 80
            elif 60 < rsi <= 65:
                rsi_score = 60
            elif rsi > 70:
                rsi_score = 0     # overbought — dangerous to short (squeeze risk)
            else:
                rsi_score = 40

        return round(vol_score * 0.6 + rsi_score * 0.4, 2)
