""" 
RRCE Engine — V6.9.24 (Multi-Timeframe, Locked)
====================================================
Implements the complete 4-stage RRCE checklist with the production
timeframe contract locked to 4H -> 1H -> 15m -> 5m:

  [1. RANGE]  ->  [2. RETAIL LIQUIDITY]  ->  [3. CONFIRMATION]  ->  [4. EXECUTION]
       (4H)              (1H)                    (15m)                 (5m)

This engine is a strict sequential validator: every stage must pass, in
order, for a result to be reported as RRCE-valid. The scanner currently
uses the modern RRCE result as diagnostic/structural confluence and keeps
the preserved V6.7.2 RRCE contribution additive; modern RRCE validity is
not a production hard signal gate. Research replays may compare RRCE stage
variants, but must not silently change production signal, LONG, risk, or
SL/TP behavior.

Phase 2 integrity fixes:
  - Structure is calculated from CLOSED candles only; the live/incomplete
    candle cannot confirm a swing used by the current decision.
  - The Stage-3 CHOCH must occur after the Stage-2 sweep in time.
  - The FVG must be created by the specific CHOCH break candle, rather than
    any unrelated FVG elsewhere in the recent lookback.
  - Stage 4 requires the exact opposite-colored candle immediately before
    the CHOCH break as the Order Block; it no longer silently falls back to
    an unrelated FVG entry.
"""

import pandas as pd
import numpy as np


class RRCEEngine:

    def __init__(self, swing_lookback: int = 10, eq_tolerance_pct: float = 0.15):
        self.swing_lookback = swing_lookback
        self.eq_tolerance_pct = eq_tolerance_pct