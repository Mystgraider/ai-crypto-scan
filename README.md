# Elite Futures Scanner V5

Automated crypto futures signal platform with signal generation, tracking, analytics, AI ranking/confidence, and scheduled reporting.

## Architecture

```text
scanner_v5.py
├── loaders/        market + symbol + OHLCV data
├── indicators/     EMA / RSI / ATR / ADX / ROC / RelVol
├── engines/        trend, quality, RRCE, BTC/context, risk, validation
├── ai/             ranking, confidence, attribution, data sufficiency
├── storage/        signals, cooldown, execution evidence
├── tracker/        lifecycle and outcome tracking
├── reports/        analytics, calibration, canonical outcome, diagnostics
└── alerts/         Telegram delivery
```

`ROADMAP.md` is the source of truth for project phase status and the Phase 2D evidence/calibration track.

## Setup

1. Fork or clone the repository.
2. Add GitHub Actions secrets:
   - `BOT_TOKEN` — Telegram bot token
   - `CHAT_ID` — Telegram chat/channel ID
3. Enable GitHub Actions.
4. The scanner workflow runs on its configured schedule.

## Signal contract

Signals contain a direction, score/grade, executable entry, structural stop loss, and staged TP1/TP2/TP3 levels. Outcome tracking distinguishes market price milestones from explicit execution evidence.

## Strategy-integrity boundary

The current Phase 2D work is primarily evidence, analytics, outcome-accounting, diagnostics, and test hardening. It does **not** silently retune the trading strategy.

The following are strategy-sensitive and require an explicit, separately reviewed change:

- scanner entry/filter decisions
- ranking logic and AI weights
- confidence formula
- score/grade thresholds
- position sizing
- risk/SL/TP decision logic
- lifecycle transition rules

See `ROADMAP.md` for the audited roadmap and remaining product work.

## Verification

Use the repository `Verify Strategy Integrity` workflow as the primary CI gate. Phase work is considered complete only after the relevant tests and integrity checks pass.
