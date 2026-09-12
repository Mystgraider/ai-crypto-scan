from ai.attribution_analytics import analyze_attribution


def _attr(**components):
    base = {
        "trend": 20.0,
        "quality": 10.0,
        "rs": 5.0,
        "oi": 2.0,
        "rr": 1.0,
        "sr": 0.5,
        "category": 1.0,
    }
    base.update(components)
    return {
        "attribution_version": "2D-D1",
        "components": base,
        "ai_rank_raw": 39.5,
        "ai_rank_score": 39.5,
    }


def test_winner_and_loser_component_averages_and_differences():
    signals = [
        {"ai_attribution": _attr(trend=30), "status": "TP3_HIT"},
        {"ai_attribution": _attr(trend=40), "status": "TP3_HIT"},
        {"ai_attribution": _attr(trend=10), "status": "SL_HIT"},
        {"ai_attribution": _attr(trend=20), "status": "SL_HIT"},
    ]
    result = analyze_attribution(signals, min_attributed_records=1)
    assert result["winner_averages"]["trend"] == 35.0
    assert result["loser_averages"]["trend"] == 15.0
    assert result["winner_minus_loser"]["trend"] == 20.0
    assert result["winner_sample"] == 2
    assert result["loser_sample"] == 2


def test_insufficient_evidence_is_explicit():
    signals = [
        {"ai_attribution": _attr(trend=50), "status": "TP3_HIT"},
        {"ai_attribution": _attr(trend=10), "status": "SL_HIT"},
    ]
    result = analyze_attribution(signals)
    assert result["ready"] is False
    assert result["evidence_level"] == "insufficient"


def test_missing_attribution_is_not_analyzed():
    signals = [
        {"ai_attribution": _attr(trend=30), "status": "TP3_HIT"},
        {"ai_attribution": None, "status": "SL_HIT"},
        {"ai_attribution": {"components": {}}, "status": "SL_HIT"},
    ]
    result = analyze_attribution(signals, min_attributed_records=1)
    assert result["winner_sample"] == 1
    assert result["loser_sample"] == 0
    assert result["winner_minus_loser"]["trend"] is None
    assert result["sufficiency"]["missing_attribution_records"] == 2
