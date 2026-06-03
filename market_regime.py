class MarketRegimeEngine:

    def detect(
        self,
        ema20,
        ema50,
        atr_pct,
        rel_volume
    ):

        gap_pct = abs(
            ema20 - ema50
        ) / ema50 * 100

        # TREND

        if (
            gap_pct > 1.0 and
            atr_pct > 1.0
        ):

            return {
                "regime": "TREND",
                "score": 4
            }

        # EXPANSION

        if (
            atr_pct > 2.5 and
            rel_volume > 1.5
        ):

            return {
                "regime": "EXPANSION",
                "score": 5
            }

        # COMPRESSION

        if (
            atr_pct < 0.8 and
            rel_volume < 0.8
        ):

            return {
                "regime": "COMPRESSION",
                "score": 1
            }

        # RANGE

        return {
            "regime": "RANGE",
            "score": 2
        }
