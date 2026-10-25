# Scanner state-save concurrency audit (research only)

## Scope

This document records the current workflow's state-save behavior and defines acceptance criteria for a later implementation. It does not change scanner execution, state-save behavior, OI logic, or strategy.

## Observed workflow behavior

- The `scan` job runs every five minutes and has job-level concurrency group `elite-scanner` with `cancel-in-progress: false`.
- The `daily_report` job also writes `storage/signals.csv`, but it has no matching concurrency group.
- Both jobs fetch `origin main`, run `git reset --mixed origin/main`, stage selected state, commit, and push to `main`.
- The scan save step optionally stages `storage/oi_snapshots.jsonl` if it exists on the checked-out working tree.
- The daily report save step stages `storage/signals.csv` only.

## Risk statement

**Confirmed workflow configuration gap:** the two jobs that can write `signals.csv` do not share a common serialization mechanism. The scan job's concurrency setting does not serialize the separate `daily_report` job.

This is a race-risk finding from workflow configuration, not evidence that a data-loss incident has occurred. The fetch/reset sequence helps avoid stale-base non-fast-forward pushes, but by itself does not guarantee that two writers cannot overwrite each other's logically independent updates to the same file.

## Required acceptance criteria for a future fix

1. Serialize all writers of shared state without allowing frequent five-minute scans to indefinitely supersede the daily report.
2. Preserve both scan-generated state and daily-report status updates when they overlap.
3. On a push conflict, fail safely or retry from the latest `main` while reapplying only the intended state changes; never silently discard another writer's updates.
4. Keep OI snapshot writes optional until an approved caller exists.
5. Keep snapshot records unit-safe and timestamped; do not treat missing history as neutral/available.
6. Add deterministic tests for interleaved writers, push rejection/retry, preservation of unrelated file changes, and optional snapshot persistence.
7. Verify that the proposed workflow does not trigger an uncontrolled workflow loop or introduce concurrent scanner executions.

## Deliberately not done

- No concurrency configuration was changed in this research PR.
- No scanner, OI engine, thresholds, signal qualification, TP/SL rules, or Telegram behavior changed.
- No live exchange requests or production scanner run were performed.
- No merge or production deployment was performed.

## Recommended next design

Do not simply add the same job-level concurrency group to `daily_report` without testing queue semantics: a five-minute scan cadence and GitHub's limited pending-run behavior could cause a pending run to be replaced. Design and test a serialization approach that explicitly protects both writers and preserves updates before enabling it.
