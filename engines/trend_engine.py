class TrendEngine:
    """
    Trend direction + score engine.

    Requirements for a valid signal:
    - EMA20 > EMA50 (LONG) or EMA20 < EMA50 (SHORT)
    - Price on the correct side of EMA20
    - ADX >= 20 (confirmed trend, not just noise)

    Score 0-100 based on EMA gap strength + ADX + ROC bonuses.
    Returns direction=NONE if ADX is too weak — prevents fake signals
    in ranging/choppy markets.
    """

    ADX_MIN = 20       # Minimum trend strength required
    ADX_STRONG = 25    # Bonus threshold

    def analyze(self, price, ema20, ema50, adx=None, roc=None):

        # Hard gate: no ADX = no confirmed trend = no signal
        if adx is not None and adx < self.ADX_MIN:
            return {"direction": "NONE", "trend": "RANGE", "score": 0.0}

        # ── LONG ──────────────────────────────────────────────────────
        if ema20 > ema50 and price > ema20:

            gap = ((ema20 - ema50) / ema50) * 100

            # Base 50, scale up with EMA gap strength
            # gap 0%  -> 50, gap 1% -> 60, gap 2% -> 70, gap 3% -> 80
            score = min(100.0, 50 + gap * 10)

            # ADX bonus
            if adx and adx >= self.ADX_STRONG:
                score = min(100.0, score + 8)

            # ROC bonus: positive momentum
            if roc and roc > 0:
                score = min(100.0, score + 4)

            return {
                "direction": "LONG",
                "trend": "BULLISH",
                "score": round(score, 2)
            }

        # ── SHORT ─────────────────────────────────────────────────────
        if ema20 < ema50 and price < ema20:

            gap = ((ema50 - ema20) / ema50) * 100
            score = min(100.0, 50 + gap * 10)

            if adx and adx >= self.ADX_STRONG:
                score = min(100.0, score + 8)

            if roc and roc < 0:
                score = min(100.0, score + 4)

            return {
                "direction": "SHORT",
                "trend": "BEARISH",
                "score": round(score, 2)
            }

        # Price between EMAs or EMAs not aligned
        return {"direction": "NONE", "trend": "RANGE", "score": 0.0}
