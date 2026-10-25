from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "scanner.yml"
DESIGN_PATH = REPO_ROOT / "docs" / "scanner-state-save-concurrency-audit.md"


def test_audit_document_records_known_shared_state_writer_risk():
    document = DESIGN_PATH.read_text(encoding="utf-8")
    assert "daily_report" in document
    assert "serialize all writers of shared state" in document
    assert "interleaved writers" in document
    assert "No concurrency configuration was changed" in document


def test_current_workflow_scan_and_daily_report_save_contract_is_explicit():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    scan_job, daily_report = workflow.split("  daily_report:", maxsplit=1)

    # Baseline audit: the scan job has job-level concurrency, while the
    # separate daily_report job does not. This is documented as a risk,
    # not represented as a completed concurrency fix.
    assert "concurrency:" in scan_job
    assert "group: elite-scanner" in scan_job
    assert "concurrency:" not in daily_report

    assert "git fetch origin main" in scan_job
    assert "git reset --mixed origin/main" in scan_job
    assert "git add storage/signals.csv" in scan_job
    assert "git commit -m \"chore: update scanner state\"" in scan_job
    assert "git push origin HEAD:main" in scan_job

    assert "git fetch origin main" in daily_report
    assert "git reset --mixed origin/main" in daily_report
    assert "git add storage/signals.csv || true" in daily_report
    assert "git commit -m \"chore: update signal statuses [skip ci]\"" in daily_report
    assert "git push origin HEAD:main" in daily_report
