from weighted_score_engine import (
    WeightedScoreEngine
)


class SignalEngine:

    def __init__(self):

        self.score_engine = (
            WeightedScoreEngine()
        )

    def generate(

        self,

        trend_score,

        volume_score,

        oi_score,

        funding_score,

        regime_score,

        direction

    ):

        score = (
            self.score_engine.calculate(

                trend_score=
                trend_score,

                volume_score=
                volume_score,

                oi_score=
                oi_score,

                funding_score=
                funding_score,

                regime_score=
                regime_score
            )
        )

        grade = (
            self.score_engine.grade(
                score
            )
        )

        if score >= 80:

            return {

                "signal": direction,

                "score": score,

                "grade": grade
            }

        return {

            "signal": "NO_TRADE",

            "score": score,

            "grade": grade
        }
