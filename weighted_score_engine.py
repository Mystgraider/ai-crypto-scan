class WeightedScoreEngine:

    def normalize(
        self,
        value,
        minimum,
        maximum
    ):

        if maximum <= minimum:
            return 0

        value = max(
            minimum,
            min(
                value,
                maximum
            )
        )

        return (
            (
                value - minimum
            )
            /
            (
                maximum - minimum
            )
        ) * 100

    def calculate(

        self,

        trend_score,

        volume_score,

        oi_score,

        funding_score,

        regime_score

    ):

        final_score = (

            trend_score * 0.30 +

            volume_score * 0.20 +

            oi_score * 0.20 +

            funding_score * 0.10 +

            regime_score * 0.20

        )

        return round(
            final_score,
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
