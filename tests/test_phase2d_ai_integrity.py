from ai.signal_ranker import AISignalRanker
from ai.confidence_engine import ConfidenceEngine


def candidate(**overrides):
    base = {
        "symbol": "BTC/USDT",
        "direction": "LONG",
        "trend_score": 80,
        "quality_score": 80,
        "rs_score": 50,
        "rr": 2.0,
        "sr_bonus": 0,
        "grade": "B",
        "oi_signal": "NEUTRAL",
        "funding_pct_raw": 0,
        "mtf_status": "ALLOWED",
        "composite": 75,
    }
    base.update(overrides)
    return base


def test_ai_rank_score_is_bounded_and_separate_from_trading_score():
    result = AISignalRanker().rank([
        candidate(
            trend_score=100,
            quality_score=100,
            rs_score=100,
            rr=5,
            oi_signal="CONFIRMED",
            sr_bonus=15,
            mtf_status="CONFIRMED_STRONG",
            grade="S",
        )
    ])[0]

    assert 0.0 <= result["ai_rank_score"] <= 100.0
    assert result["ai_composite"] == result["ai_rank_score"]
    assert result["composite"] == 75
    assert result["ai_rank_score"] != result["composite"]


def test_ai_rank_raw_is_retained_for_auditability():
    result = AISignalRanker().rank([candidate()])[0]
    assert "ai_rank_raw" in result
    assert result["ai_rank_score"] == result["ai_composite"]


def test_ai_rank_orders_candidates_deterministically():
    results = AISignalRanker().rank([
        candidate(symbol="A", trend_score=70),
        candidate(symbol="B", trend_score=90),
    ])
    assert [x["symbol"] for x in results] == ["B", "A"]


def test_confidence_is_bounded_and_not_affected_by_out_of_range_wr():
    engine = ConfidenceEngine()
    assert 0.0 <= engine.estimate(90, 90, 200) <= 100.0
    assert 0.0 <= engine.estimate(10, 10, -50) <= 100.0


def test_confidence_is_heuristic_not_a_raw_win_rate_echo():
    engine = ConfidenceEngine()
    assert engine.estimate(80, 80, 50) == 80.0
    assert engine.estimate(80, 80, 100) == 90.0
