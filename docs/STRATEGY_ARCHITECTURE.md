# Strategy Architecture Contract

## Purpose

This document is the authoritative contract for the scanner's trading decision flow. It is intended to prevent historical V5/V6/V6.9 logic from silently becoming the strategy again.

## Core principle

**BTC is market context, not the signal generator.**

A signal must originate from the individual asset's own setup. BTC may provide regime, risk context, and relative-strength information, but ordinary BTC bullish/bearish direction must not automatically create or suppress an otherwise valid asset setup.

## Direction model

The scanner supports two independent directions:

- `LONG`
- `SHORT`

Each direction must be evaluated as its own candidate. A TrendEngine `NONE` result must not be interpreted as "no possible setup" when the trend gate is disabled. Likewise, a LONG indication from an auxiliary trend model must not prevent the scanner from evaluating a possible SHORT structural setup, and vice versa.

Direction-specific controls are allowed where market mechanics justify them (for example, funding or short resistance), but they must be explicit and testable rather than hidden BTC proxies.

## Decision layers

### 1. Market context

- BTC regime
- broad market safety state
- optional correlation/relative-strength context

This layer provides context and emergency risk controls. It does not manufacture LONG/SHORT signals.

### 2. Asset candidate discovery

The asset itself is evaluated for both directional possibilities when the structural pipeline is responsible for the final decision.

### 3. Structural validation

RRCE is the primary structural validator for the current strategy. A valid candidate requires the configured structural sequence and executable entry conditions.

### 4. Supporting evidence

Supporting engines may include:

- funding
- open interest
- support/resistance
- volume profile
- relative strength
- multi-timeframe evidence

Each engine must be classified explicitly as either a hard gate, soft evidence, ranking input, or observability-only component.

### 5. Risk and execution integrity

The final entry, stop, targets, RR, and live-price validation must come from one authoritative risk/execution path. Multiple engines must not silently overwrite each other's executable levels.

### 6. Ranking

The ranker orders candidates that have already passed eligibility. `ai_rank_score` is **not** a win probability and must not be described as one.

### 7. Final output

The only final trading decisions are:

- `LONG`
- `SHORT`
- `NO TRADE`

## Engine classification rule

Every production engine must have one documented role:

- **HARD_GATE** — failure rejects the candidate.
- **SOFT_EVIDENCE** — contributes evidence but does not reject by itself.
- **RANKING** — affects ordering only.
- **RISK** — calculates/validates executable risk levels.
- **OBSERVABILITY** — records diagnostics only.
- **EXPERIMENTAL** — isolated from production decisions.
- **DEPRECATED** — retained only for historical/reference purposes.

A disabled legacy gate must not remain ambiguous: its configuration and comments must clearly state why it is disabled and what component replaced its responsibility.

## Current intended production roles

| Component | Intended role |
|---|---|
| BTCFilter | MARKET_CONTEXT / safety context |
| RRCE | HARD_GATE / structural validation |
| TrendEngine | SOFT_EVIDENCE / direction evidence when its hard gate is disabled |
| QualityEngine | SOFT_EVIDENCE when hard gate is disabled |
| RelativeStrengthEngine | SOFT_EVIDENCE or RANKING; hard rejection requires explicit validation |
| FundingEngine | HARD_GATE for extreme crowding; supporting evidence otherwise |
| OIEngine | SOFT_EVIDENCE / RANKING |
| BetaFilter | DIRECTION-SPECIFIC HARD_GATE for configured risk cases |
| SupportResistanceEngine | SOFT_EVIDENCE / direction-specific constraint |
| MultiFrameEngine | SOFT_EVIDENCE / RANKING unless explicitly promoted after validation |
| PositionSizer | RISK recommendation only; never signal creation |
| AISignalRanker | RANKING only |
| ConfidenceEngine | HEURISTIC score only; not calibrated probability |
| CircuitBreaker | GLOBAL SAFETY HARD_GATE |
| 4H RRCE experiment | EXPERIMENTAL / OBSERVABILITY only |

## What must not happen

1. BTC bullishness must not be the reason a coin becomes LONG.
2. BTC bearishness must not automatically eliminate every SHORT or LONG candidate unless an explicit global safety state is active.
3. A legacy TrendEngine direction must not silently prevent the opposite direction from being structurally evaluated when the trend hard gate is disabled.
4. Ranking must not create a signal that failed structural/risk validation.
5. Heuristic confidence must not be presented as a probability.
6. Experimental results must not feed production signals without an explicit promotion decision and tests.

## Cleanup rule

Before changing numerical thresholds, first remove duplicated ownership and contradictory gates. Strategy tuning comes only after the decision pipeline is deterministic, direction-neutral, observable, and backtestable.
