class TrendEngine:

    def analyze(
        self,
        price,
        ema20,
        ema50
    ):

        # Bullish

        if (
            ema20 > ema50 and
            price > ema20
        ):

            gap = (
                (ema20 - ema50)
                /
                ema50
            ) * 100

            score = min(
                100,
                60 + gap * 10
            )

            return {

                "direction":
                "LONG",

                "trend":
                "BULLISH",

                "score":
                round(score, 2)
            }

        # Bearish

        if (
            ema20 < ema50 and
            price < ema20
        ):

            gap = (
                (ema50 - ema20)
                /
                ema50
            ) * 100

            score = min(
                100,
                60 + gap * 10
            )

            return {

                "direction":
                "SHORT",

                "trend":
                "BEARISH",

                "score":
                round(score, 2)
            }

        return {

            "direction":
            "NONE",

            "trend":
            "RANGE",

            "score":
            40
        }
