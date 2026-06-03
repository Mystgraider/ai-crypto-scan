class WeightedScoreEngine:

    def calculate(
        self,
        trend_score=0,
        volume_score=0,
        oi_score=0,
        funding_score=0,
        regime_score=0
    ):

        total = (

            trend_score * 0.30 +

            volume_score * 0.20 +

            oi_score * 0.20 +

            funding_score * 0.10 +

            regime_score * 0.20

        )

        return round(
            total,
            2
        )

    def grade(
        self,
        score
    ):

        if score >= 90:
            return "S"

        if score >= 80:
            return "A"

        if score >= 70:
            return "B"

        if score >= 60:
            return "C"

        return "D"
