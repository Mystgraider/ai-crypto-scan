import math


class QualityEngine:
    """
    Quality Engine V6.1.

    The production score uses relative volume and RSI only. The additional
    indicator arguments are accepted for scanner compatibility but are not
    part of the V6.1 scoring formula.

    Hard blocks:
    - invalid/non-finite inputs or direction
    - LONG RSI > 70
    - SHORT RSI < 30
    - relative volume < 1.0x
    - relative volume > 3.0x
    """

    MIN_VOLUME = 1.0
    MAX_VOLUME = 3.0    # hard cap — extreme volume = reversal
    LONG_RSI_MAX = 70
    SHORT_RSI_MIN = 30

    def score(
        self,
        rel_volume: float,
        rsi: float,
        direction: str,
        stoch_k: float = None,   # accepted for compatibility, unused
        bb_pct_b: float = None,  # accepted for compatibility, unused
        macd_hist: float = None, # accepted for compatibility, unused
    ) -> float:
        # Fail closed on malformed inputs. Without this guard, NaN comparisons
        # fall through the threshold checks and can produce a non-zero score.
        try:
            rel_volume = float(rel_volume)
            rsi = float(rsi)
        except (TypeError, ValueError):
            return 0.0

        if direction not in ("LONG", "SHORT"):
            return 0.0

        if not math.isfinite(rel_volume) or not math.isfinite(rsi):
            return 0.0

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
        if rel_volume >= 2.5:    vol_score = 40
        elif rel_volume >= 2.0:  vol_score = 55
        elif rel_volume >= 1.5:  vol_score = 85
        elif rel_volume >= 1.2:  vol_score = 100
        elif rel_volume >= 1.0:  vol_score = 75
        else:                    vol_score = 0

        # RSI score
        if direction == "LONG":
            if 55 <= rsi <= 60:       rsi_score = 100
            elif 50 <= rsi < 55:      rsi_score = 85
            elif 60 < rsi <= 63:      rsi_score = 70
            elif 45 <= rsi < 50:      rsi_score = 70
            elif 63 < rsi <= 67:      rsi_score = 45
            elif 40 <= rsi < 45:      rsi_score = 50
            elif rsi > 67:            rsi_score = 20
            else:                     rsi_score = 30
        else:  # SHORT
            if 40 <= rsi <= 45:       rsi_score = 100
            elif 45 < rsi <= 50:      rsi_score = 85
            elif 35 <= rsi < 40:      rsi_score = 70
            elif 50 < rsi <= 55:      rsi_score = 70
            elif 30 <= rsi < 35:      rsi_score = 45
            elif 55 < rsi <= 60:      rsi_score = 45
            elif rsi > 65:            rsi_score = 20
            else:                     rsi_score = 30

        return round(vol_score * 0.55 + rsi_score * 0.45, 2)
