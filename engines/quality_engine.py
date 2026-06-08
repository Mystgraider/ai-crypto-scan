class QualityEngine:
    """
    Signal quality score 0-100.

    Hard blocks (return 0 regardless of other factors):
      - rel_volume < 1.0        → no conviction, no signal
      - LONG  RSI > 70          → overbought, hard block
      - SHORT RSI < 40          → coin bounce risk, hard block

    Volume score (60% weight):
      >= 3.0x = 100
      >= 2.0x = 90
      >= 1.5x = 80
      >= 1.2x = 70
      >= 1.0x = 58
      <  1.0x = 0  ← HARD BLOCK

    RSI score (40% weight):
      LONG  ideal: 45-60
      SHORT ideal: 42-55
    """

    MIN_VOLUME       = 1.0
    LONG_RSI_MAX     = 70    # block LONG if RSI above this
    SHORT_RSI_MIN    = 40    # block SHORT if RSI below this

    def score(self, rel_volume: float, rsi: float, direction: str) -> float:

        # ── Hard block: weak volume ────────────────────────────────────
        if rel_volume < self.MIN_VOLUME:
            return 0.0

        # ── Hard block: extreme RSI — check BEFORE volume bonus ───────
        if direction == "LONG" and rsi > self.LONG_RSI_MAX:
            return 0.0   # overbought — no matter how high the volume

        if direction == "SHORT" and rsi < self.SHORT_RSI_MIN:
            return 0.0   # coin too low — bounce risk regardless of volume

        # ── Volume score ───────────────────────────────────────────────
        if rel_volume >= 3.0:   vol_score = 100
        elif rel_volume >= 2.0: vol_score = 90
        elif rel_volume >= 1.5: vol_score = 80
        elif rel_volume >= 1.2: vol_score = 70
        else:                   vol_score = 58

        # ── RSI score ──────────────────────────────────────────────────
        if direction == "LONG":
            if rsi > 65:                rsi_score = 20
            elif 45 <= rsi <= 60:       rsi_score = 100
            elif 40 <= rsi < 45:        rsi_score = 80
            elif 60 < rsi <= 65:        rsi_score = 80
            elif 35 <= rsi < 40:        rsi_score = 50
            else:                       rsi_score = 30

        else:  # SHORT
            if rsi < 42:                rsi_score = 20   # borderline
            elif 42 <= rsi <= 55:       rsi_score = 100  # ideal
            elif 55 < rsi <= 60:        rsi_score = 80
            elif 60 < rsi <= 65:        rsi_score = 60
            elif rsi > 70:              rsi_score = 0    # overbought SHORT = squeeze risk
            else:                       rsi_score = 40

        return round(vol_score * 0.6 + rsi_score * 0.4, 2)
