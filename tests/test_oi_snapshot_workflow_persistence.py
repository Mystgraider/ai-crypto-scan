from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "scanner.yml"


def test_scanner_workflow_persists_oi_snapshot_file_when_present():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    scan_job = workflow.split("  daily_report:", maxsplit=1)[0]
    save_step = scan_job.split("      - name: Save generated scanner state", maxsplit=1)[1]

    assert "if: always()" in save_step
    assert 'if [ -f storage/oi_snapshots.jsonl ]; then' in save_step
    assert "git add storage/oi_snapshots.jsonl" in save_step
    assert "git commit -m \"chore: update scanner state\"" in save_step
    assert "git push origin HEAD:main" in save_step


def test_oi_snapshot_is_optional_and_does_not_replace_existing_state_staging():
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    scan_job = workflow.split("  daily_report:", maxsplit=1)[0]
    save_step = scan_job.split("      - name: Save generated scanner state", maxsplit=1)[1]

    existing_state_staging = (
        "git add storage/signals.csv storage/cooldown.json "
        "storage/circuit_breaker.json storage/rrce_watchlist.json "
        "storage/scan_debug_log.jsonl storage/symbol_trace_log.jsonl || true"
    )
    assert existing_state_staging in save_step
    assert save_step.index(existing_state_staging) < save_step.index(
        'if [ -f storage/oi_snapshots.jsonl ]; then'
    )
