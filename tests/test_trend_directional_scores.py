from engines.trend_engine import TrendEngine


def test_directional_scores_are_independent():
    engine = TrendEngine()
    scores = engine.directional_scores(
        price=110, ema20=105, ema50=100, adx=30, roc=2,
        macd=3, macd_sig=2, macd_hist=1, stoch_k=55, bb_pct_b=0.5,
    )
    assert scores["LONG"] != scores["SHORT"]
    assert scores["LONG"] > scores["SHORT"]


def test_analyze_uses_matching_directional_score():
    engine = TrendEngine()
    scores = engine.directional_scores(
        price=90, ema20=95, ema50=100, adx=30, roc=-2,
        macd=-3, macd_sig=-2, macd_hist=-1, stoch_k=45, bb_pct_b=0.5,
    )
    confirmed = engine.analyze(
        price=90, ema20=95, ema50=100, adx=30, roc=-2,
        macd=-3, macd_sig=-2, macd_hist=-1, stoch_k=45,
        stoch_d=50, bb_pct_b=0.5,
    )
    assert confirmed["direction"] == "SHORT"
    assert confirmed["score"] == scores["SHORT"]
