from reports.outcome_quality import analyze_outcome_quality

BASE = {"direction": "LONG", "entry": 100.0, "initial_sl": 98.0}


def test_counts_canonical_sources_and_execution_quality():
    signals = [
        {**BASE, "status": "TP3_HIT", "realized_r": 2.0},
        {**BASE, "status": "SL_HIT", "exit_price": 98.0},
        {**BASE, "status": "TP3_HIT", "tp1_qty_pct": 50, "tp1_exit_price": 104, "tp1_realized_r": 2, "tp1_executed_at": "2026-09-13T00:00:00Z"},
        {**BASE, "status": "EXPIRED"},
        {**BASE, "status": "OPEN"},
    ]
    report = analyze_outcome_quality(signals)
    assert report["total_signals"] == 5
    assert report["terminal_signals"] == 4
    assert report["resolved_signals"] == 2
    assert report["expired_signals"] == 1
    assert report["unresolved_resolved_statuses"] == 1
    assert report["outcome_source_counts"]["terminal_realized_r"] == 1
    assert report["outcome_source_counts"]["legacy_calculation"] == 1
    assert report["outcome_source_counts"]["unresolved"] == 3
    assert report["execution_evidence_counts"] == {"complete": 0, "incomplete_or_invalid": 1, "none": 4}


def test_complete_explicit_execution_is_reported_as_complete():
    signal = {**BASE, "status": "TP3_HIT", "tp1_qty_pct": 100, "tp1_exit_price": 104, "tp1_realized_r": 2, "tp1_executed_at": "2026-09-13T00:00:00Z", "remaining_position_pct": 0}
    report = analyze_outcome_quality([signal])
    assert report["resolved_signals"] == 1
    assert report["outcome_source_counts"]["explicit_execution"] == 1
    assert report["execution_evidence_counts"]["complete"] == 1


def test_tp_hit_fields_never_count_as_execution():
    signal = {**BASE, "status": "TP3_HIT", "tp1_hit_at": "2026-09-13T00:00:00Z", "tp2_hit_at": "2026-09-13T00:01:00Z", "tp3_hit_at": "2026-09-13T00:02:00Z", "realized_r": 3.0}
    report = analyze_outcome_quality([signal])
    assert report["execution_evidence_counts"]["none"] == 1
    assert report["outcome_source_counts"]["terminal_realized_r"] == 1


def test_incomplete_execution_remains_diagnostic_when_terminal_fallback_resolves():
    signal = {**BASE, "status": "TP3_HIT", "tp1_qty_pct": 50, "tp1_exit_price": 104, "realized_r": 2.0}
    report = analyze_outcome_quality([signal])
    assert report["resolved_signals"] == 1
    assert report["outcome_source_counts"]["terminal_realized_r"] == 1
    assert report["execution_evidence_counts"]["incomplete_or_invalid"] == 1


def test_over_100_percent_execution_is_not_complete():
    signal = {**BASE, "status": "TP3_HIT", "tp1_qty_pct": 60, "tp1_exit_price": 104, "tp1_realized_r": 2, "tp1_executed_at": "2026-09-13T00:00:00Z", "tp2_qty_pct": 50, "tp2_exit_price": 106, "tp2_realized_r": 3, "tp2_executed_at": "2026-09-13T00:01:00Z"}
    report = analyze_outcome_quality([signal])
    assert report["execution_evidence_counts"]["incomplete_or_invalid"] == 1
    assert report["outcome_source_counts"]["unresolved"] == 1
    assert report["unresolved_resolved_statuses"] == 1


def test_remaining_zero_can_complete_full_accounting():
    signal = {**BASE, "status": "SL_HIT", "tp1_qty_pct": 50, "tp1_exit_price": 104, "tp1_realized_r": 2, "tp1_executed_at": "2026-09-13T00:00:00Z", "tp2_qty_pct": 50, "tp2_exit_price": 106, "tp2_realized_r": 3, "tp2_executed_at": "2026-09-13T00:01:00Z", "remaining_position_pct": 0}
    report = analyze_outcome_quality([signal])
    assert report["resolved_signals"] == 1
    assert report["outcome_source_counts"]["explicit_execution"] == 1
    assert report["execution_evidence_counts"]["complete"] == 1


def test_short_legacy_calculation_is_resolved():
    signal = {"direction": "SHORT", "entry": 100.0, "initial_sl": 102.0, "status": "SL_HIT", "exit_price": 102.0}
    report = analyze_outcome_quality([signal])
    assert report["resolved_signals"] == 1
    assert report["outcome_source_counts"]["legacy_calculation"] == 1


def test_coverage_metrics_and_empty_input_are_deterministic():
    report = analyze_outcome_quality([{**BASE, "status": "TP3_HIT", "realized_r": 2.0}, {**BASE, "status": "EXPIRED"}, {**BASE, "status": "OPEN"}])
    assert report["coverage_pct"]["terminal"] == 66.67
    assert report["coverage_pct"]["resolved"] == 100.0
    assert report["coverage_pct"]["expired"] == 33.33
    assert report["coverage_pct"]["terminal_realized_r"] == 33.33
    assert report["coverage_pct"]["unresolved"] == 66.67
    empty = analyze_outcome_quality([])
    assert empty["coverage_pct"]["terminal"] == 0.0
    assert empty["outcome_source_counts"] == {"explicit_execution": 0, "legacy_calculation": 0, "terminal_realized_r": 0, "unresolved": 0}
    assert empty["execution_evidence_counts"] == {"complete": 0, "incomplete_or_invalid": 0, "none": 0}


def test_expired_can_have_execution_evidence_but_is_not_a_resolved_lifecycle_outcome():
    signal = {
        **BASE,
        "status": "EXPIRED",
        "tp1_qty_pct": 100,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T00:00:00Z",
        "remaining_position_pct": 0,
    }
    report = analyze_outcome_quality([signal])
    assert report["expired_signals"] == 1
    assert report["resolved_signals"] == 0
    assert report["execution_evidence_counts"]["complete"] == 1
    assert report["outcome_source_counts"]["explicit_execution"] == 1


def test_open_can_have_complete_execution_evidence_without_being_lifecycle_resolved():
    signal = {
        **BASE,
        "status": "OPEN",
        "tp1_qty_pct": 100,
        "tp1_exit_price": 104,
        "tp1_realized_r": 2,
        "tp1_executed_at": "2026-09-13T00:00:00Z",
        "remaining_position_pct": 0,
    }
    report = analyze_outcome_quality([signal])
    assert report["resolved_signals"] == 0
    assert report["terminal_signals"] == 0
    assert report["execution_evidence_counts"]["complete"] == 1
    assert report["outcome_source_counts"]["explicit_execution"] == 1
