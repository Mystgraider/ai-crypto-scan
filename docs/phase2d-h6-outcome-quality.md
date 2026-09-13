# Phase 2D-H.6 — Outcome Quality & Evidence Diagnostics

## Purpose

H.6 provides read-only diagnostics for the quality and provenance of stored trade outcomes. It consumes the H.5 canonical outcome resolver and does not alter trading behavior.

## Contract

- H.5 remains the only canonical trade-R resolver.
- Explicit execution evidence is authoritative only when H.5 resolves it as complete.
- Terminal `realized_r` and legacy calculation remain fallback sources according to H.5 precedence.
- TP milestone timestamps (`tp1_hit_at`, `tp2_hit_at`, `tp3_hit_at`) never count as execution evidence.
- H.6 never creates, repairs, or infers execution data.
- `EXPIRED` remains censored and is not counted as a resolved win/loss outcome.
- A terminal `TP3_HIT` or `SL_HIT` with no authoritative H.5 outcome is reported as unresolved.

## Diagnostics

The H.6 report exposes:

- total signals
- terminal signals
- resolved signals
- expired signals
- unresolved resolved-status records
- canonical outcome source distribution
- explicit execution evidence quality distribution
- unresolved reason distribution

## Safety boundary

H.6 is diagnostic only. It does not modify:

- scanner decisions
- ranking
- AI weights
- thresholds
- confidence formula
- position sizing
- lifecycle transitions
- stored signal outcomes

The output is intended to make outcome provenance and data quality measurable before any future tuning or strategy changes are considered.
