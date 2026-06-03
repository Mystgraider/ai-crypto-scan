from market_regime import MarketRegimeEngine

engine = MarketRegimeEngine()

result = engine.detect(
    ema20=105,
    ema50=100,
    atr_pct=1.8,
    rel_volume=1.3
)

print(result)
