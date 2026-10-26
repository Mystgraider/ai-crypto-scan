# Multi-window Indicator Counterfactual — 2026-10-26

## Scope and provenance

Research-only retrospective analysis of `storage/signals.csv` from `main`, retrieved 2026-10-26. The file contained 3,560 timestamped signal rows through 2026-10-26T01:38:51.128659+00:00.

Candidate: `direction == SHORT AND RSI >= 50 AND ADX >= 20`.
Baseline: all saved SHORT signals.
Rows were sorted chronologically and split into five contiguous, approximately equal-row windows (712 rows each). Window durations differ because signal frequency varies.

This is an observed-signal association, **not** a true counterfactual scanner replay. Signals rejected before logging are unavailable, so the analysis cannot establish what would have happened if the candidate had blocked signals in real time.

## Aggregate results across all 3,560 saved rows

| Population | Signals | TP3 | SL | Other statuses | TP3 / (TP3 + SL) | Share of SHORT signals |
|---|---:|---:|---:|---:|---:|---:|
| SHORT baseline | 1,699 | 485 | 793 | 421 | 37.95% | 100% |
| SHORT + RSI >= 50 + ADX >= 20 | 273 | 105 | 102 | 66 | 50.72% | 16.07% |

Candidate's TP3 rate among TP3/SL-resolved rows is +12.77 percentage points vs SHORT baseline overall. It selected 16.07% of saved SHORT signals, so it would exclude most SHORT signals if applied as a gate. This is not a production performance estimate.

## Five chronological windows

TP3 rate below means TP3 / (TP3 + SL) only. Other statuses are shown separately because expired/open/partial-target rows must not be silently counted as losses or wins.

| Window | UTC range | SHORT N | SHORT TP3/SL | SHORT TP3 rate | Candidate N | Candidate TP3/SL | Candidate TP3 rate | Difference | Candidate other statuses |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | Jun 19 – Oct 6 | 227 | 65 / 144 | 31.10% | 35 | 16 / 17 | 48.48% | +17.38 pp | 2 expired |
| 2 | Oct 6 – Oct 11 | 334 | 124 / 174 | 41.61% | 45 | 11 / 30 | 26.83% | -14.78 pp | 4 expired |
| 3 | Oct 11 – Oct 16 | 328 | 108 / 144 | 42.86% | 62 | 18 / 17 | 51.43% | +8.57 pp | 27 other, mainly expired/open |
| 4 | Oct 16 – Oct 21 | 316 | 85 / 175 | 32.69% | 58 | 23 / 27 | 46.00% | +13.31 pp | 8 expired |
| 5 | Oct 21 – Oct 26 | 494 | 103 / 156 | 39.77% | 73 | 37 / 11 | 77.08% | +37.31 pp | 25 other, including 24 open and 1 expired |

The candidate beat the SHORT baseline in 4 of 5 windows, but materially underperformed in Window 2. Window 5 has substantial unresolved/open outcomes; its 77.08% resolved TP3 rate is preliminary and can change as trades resolve.

## Realized-R data quality note

Among rows with a nonblank `realized_r`, the arithmetic mean was 1.0120 for SHORT baseline (1,261 nonblank rows) and 1.5909 for the candidate (207 nonblank rows). This is **descriptive only**, not an expectancy comparison: 438 SHORT rows and 66 candidate rows had blank realized-R values, and missingness is related to trade status/outcome. Do not use these means to approve a strategy.

## Decision

**Do not enable this filter in production yet.** The aggregate association is encouraging, but one chronological window is clearly negative, the newest window has many unresolved trades, and this logged-row analysis cannot replay rejected candidates or prove execution-aware expectancy.

Before any production change:
1. Preserve a frozen CSV snapshot and rerun from that exact file.
2. Re-evaluate with pre-registered thresholds on later, untouched data after open trades resolve.
3. Calculate realized-R/expectancy with a consistent policy for every status, partial targets, fees, and execution.
4. Replay the actual scanner pipeline in an isolated research harness, including candidates currently rejected before logging.
