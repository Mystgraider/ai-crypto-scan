from ai.data_sufficiency import analyze_data_sufficiency


def _attr():
    return {
        "attribution_version": "2D-D1",
        "components": {"trend": 28.0},
        "ai_rank_raw": 64.69,
        "ai_rank_score": 64.69,
    }


def test_insufficient_dataset_is_not_ready():
    signals = [{"ai_attribution": _attr(), "status": "TP3_HIT"} for _ in range(20)]
    result = analyze_data_sufficiency(signals)
    assert result["attributed_records"] == 20
    assert result["winner_records"] == 20
    assert result["loser_records"] == 0
    assert result["ready"] is False


def test_ready_dataset_requires_minimum_attribution_and_both_outcomes():
    signals = (
        [{"ai_attribution": _attr(), "status": "TP3_HIT"} for _ in range(10)]
        + [{"ai_attribution": _attr(), "status": "SL_HIT"} for _ in range(10)]
        + [{"ai_attribution": _attr(), "status": "OPEN"} for _ in range(5)]
    )
    result = analyze_data_sufficiency(signals)
    assert result["total_records"] == 25
    assert result["attributed_records"] == 25
    assert result["completed_attributed_records"] == 20
    assert result["winner_records"] == 10
    assert result["loser_records"] == 10
    assert result["attribution_coverage"] == 1.0
    assert result["ready"] is True


def test_missing_or_malformed_attribution_is_excluded():
    signals = [
        {"ai_attribution": _attr(), "status": "TP3_HIT"},
        {"ai_attribution": "", "status": "SL_HIT"},
        {"ai_attribution": {"components": {}}, "status": "TP3_HIT"},
    ]
    result = analyze_data_sufficiency(signals, min_attributed_records=1)
    assert result["total_records"] == 3
    assert result["attributed_records"] == 1
    assert result["missing_attribution_records"] == 2
    assert result["attribution_coverage"] == 0.3333
    assert result["ready"] is False
