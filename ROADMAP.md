# AI Crypto Scan — Roadmap

## Current baseline

`main` is the protected strategy baseline. The current system is an automated crypto futures scanner with signal generation, tracking, analytics, AI ranking/confidence, and scheduled reporting.

**Strategy-integrity rule:** roadmap, observability, outcome-accounting, and diagnostics work must not silently change scanner decisions. Any future strategy change must be explicit, isolated, tested, and called out separately.

## Core platform roadmap

| Area | Status | Notes |
|---|---|---|
| Phase 1 — Core scanner | Done | Indicators, trend/quality, Telegram, TP/SL, logging |
| Phase 2 — Tracking | Done | Cooldown and signal lifecycle tracking |
| Phase 3 — Analytics/reporting | Done | Analytics, profit factor, daily reporting |
| Phase 4 — Market-context upgrades | Done in code | BTC filter, multi-timeframe, relative strength and additional market/risk engines are present; old README incorrectly marked this as next |
| Phase 5 — AI layer | Done | AI ranker and confidence engine are present |
| Phase 6 — Dashboard/web analytics | Pending | No dashboard milestone is represented by the current repository tree; treat this as future work, not completed work |

## Phase 2D evidence/calibration program

This is a measurement and hardening track. It is deliberately separate from changing the trading strategy.

| Phase | Status | Purpose |
|---|---|---|
| B0 | Done | Persist AI rank/confidence evidence |
| B1 | Done | Read-only calibration analyzer |
| B2 | Done | Calibration reporting checkpoint |
| C | Done | Evidence-based, report-only tuning advisor |
| D1/D2 | Done | AI attribution evidence logging |
| D3A | Done | Attribution data-sufficiency analysis |
| D3B | Done | Attribution analytics |
| E | Done | TP ladder tests + RRCE TP ladder integration |
| F | Done | Runtime outcome persistence/lifecycle test hardening |
| H.2 | Done | Outcome execution contract tests |
| H.4 | Done | Explicit execution evidence + independent lifecycle state model |
| H.5 | Done + hardened | Canonical execution outcome / trade-R resolver |
| H.6 | Done | Outcome quality and evidence diagnostics |

### H-series boundary

H.4–H.6 do **not** change the trading strategy. They separate market milestones from explicit execution evidence, establish one canonical trade-R calculation path, and expose data-quality diagnostics.

H.6 is the last currently-defined H-series phase. That does **not** mean the entire product is finished: the core roadmap still has the Dashboard/Web Analytics work pending, plus any future explicitly approved features.

## Cleanup / maintenance policy

- Do not keep temporary checkpoint-marker files in the repository root after their phase is accepted.
- Keep phase-specific technical documentation under `docs/`.
- Keep `README.md` focused on the current product and point detailed phase history to this roadmap.
- Do not infer strategy changes from analytics or diagnostics work.
- Before any strategy modification, record the exact intended behavior change and add regression coverage.

## Verification baseline

The repository's `Verify Strategy Integrity` workflow is the primary automated gate for Python compilation and the full test suite. A phase is not considered complete merely because code exists; its tests and CI must pass at the relevant checkpoint.
