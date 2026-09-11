from reports.tuning_advisor import TuningAdvisor


def _rows_for_bucket(bucket_score, count, realized_r, confidence=80):
    return [
        {
            "status": "TP3_HIT" if realized_r > 0 else "SL_HIT",
            "ai_rank_score": bucket_score,
            "confidence": confidence,
            "realized_r": realized_r,
            "grade": "A",
        }
        for _ in range(count)
    ]


def test_insufficient_evidence_blocks_tuning():
    rows = _rows_for_bucket(80, 10, 1.0)
    result = TuningAdvisor(signals=rows).compute()

    assert result["ready"] is False
    assert result["recommendation"]["action"] == "NO_TUNING"
    assert result["attribution"]["available"] is False
    assert "insufficient AI rank samples" in result["warnings"]
    assert "insufficient confidence samples" in result["warnings"]


def test_reliable_separation_requests_investigation_without_mutation():
    rows = _rows_for_bucket(90, 20, 1.0) + _rows_for_bucket(60, 20, -1.0)
    before = [row.copy() for row in rows]

    result = TuningAdvisor(signals=rows).compute()

    assert result["ready"] is True
    assert result["recommendation"]["action"] == "INVESTIGATE_COMPONENTS"
    assert result["comparison"]["net_r_gap"] >= 2.0
    assert rows == before
    assert "REPORT_ONLY" in result["guardrail"]


def test_reliable_but_close_buckets_do_not_trigger_tuning():
    rows = _rows_for_bucket(80, 20, 1.0) + _rows_for_bucket(60, 20, 0.9)
    result = TuningAdvisor(signals=rows).compute()

    assert result["ready"] is True
    assert result["recommendation"]["action"] == "NO_TUNING"
    assert result["comparison"]["net_r_gap"] < 2.0
    assert result["comparison"]["win_rate_gap_pct"] < 10.0


def test_component_attribution_is_explicitly_unavailable():
    rows = _rows_for_bucket(90, 20, 1.0) + _rows_for_bucket(60, 20, -1.0)
    result = TuningAdvisor(signals=rows).compute()

    assert result["attribution"] == {
        "available": False,
        "note": "Aggregate score outcomes are logged, but per-component score contributions are not stored.",
    }
