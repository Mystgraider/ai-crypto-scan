from reports.calibration_report import CalibrationReport


def signal(status, ai=None, confidence=None, grade="A", realized_r=None):
    return {
        "status": status,
        "ai_rank_score": "" if ai is None else str(ai),
        "confidence": "" if confidence is None else str(confidence),
        "grade": grade,
        "realized_r": "" if realized_r is None else str(realized_r),
    }


def test_report_identifies_reliable_strongest_and_weakest_buckets():
    rows = []
    rows.extend(signal("TP3_HIT", 95, 90, grade="S", realized_r=2.0) for _ in range(20))
    rows.extend(signal("SL_HIT", 95, 90, grade="S", realized_r=-1.0) for _ in range(20))
    rows.extend(signal("SL_HIT", 65, 60, grade="D", realized_r=-1.0) for _ in range(20))

    result = CalibrationReport(rows, min_sample=20).compute()

    assert result["interpretation"]["ai_rank_score"]["reliable"] is True
    assert result["interpretation"]["ai_rank_score"]["strongest"]["bucket"] == "90-100"
    assert result["interpretation"]["ai_rank_score"]["weakest"]["bucket"] == "60-69"
    assert result["interpretation"]["grade"]["strongest"]["grade"] == "S"
    assert result["ready_for_tuning"] is True


def test_confidence_interpretation_is_diagnostic_only():
    rows = []
    rows.extend(signal("TP3_HIT", 80, 80, realized_r=1.0) for _ in range(20))
    rows.extend(signal("SL_HIT", 80, 80, realized_r=-1.0) for _ in range(20))

    result = CalibrationReport(rows, min_sample=20).compute()
    confidence = result["interpretation"]["confidence"]

    assert confidence["most_overconfident"]["bucket"] == "80-89"
    assert "diagnostic only" in confidence["note"]
    assert "REPORT_ONLY" in result["guardrail"]


def test_report_blocks_tuning_when_samples_are_insufficient():
    rows = [signal("TP3_HIT", 95, 95, grade="A", realized_r=2.0)]

    result = CalibrationReport(rows, min_sample=20).compute()

    assert result["ready_for_tuning"] is False
    assert "insufficient AI rank samples" in result["warnings"]
    assert "insufficient confidence samples" in result["warnings"]


def test_render_text_contains_all_required_sections():
    rows = [signal("TP3_HIT", 92, 88, grade="A", realized_r=2.0)]

    text = CalibrationReport(rows, min_sample=20).render_text()

    assert "AI Rank Score" in text
    assert "Confidence" in text
    assert "Grade" in text
    assert "Evidence" in text
    assert "Ready for tuning: False" in text
    assert "REPORT_ONLY" in text
