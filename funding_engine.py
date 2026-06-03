class FundingEngine:

    def analyze(
        self,
        funding_rate
    ):

        funding_pct = (
            funding_rate * 100
        )

        if funding_pct >= 0.05:

            return {
                "grade": "EXTREME_LONG",
                "score": -2
            }

        if funding_pct >= 0.02:

            return {
                "grade": "LONG_HEAVY",
                "score": -1
            }

        if funding_pct <= -0.05:

            return {
                "grade": "EXTREME_SHORT",
                "score": -2
            }

        if funding_pct <= -0.02:

            return {
                "grade": "SHORT_HEAVY",
                "score": -1
            }

        return {
            "grade": "NEUTRAL",
            "score": 2
        }
