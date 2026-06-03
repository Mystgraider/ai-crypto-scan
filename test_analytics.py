from analytics_engine import AnalyticsEngine

engine = AnalyticsEngine()

wr = engine.win_rate(
    wins=70,
    losses=30
)

pf = engine.profit_factor(
    gross_profit=2500,
    gross_loss=1000
)

exp = engine.expectancy(
    win_rate=wr,
    avg_win=2.0,
    avg_loss=1.0
)

print("WR:", wr)
print("PF:", pf)
print("EXP:", exp)
