class TrendEngine:

    def analyze(self, price, ema20, ema50, adx=None, roc=None):

        # LONG: price above both EMAs, fast above slow
        if ema20 > ema50 and price > ema20:

            gap = ((ema20 - ema50) / ema50) * 100
            score = min(100.0, 60 + gap * 10)

            # ADX bonus: strong trend confirmation
            if adx and adx > 25:
                score = min(100.0, score + 5)

            # ROC bonus: positive momentum
            if roc and roc > 0:
                score = min(100.0, score + 3)

            return {
                "direction": "LONG",
                "trend": "BULLISH",
                "score": round(score, 2)
            }

        # SHORT: price below both EMAs, fast below slow
        if ema20 < ema50 and price < ema20:

            gap = ((ema50 - ema20) / ema50) * 100
            score = min(100.0, 60 + gap * 10)

            if adx and adx > 25:
                score = min(100.0, score + 5)

            if roc and roc < 0:
                score = min(100.0, score + 3)

            return {
                "direction": "SHORT",
                "trend": "BEARISH",
                "score": round(score, 2)
            }

        return {
            "direction": "NONE",
            "trend": "RANGE",
            "score": 40.0
        }
