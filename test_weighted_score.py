from weighted_score_engine import (
    WeightedScoreEngine
)

engine = WeightedScoreEngine()

score = engine.calculate(

    trend_score=90,

    volume_score=80,

    oi_score=85,

    funding_score=70,

    regime_score=90
)

print(score)

print(
    engine.grade(
        score
    )
)
