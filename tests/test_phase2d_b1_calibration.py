from reports.calibration_engine import CalibrationEngine


def signal(status, ai=None, confidence=None, grade="A", realized_r=None):
    return {
        "status": status,
        "ai_rank_score": "" if ai is None else str(ai),
        "confidence": "" if confidence is None else str(confidence),
        "grade": grade,
        "realized_r": "" if realized_r is None else str(realized_r),
    }


def test_calibration_uses_only_resolved_and_excludes_expired():
    rows = [
        signal("TP3_HIT", 92, 88, realized_r=2.0),
        signal("SL_HIT", 92, 88, realized_r=-1.0),
        signal("EXPIRED", 92, 88, realized_r=""),
        signal("OPEN", 92, 88, realized_r=""),
    ]

    report = CalibrationEngine(rows, min_sample=2).compute()

    assert report["scope"]["resolved_signals"] == 2
    assert report["scope"]["expired_signals"] == 1
    assert report["scope"]["ai_calibration_samples"] == 2
    bucket = report["ai_rank_score"]["90-100"]
    assert bucket["n"] == 2
    assert bucket["wins"] == 1
    assert bucket["win_rate_pct"] == 50.0
    assert bucket["avg_r"] == 0.5


def test_legacy_rows_without_ai_fields_are_not_reconstructed():
    rows = [
        signal("TP3_HIT", None, None, realized_r=2.0),
        signal("SL_HIT", 95, 90, realized_r=-1.0),
    ]

    report = CalibrationEngine(rows, min_sample=1).compute()

    assert report["scope"]["ai_calibration_samples"] == 1
    assert report["scope"]["confidence_calibration_samples"] == 1
    assert report["ai_rank_score"]["90-100"]["n"] == 1
    assert report["ai_rank_score"]["90-100"]["wins"] == 0


def test_confidence_reports_observed_wr_and_diagnostic_calibration_error():
    rows = [
        signal("TP3_HIT", 80, 80, realized_r=1.0),
        signal("SL_HIT", 80, 80, realized_r=-1.0),
    ]

    report = CalibrationEngine(rows, min_sample=2).compute()
    bucket = report["confidence"]["80-89"]

    assert bucket["n"] == 2
    assert bucket["mean_predicted_pct"] == 80.0
    assert bucket["win_rate_pct"] == 50.0
    assert bucket["calibration_error_pct"] == 30.0
    assert bucket["reliable"] is True


def test_grade_stats_can_use_legacy_resolved_history():
    rows = [
        signal("TP3_HIT", None, None, grade="S", realized_r=2.0),
        signal("SL_HIT", None, None, grade="S", realized_r=-1.0),
    ]

    report = CalibrationEngine(rows, min_sample=1).compute()
    assert report["grade"]["S"]["n"] == 2
    assert report["grade"]["S"]["win_rate_pct"] == 50.0


def test_summary_flags_insufficient_samples_and_blocks_tuning():
    rows = [signal("TP3_HIT", 95, 95, realized_r=2.0)]

    result = CalibrationEngine(rows, min_sample=20).summary()

    assert "insufficient AI rank samples" in result["warnings"]
    assert "insufficient confidence samples" in result["warnings"]
    assert result["ready_for_tuning"] is False
