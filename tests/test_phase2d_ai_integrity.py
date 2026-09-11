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


def test_ai_rank_does_not_collapse_strong_candidates_at_100():
    results = AISignalRanker().rank([
        candidate(symbol="A", trend_score=100, quality_score=100, rs_score=100, rr=5, sr_bonus=15),
        candidate(symbol="B", trend_score=99, quality_score=99, rs_score=99, rr=5, sr_bonus=15),
    ])
    assert results[0]["symbol"] == "A"
    assert results[0]["ai_rank_score"] > results[1]["ai_rank_score"]
    assert results[0]["ai_rank_score"] <= 100.0


def test_ai_rank_normalizes_out_of_range_components():
    normal = AISignalRanker().rank([candidate()])[0]
    extreme = AISignalRanker().rank([
        candidate(trend_score=1000, quality_score=1000, rs_score=1000, rr=100, sr_bonus=100)
    ])[0]
    assert extreme["ai_rank_score"] <= 100.0
    assert extreme["ai_rank_raw"] <= 100.0
    assert normal["composite"] == extreme["composite"] == 75


def test_ai_rank_handles_negative_rr_without_bonus():
    positive = AISignalRanker().rank([candidate(rr=0)])[0]
    negative = AISignalRanker().rank([candidate(rr=-10)])[0]
    assert negative["ai_rank_score"] == positive["ai_rank_score"]


def test_confidence_is_bounded_and_not_affected_by_out_of_range_wr():
    engine = ConfidenceEngine()
    assert 0.0 <= engine.estimate(90, 90, 200) <= 100.0
    assert 0.0 <= engine.estimate(10, 10, -50) <= 100.0


def test_confidence_is_heuristic_not_a_raw_win_rate_echo():
    engine = ConfidenceEngine()
    assert engine.estimate(80, 80, 50) == 80.0
    assert engine.estimate(80, 80, 100) == 90.0
