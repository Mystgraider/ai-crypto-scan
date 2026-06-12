class QualityEngine:
    """
    Signal quality score 0-100 — V6.0
    =====================================
    Upgrades from V5.x:
    - Stoch RSI incorporated into quality scoring
    - BB %B position affects quality (middle of band = healthiest)
    - MACD histogram strength as quality bonus
    - Tighter RSI zone scoring (sweet spot narrower = fewer fake signals)
    - Volume tiers refined

    Hard blocks:
      - rel_volume < 1.0        → no conviction
      - LONG  RSI > 70          → overbought hard block
      - SHORT RSI < 30          → extreme oversold hard block
      - LONG  Stoch K > 85      → overbought (caught at extension)
      - SHORT Stoch K < 15      → oversold  (caught at extension)
    """

    MIN_VOLUME    = 1.0
    LONG_RSI_MAX  = 70
    SHORT_RSI_MIN = 30

    def score(self, rel_volume: float, rsi: float, direction: str,
              stoch_k: float = 50.0, bb_pct_b: float = 0.5,
              macd_hist: float = 0.0) -> float:

        # Hard block: weak volume
        if rel_volume < self.MIN_VOLUME:
            return 0.0

        # Hard block: extreme RSI
        if direction == "LONG"  and rsi  > self.LONG_RSI_MAX:
            return 0.0
        if direction == "SHORT" and rsi  < self.SHORT_RSI_MIN:
            return 0.0

        # Hard block: Stoch RSI extremes
        if direction == "LONG"  and stoch_k > 85:
            return 0.0
        if direction == "SHORT" and stoch_k < 15:
            return 0.0

        # ── Volume score ───────────────────────────────────────────────
        if   rel_volume >= 3.0:  vol_score = 100
        elif rel_volume >= 2.0:  vol_score = 90
        elif rel_volume >= 1.5:  vol_score = 80
        elif rel_volume >= 1.2:  vol_score = 70
        else:                    vol_score = 58

        # ── RSI score ──────────────────────────────────────────────────
        if direction == "LONG":
            if   rsi > 65:           rsi_score = 20
            elif 50 <= rsi <= 62:    rsi_score = 100   # ideal long zone
            elif 45 <= rsi < 50:     rsi_score = 85
            elif 62 < rsi <= 65:     rsi_score = 70
            elif 40 <= rsi < 45:     rsi_score = 55
            elif 35 <= rsi < 40:     rsi_score = 35
            else:                    rsi_score = 20

        else:  # SHORT
            if   rsi < 30:           rsi_score = 0
            elif rsi < 35:           rsi_score = 25
            elif rsi < 40:           rsi_score = 45
            elif 40 <= rsi <= 52:    rsi_score = 100   # ideal short zone
            elif 52 < rsi <= 58:     rsi_score = 80
            elif 58 < rsi <= 65:     rsi_score = 55
            elif rsi > 70:           rsi_score = 0
            else:                    rsi_score = 35

        # ── Stoch RSI score ────────────────────────────────────────────
        if direction == "LONG":
            if   40 <= stoch_k <= 70:  stoch_score = 20   # healthy zone bonus
            elif stoch_k > 70:         stoch_score = -10  # getting extended
            else:                      stoch_score = 0

        else:  # SHORT
            if   30 <= stoch_k <= 60:  stoch_score = 20
            elif stoch_k < 30:         stoch_score = -10
            else:                      stoch_score = 0

        # ── BB position score ──────────────────────────────────────────
        if direction == "LONG":
            if   0.2 <= bb_pct_b <= 0.6:  bb_score = 10   # middle to mid-upper
            elif bb_pct_b > 0.8:           bb_score = -10  # near top
            else:                          bb_score = 0

        else:  # SHORT
            if   0.4 <= bb_pct_b <= 0.8:  bb_score = 10   # middle to mid-lower
            elif bb_pct_b < 0.2:           bb_score = -10  # near bottom
            else:                          bb_score = 0

        # ── MACD histogram bonus ───────────────────────────────────────
        if direction == "LONG"  and macd_hist > 0:  macd_bonus = 5
        elif direction == "SHORT" and macd_hist < 0: macd_bonus = 5
        else:                                         macd_bonus = 0

        raw = (vol_score * 0.55 + rsi_score * 0.35) + stoch_score + bb_score + macd_bonus
        return round(max(0.0, min(100.0, raw)), 2)
