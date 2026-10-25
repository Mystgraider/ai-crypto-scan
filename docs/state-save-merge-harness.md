# State-save merge/conflict harness (research only)

## Purpose

This change adds a small, deterministic three-way text-merge primitive and tests for interleaved state writers. It is a research step toward safe state-save retries, not a completed workflow fix.

## Behavior under test

Given a common base version, the current remote version, and a job's generated version:

- Non-overlapping edits are merged so both writers' changes survive.
- Identical edits are accepted.
- Overlapping edits raise an explicit conflict instead of silently replacing either writer's changes.
- Unrelated changes present in the latest remote content are preserved.

The implementation delegates the merge to `git merge-file`; it does not invent CSV row keys or guess which signal status should win.

## Important limitations

- The helper is **not yet wired into** `.github/workflows/scanner.yml`.
- These unit tests prove the merge primitive's behavior only; they do not prove end-to-end workflow serialization, push retries, or durable OI snapshot persistence.
- A production integration must capture the true common-base content before the job mutates state, fetch latest `main`, merge each generated state file against that base, and fail safely on conflicts.
- The integration must account for `workflow_dispatch` runs that may scan a non-main ref; it must not assume `GITHUB_SHA` is always the correct base for production state.
- Conflict retries must reapply only the intended changes and must not repeat scanner execution or Telegram alerts.
- Do not merge this PR or enable OI snapshot persistence based on these tests alone.

## Scope guardrails

No scanner/OI logic, strategy thresholds, grading, signal qualification, TP/SL rules, alerts, or workflow behavior is changed here. No live exchange requests or production scanner runs were performed.
