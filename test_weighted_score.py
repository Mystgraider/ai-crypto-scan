from weighted_score_engine import (
    WeightedScoreEngine
)

engine = WeightedScoreEngine()

score = engine.calculate(

    trend_score=90,

    volume_score=80,

    oi_score=85,

    funding_score=75,

    regime_score=95
)

print(
    "Score:",
    score
)

print(
    "Grade:",
    engine.grade(
        score
    )
)
