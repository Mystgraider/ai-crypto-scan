from signal_engine import (
    SignalEngine
)

engine = SignalEngine()

result = engine.generate(

    trend_score=90,

    volume_score=85,

    oi_score=90,

    funding_score=80,

    regime_score=90,

    direction="LONG"
)

print(result)
