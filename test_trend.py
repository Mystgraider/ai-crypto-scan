from engines.trend_engine import (
    TrendEngine
)

engine = TrendEngine()

result = engine.analyze(

    price=105,

    ema20=102,

    ema50=100
)

print(result)
