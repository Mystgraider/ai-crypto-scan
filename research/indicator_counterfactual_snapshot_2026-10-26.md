# Indicator Counterfactual Snapshot — 2026-10-26

## Scope and safety

Research-only snapshot from `storage/signals.csv` on the repository's `main` branch as inspected on 2026-10-26. No production configuration or scanner logic was changed.

The reproducible helper is `research/indicator_counterfactual.py`. It filters saved outcomes; it does **not** replay scanner logic or simulate signals that a gate would have rejected.

## Dataset

- Resolved outcomes included: 3,072 rows with `status` equal to `TP3_HIT` or `SL_HIT`.
- UTC range: 2026-06-20 through 2026-10-25.
- Chronological 70/30 split: train 2,150 rows; test 922 rows (split index follows sorted timestamps; exact counts may vary as the CSV grows).
- This snapshot's prior execution yielded 921 test rows due to a changing live CSV during reads. Re-run the script against a single downloaded CSV snapshot for the canonical count.

## Candidate results from the latest captured run

Latest 30% holdout, approximately 2026-10-18 to 2026-10-25. Outcome rate is TP3 / (TP3 + SL); this is not total win rate or realized expectancy.

| Rule | N | TP3 | SL | TP3 rate |
|---|---:|---:|---:|---:|
| All directions | 921 | 158 | 763 | 17.16% |
| SHORT only | 407 | 131 | 276 | 32.19% |
| SHORT, RSI >= 50 | 135 | 69 | 66 | 51.11% |
| SHORT, ADX >= 20 | 325 | 114 | 211 | 35.08% |
| SHORT, RSI >= 50 and ADX >= 20 | 92 | 57 | 35 | 61.96% |
| SHORT, RSI >= 50, ADX >= 20, rel_volume >= 1 | 71 | 43 | 28 | 60.56% |

Training comparison:

| Rule | N | TP3 | SL | TP3 rate |
|---|---:|---:|---:|---:|
| SHORT only | 869 | 352 | 517 | 40.51% |
| SHORT, RSI >= 50 | 254 | 111 | 143 | 43.70% |
| SHORT, ADX >= 20 | 492 | 192 | 300 | 39.02% |
| SHORT, RSI >= 50 and ADX >= 20 | 115 | 48 | 67 | 41.74% |
| SHORT, RSI >= 50, ADX >= 20, rel_volume >= 1 | 87 | 38 | 49 | 43.68% |

## Interpretation

- The RSI/ADX combination is a **candidate for further validation**, not an approved production rule. Its 61.96% TP3 rate in the holdout is materially above the 41.74% training rate for the same filter; that gap can reflect regime shift, sampling noise, or selection after inspecting results.
- Relative-volume >= 1 did not improve the latest holdout TP3 rate over the RSI/ADX combination and reduced the sample size.
- The CSV's resolved TP3/SL rows omit unresolved and partial-target outcomes. A TP3/SL-only rate can misstate strategy performance.
- These filters are retrospective slices of recorded signals, not true counterfactual replay. The script intentionally labels this limitation.
- Trend/quality gate counterfactuals remain **NOT VERIFIABLE FROM THIS CSV ALONE** because the logged rows do not contain every input needed to reconstruct pre-filter candidates and exact gate decisions.

## Required before any production change

1. Re-run the helper against one frozen CSV snapshot and retain its JSON output.
2. Evaluate several rolling chronological windows with pre-registered thresholds (do not keep tuning on the final holdout).
3. Include all statuses, realized R, trade execution/partial-target rules, and signal coverage.
4. Replay the actual scanner pipeline in an isolated research harness to test trend and quality gates.
5. Keep all candidates research-only until repeatable out-of-sample benefit is demonstrated.

**Decision: no production change recommended from this snapshot.**
