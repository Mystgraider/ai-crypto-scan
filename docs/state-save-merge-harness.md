# State-save merge/conflict harness (research only)

## Purpose

This change adds a deterministic, line-based three-way text-merge primitive and tests for interleaved state writers. It is a research step toward safe state-save retries, not a completed workflow fix.

## Behavior under test

Given a common base version, the current remote version, and a job's generated version:

- Non-overlapping edits are intended to merge so both writers' changes survive.
- Identical edits are accepted.
- Detected overlapping edits raise `StateMergeConflict` rather than silently choosing one version.
- Unrelated changes present in the latest remote content are intended to be preserved.

The implementation uses Python's `difflib.SequenceMatcher` to calculate line-level edits. It does **not** use `git merge-file`, and it does not understand CSV records, signal IDs, or business-level state transitions.

## Important limitations

- The helper is **not yet wired into** `.github/workflows/scanner.yml`.
- Unit tests cover only selected text-merge cases; they do not prove correctness for every edit pattern, CSV state semantics, end-to-end workflow serialization, push retries, or durable OI snapshot persistence.
- A production integration must capture the true common-base content before the job mutates state, fetch latest `main`, merge each generated state file against that base, and fail safely on conflicts.
- The integration must account for `workflow_dispatch` runs that may scan a non-main ref; it must not assume `GITHUB_SHA` is always the correct base for production state.
- Conflict retries must reapply only the intended changes and must not repeat scanner execution or Telegram alerts.
- Do not merge this PR or enable OI snapshot persistence based on these tests alone.

## Scope guardrails

No scanner/OI logic, strategy thresholds, grading, signal qualification, TP/SL rules, alerts, or production workflow behavior is changed here. No live exchange requests or production scanner runs were performed.
