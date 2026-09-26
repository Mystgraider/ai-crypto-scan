"""
RRCE Engine — V6.9.24 (Multi-Timeframe, Locked)
====================================================
Implements the complete 4-stage RRCE checklist with the production
timeframe contract locked to 4H -> 1H -> 15m -> 5m:

  [1. RANGE]  ->  [2. RETAIL LIQUIDITY]  ->  [3. CONFIRMATION]  ->  [4. EXECUTION]
       (4H)              (1H)                    (15m)                 (5m)

This is a strict sequential validator, not a soft bonus generator — every
stage must pass, in order, for a setup to be considered RRCE-valid.
Partial confluence is reported for visibility but does NOT count as a
valid setup, and (as of V6.9.1) is a hard requirement in the scanner —
no signal fires unless RRCE is fully valid.

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

    @staticmethod
    def live_entry_levels(direction: str, live_price: float, stage4: dict,
                          max_deviation_pct: float, min_rr: float) -> dict:
        """Validate a live fill against the RRCE pullback zone."""
        if not stage4:
            return {"valid": False, "reason": "missing_stage4"}
        if stage4.get("valid") is not True:
            return {"valid": False, "reason": "invalid_stage4"}

        planned_entry = float(stage4["entry"])
        sl = float(stage4["sl"])
        tp = float(stage4["tp"])
        if planned_entry <= 0 or live_price <= 0:
            return {"valid": False, "reason": "invalid_price"}

        deviation_pct = abs(live_price - planned_entry) / planned_entry * 100
        if deviation_pct > max_deviation_pct:
            return {
                "valid": False,
                "reason": "price_away_from_rrce_entry",
                "planned_entry": planned_entry,
                "deviation_pct": round(deviation_pct, 3),
            }

        if direction == "LONG":
            valid_structure = sl < live_price < tp
        elif direction == "SHORT":
            valid_structure = tp < live_price < sl
        else:
            return {"valid": False, "reason": "invalid_direction"}

        if not valid_structure:
            return {"valid": False, "reason": "invalid_live_structure"}

        risk = abs(live_price - sl)
        reward = abs(tp - live_price)
        rr = reward / risk if risk else 0.0
        if rr < min_rr:
            return {"valid": False, "reason": "rr_below_minimum", "rr": round(rr, 2)}

        return {
            "valid": True,
            "entry": live_price,
            "sl": sl,
            "tp1": tp,
            "tp2": tp,
            "tp3": tp,
            "rr": round(rr, 2),
            "planned_entry": planned_entry,
            "deviation_pct": round(deviation_pct, 3),
        }

    # ── shared helper ────────────────────────────────────────────────────
    def _find_swings(self, df: pd.DataFrame, n: int = None) -> pd.DataFrame:
        n = n or self.swing_lookback
        # Structure must never be allowed to use the currently-forming candle
        # as the "future" confirmation bar for a swing point.
        d = df.iloc[:-1].copy() if len(df) >= 2 else df.iloc[0:0].copy()
        d["swing_high"] = d["high"].where(
            d["high"] == d["high"].rolling(2 * n + 1, center=True).max()
        )
        d["swing_low"] = d["low"].where(
            d["low"] == d["low"].rolling(2 * n + 1, center=True).min()
        )
        return d

    def _find_swings_v69_shadow(self, df: pd.DataFrame, n: int = None) -> pd.DataFrame:
        """Raw V6.9 shadow swing detector; intentionally keeps the forming row."""
        n = n or self.swing_lookback
        d = df.copy()
        d["swing_high"] = d["high"].where(
            d["high"] == d["high"].rolling(2 * n + 1, center=True).max()
        )
        d["swing_low"] = d["low"].where(
            d["low"] == d["low"].rolling(2 * n + 1, center=True).min()
        )
        return d

    def stage1_v69_shadow(self, df_htf: pd.DataFrame, direction: str, price: float,
                          lookback: int = 60) -> dict | None:
        """Non-blocking replay of raw V6.9 Stage 1 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None
        range_high = float(highs.max())
        range_low = float(lows.min())
        if range_high <= range_low:
            return None
        midpoint = (range_high + range_low) / 2.0
        position_pct = (price - range_low) / (range_high - range_low) * 100
        passed = price <= midpoint if direction == "LONG" else price >= midpoint
        return {"passed": bool(passed), "range_high": range_high,
                "range_low": range_low, "position_pct": round(position_pct, 1)}

    def stage2_v69_shadow(self, df_mtf: pd.DataFrame, direction: str,
                          range_low: float, range_high: float,
                          proximity_pct: float = 5.0, lookback: int = 80) -> dict | None:
        """Non-blocking replay of raw V6.9 Stage 2 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_mtf).tail(lookback)
        if len(df_mtf) < 2:
            return None
        last = df_mtf.iloc[-2]
        if direction == "LONG":
            pools = self._equal_levels(d["swing_low"].dropna().tolist())
            near = [p for p in pools if abs(p["level"] - range_low) / range_low * 100 <= proximity_pct]
            if not near:
                return {"passed": False, "reason": "no_equal_lows_near_range_low"}
            pool = min(near, key=lambda p: abs(p["level"] - range_low))
            swept = float(last["low"]) < pool["level"] and float(last["close"]) > pool["level"]
        elif direction == "SHORT":
            pools = self._equal_levels(d["swing_high"].dropna().tolist())
            near = [p for p in pools if abs(p["level"] - range_high) / range_high * 100 <= proximity_pct]
            if not near:
                return {"passed": False, "reason": "no_equal_highs_near_range_high"}
            pool = min(near, key=lambda p: abs(p["level"] - range_high))
            swept = float(last["high"]) > pool["level"] and float(last["close"]) < pool["level"]
        else:
            return None
        return {"passed": bool(swept), "reason": None if swept else "pool_found_not_swept"}

    # ── Stage 1: RANGE (HTF) ─────────────────────────────────────────────
    def stage1_range(self, df_htf: pd.DataFrame, direction: str, price: float,
                      lookback: int = 45, zone_threshold_pct: float = 60.0) -> dict | None:
        d = self._find_swings(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None

        # V6.9 contract: the HTF range is the swing envelope over the
        # configured lookback — highest confirmed swing high and lowest
        # confirmed swing low. Do not replace this with an alternating
        # "latest high/latest low pair"; that changes the range itself and
        # can move the Discount/Premium boundary between decisions.
        range_high = float(highs.max())
        range_low = float(lows.min())
        last_high_idx = highs.idxmax()
        last_low_idx = lows.idxmin()

        if range_high <= range_low:
            return None

        midpoint = (range_high + range_low) / 2.0
        range_width_pct = (range_high - range_low) / range_low * 100 if range_low else None
        position_pct = (price - range_low) / (range_high - range_low) * 100

        def _timestamp_for(idx):
            if "timestamp" not in df_htf.columns or idx not in df_htf.index:
                return None
            try:
                return str(df_htf.loc[idx, "timestamp"])
            except Exception:
                return None

        range_high_time = _timestamp_for(last_high_idx)
        range_low_time = _timestamp_for(last_low_idx)

        # A structural range is only valid while price is inside that
        # range. Without this bound, LONG setups below range_low and SHORT
        # setups above range_high can pass the one-sided discount/premium
        # test, producing negative or >100% position_pct values.
        inside_range = 0.0 <= position_pct <= 100.0

        if direction == "LONG":
            zone_ok = inside_range and position_pct <= zone_threshold_pct
            zone = "discount"
        elif direction == "SHORT":
            zone_ok = inside_range and position_pct >= (100 - zone_threshold_pct)
            zone = "premium"
        else:
            zone_ok = False
            zone = "invalid"

        return {
            "passed": zone_ok,
            "range_high": range_high,
            "range_low": range_low,
            "midpoint": midpoint,
            "zone": zone,
            "position_pct": round(position_pct, 1),
            "range_width_pct": round(range_width_pct, 4) if range_width_pct is not None else None,
            "range_high_time": range_high_time,
            "range_low_time": range_low_time,
            "range_high_index": str(last_high_idx),
            "range_low_index": str(last_low_idx),
            "price_above_range_high_pct": round((price - range_high) / range_high * 100, 4) if range_high else None,
            "price_below_range_low_pct": round((range_low - price) / range_low * 100, 4) if range_low else None,
        }

    # ── Stage 2: RETAIL LIQUIDITY (MTF) ──────────────────────────────────
    def _equal_levels(self, levels: list[float]) -> list[dict]:
        """Groups nearby levels (within eq_tolerance_pct) into pools of 2+."""
        if len(levels) < 2:
            return []
        levels = sorted(levels)
        pools, current = [], [levels[0]]
        for lvl in levels[1:]:
            ref = current[-1]
            if ref != 0 and abs(lvl - ref) / abs(ref) * 100 <= self.eq_tolerance_pct:
                current.append(lvl)
            else:
                if len(current) >= 2:
                    pools.append(current)
                current = [lvl]
        if len(current) >= 2:
            pools.append(current)
        return [{"level": float(np.mean(p)), "touches": len(p)} for p in pools]

    def stage2_retail_liquidity(self, df_mtf: pd.DataFrame, direction: str,
                                 range_low: float, range_high: float,
                                 proximity_pct: float = 5.0, lookback: int = 80,
                                 patience_bars: int = 6) -> dict | None:
        """Find a recent equal-level liquidity pool and a CLOSED-candle sweep."""
        # Liquidity pools must be knowable before the sweep window begins.
        # Discovering swings from the full dataframe can let future-confirmed
        # swing points become pools for an earlier sweep, creating look-ahead
        # bias. Build the pool universe only from candles strictly before the
        # bounded sweep window; the sweep itself is then evaluated separately
        # on the closed candles inside that window.
        pool_window_start = max(0, len(df_mtf) - (patience_bars + 1))
        pool_source = df_mtf.iloc[:pool_window_start]
        d = self._find_swings(pool_source).tail(lookback)
        window = df_mtf.iloc[-(patience_bars + 1):-1]

        if direction == "LONG":
            lows = d["swing_low"].dropna().tolist()
            pools = self._equal_levels(lows)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_low) / range_low * 100 <= proximity_pct]
            range_extreme = range_low
            pool_side = "low"
            if not near_pools:
                return {
                    "passed": False,
                    "reason": "no_equal_lows_near_range_low",
                    "pools": pools,
                    "near_pool_count": 0,
                    "all_pool_count": len(pools),
                    "proximity_pct": float(proximity_pct),
                    "patience_bars": int(patience_bars),
                    "sweep_window_start": str(window["timestamp"].iloc[0]) if "timestamp" in window.columns and not window.empty else None,
                    "sweep_window_end": str(window["timestamp"].iloc[-1]) if "timestamp" in window.columns and not window.empty else None,
                }
            # Prefer a qualifying pool that was actually swept. If multiple
            # qualifying pools were swept, keep the one closest to the range
            # extreme. Do not let an unswept nearest pool hide a valid sweep
            # on another qualifying liquidity pool.
            swept_pools = []
            for candidate in near_pools:
                candidate_mask = (window["low"] < candidate["level"]) & (window["close"] > candidate["level"])
                if bool(candidate_mask.any()):
                    swept_pools.append((candidate, candidate_mask))
            if swept_pools:
                pool, swept_mask = min(
                    swept_pools,
                    key=lambda item: abs(item[0]["level"] - range_low)
                )
                swept = True
            else:
                pool = min(near_pools, key=lambda p: abs(p["level"] - range_low))
                swept_mask = (window["low"] < pool["level"]) & (window["close"] > pool["level"])
                swept = False
            sweep_extreme = float(window.loc[swept_mask, "low"].min()) if swept else float(window["low"].min())
        elif direction == "SHORT":
            highs = d["swing_high"].dropna().tolist()
            pools = self._equal_levels(highs)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_high) / range_high * 100 <= proximity_pct]
            range_extreme = range_high
            pool_side = "high"
            if not near_pools:
                return {
                    "passed": False,
                    "reason": "no_equal_highs_near_range_high",
                    "pools": pools,
                    "near_pool_count": 0,
                    "all_pool_count": len(pools),
                    "proximity_pct": float(proximity_pct),
                    "patience_bars": int(patience_bars),
                    "sweep_window_start": str(window["timestamp"].iloc[0]) if "timestamp" in window.columns and not window.empty else None,
                    "sweep_window_end": str(window["timestamp"].iloc[-1]) if "timestamp" in window.columns and not window.empty else None,
                }
            swept_pools = []
            for candidate in near_pools:
                candidate_mask = (window["high"] > candidate["level"]) & (window["close"] < candidate["level"])
                if bool(candidate_mask.any()):
                    swept_pools.append((candidate, candidate_mask))
            if swept_pools:
                pool, swept_mask = min(
                    swept_pools,
                    key=lambda item: abs(item[0]["level"] - range_high)
                )
                swept = True
            else:
                pool = min(near_pools, key=lambda p: abs(p["level"] - range_high))
                swept_mask = (window["high"] > pool["level"]) & (window["close"] < pool["level"])
                swept = False
            sweep_extreme = float(window.loc[swept_mask, "high"].max()) if swept else float(window["high"].max())
        else:
            return {"passed": False, "reason": "invalid_direction", "pools": []}

        sweep_time = None
        sweep_candle_time = None
        if swept and "timestamp" in window.columns:
            # Exchange OHLCV timestamps identify candle OPEN time. Stage 3 runs
            # on 5m candles, so the confirmation clock must begin only after
            # the complete 15m sweep candle has CLOSED. Using the 15m open
            # timestamp here would incorrectly admit 5m candles that occurred
            # inside the sweep candle itself.
            sweep_candle_time = window.loc[swept_mask, "timestamp"].iloc[-1]
            sweep_time = pd.to_datetime(
                sweep_candle_time, utc=True, errors="raise"
            ) + pd.Timedelta(minutes=15)

        pool_distance_pct = abs(pool["level"] - range_extreme) / range_extreme * 100 if range_extreme else None

        return {
            "passed": bool(swept),
            "reason": None if swept else "pool_found_not_swept",
            "pools": pools,
            "pool_level": pool["level"],
            "selected_pool_side": pool_side,
            "proximity_pct": float(proximity_pct),
            "pool_touches": pool["touches"],
            "pool_distance_from_range_extreme_pct": round(pool_distance_pct, 4) if pool_distance_pct is not None else None,
            "near_pool_count": len(near_pools),
            "all_pool_count": len(pools),
            "patience_bars": int(patience_bars),
            "sweep_window_start": str(window["timestamp"].iloc[0]) if "timestamp" in window.columns and not window.empty else None,
            "sweep_window_end": str(window["timestamp"].iloc[-1]) if "timestamp" in window.columns and not window.empty else None,
            "sweep_extreme": sweep_extreme,
            "sweep_candle_time": sweep_candle_time,
            "sweep_time": sweep_time,
        }

    # ── Stage 3: CONFIRMATION (LTF) ──────────────────────────────────────
    def _detect_fvg_near(self, df: pd.DataFrame, direction: str,
                         lookback: int = 10, break_idx: int = None) -> dict | None:
        """Detect the FVG specifically created by the CHOCH break candle."""
        if break_idx is not None:
            if break_idx < 2 or break_idx >= len(df):
                return None
            c0, c2 = df.iloc[break_idx - 2], df.iloc[break_idx]
            if direction == "LONG" and c2["low"] > c0["high"]:
                return {"top": float(c2["low"]), "bottom": float(c0["high"]), "break_idx": break_idx}
            if direction == "SHORT" and c2["high"] < c0["low"]:
                return {"top": float(c0["low"]), "bottom": float(c2["high"]), "break_idx": break_idx}
            return None

        d = df.tail(lookback + 2).reset_index(drop=True)
        for i in range(2, len(d)):
            c0, c2 = d.iloc[i - 2], d.iloc[i]
            if direction == "LONG" and c2["low"] > c0["high"]:
                return {"top": float(c2["low"]), "bottom": float(c0["high"]), "break_idx": i}
            if direction == "SHORT" and c2["high"] < c0["low"]:
                return {"top": float(c0["low"]), "bottom": float(c2["high"]), "break_idx": i}
        return None

    def stage3_confirmation(self, df_ltf: pd.DataFrame, direction: str,
                            lookback: int = 60, sweep_time=None,
                            confirmation_bars: int = 3) -> dict | None:
        """Confirm CHOCH/FVG using a bounded sweep-anchored window.

        The primary confirmation window remains anchored to the Stage-2 sweep.
        If no valid pair is found there, a bounded structural handoff may extend
        the search only after a post-sweep swing has become objectively
        confirmed. This accounts for centered-swing confirmation latency
        without turning Stage 3 into an unbounded "wait until CHOCH" rule.
        """
        closed = df_ltf.iloc[:-1].copy() if len(df_ltf) >= 2 else df_ltf.iloc[0:0].copy()
        if len(closed) < 3:
            return {"passed": False, "reason": "insufficient_closed_candles"}

        confirmation_bars = int(confirmation_bars)
        if confirmation_bars < 1:
            return {"passed": False, "reason": "invalid_confirmation_bars"}

        window_end = len(closed) - 1
        sweep_ts = None
        if sweep_time is not None:
            if "timestamp" not in closed.columns:
                return {"passed": False, "reason": "missing_ltf_timestamp"}
            try:
                sweep_ts = pd.to_datetime(sweep_time, utc=True, errors="raise")
                break_ts_series = pd.to_datetime(
                    closed["timestamp"], utc=True, errors="raise"
                )
            except (TypeError, ValueError, OverflowError):
                return {"passed": False, "reason": "invalid_sweep_timestamp"}
            if break_ts_series.duplicated().any():
                return {"passed": False, "reason": "duplicate_ltf_timestamps"}
            post_sweep = [
                int(i) for i in range(len(closed))
                if break_ts_series.iloc[i] > sweep_ts
            ]
            primary_candidates = post_sweep[:confirmation_bars]
        else:
            window_start = max(2, window_end - confirmation_bars + 1)
            primary_candidates = list(range(window_start, window_end + 1))

        primary_candidates = [
            i for i in primary_candidates if 2 <= i <= window_end
        ]
        if not primary_candidates:
            return {"passed": False, "reason": "no_choch", "saw_choch": False}

        primary_end = primary_candidates[-1]
        structure_lookbacks = [self.swing_lookback, 3, 5, 7]

        # First pass: preserve the original hard sweep-anchored confirmation
        # window. No delayed handoff is admitted until this pass fails.
        candidate_indices = list(primary_candidates)
        handoff_candidates = []
        handoff_ready_details = []
        handoff_choch_indices = []
        handoff_fvg_indices = []
        handoff_end = None

        # Second pass: bounded structural handoff. A later break candle is
        # eligible only after a post-sweep swing is actually confirmed by that
        # candle. This is the key latency fix: the clock for a late structure
        # starts when the structure becomes knowable, not when its swing point
        # merely appears on the chart.
        if sweep_ts is not None and primary_end < window_end:
            max_extension = max(structure_lookbacks)
            handoff_end = min(window_end, primary_end + max_extension)
            for break_idx in range(primary_end + 1, handoff_end + 1):
                handoff_ready = False
                for structure_n in structure_lookbacks:
                    if structure_n <= 0:
                        continue
                    structure = self._find_swings(
                        closed.iloc[:break_idx + 1], n=structure_n
                    )
                    if direction == "LONG":
                        swing_series = structure["swing_high"]
                    else:
                        swing_series = structure["swing_low"]
                    swing_levels = swing_series.dropna()
                    if swing_levels.empty:
                        continue
                    swing_idx = swing_levels.index[-1]
                    try:
                        swing_ts = pd.to_datetime(
                            closed["timestamp"].loc[swing_idx],
                            utc=True,
                            errors="raise",
                        )
                    except (TypeError, ValueError, OverflowError):
                        continue
                    if swing_ts > sweep_ts:
                        handoff_ready = True
                        break
                if handoff_ready:
                    candidate_indices.append(break_idx)
                    handoff_candidates.append(break_idx)
                    handoff_ready_details.append({
                        "break_idx": break_idx,
                        "break_time": closed["timestamp"].iloc[break_idx]
                        if "timestamp" in closed.columns else None,
                    })

        candidate_indices = sorted(set(candidate_indices))

        saw_choch = False
        saw_choch_before_sweep = False
        saw_choch_without_fvg = False
        last_choch_level = None
        last_break_time = None

        for break_idx in candidate_indices:
            break_time = (
                closed["timestamp"].iloc[break_idx]
                if "timestamp" in closed.columns else None
            )
            break_ts = (
                pd.to_datetime(break_time, utc=True, errors="raise")
                if break_time is not None else None
            )
            close = float(closed["close"].iloc[break_idx])

            for structure_n in structure_lookbacks:
                structure = self._find_swings(
                    closed.iloc[:break_idx + 1], n=structure_n
                ).tail(lookback)
                if direction == "LONG":
                    swing_series = structure["swing_high"]
                else:
                    swing_series = structure["swing_low"]

                swing_levels = swing_series.dropna()
                if swing_levels.empty:
                    continue

                swing_idx = swing_levels.index[-1]
                if sweep_ts is not None:
                    if "timestamp" not in closed.columns:
                        continue
                    swing_ts = pd.to_datetime(
                        closed["timestamp"].loc[swing_idx],
                        utc=True,
                        errors="raise",
                    )
                    # A structural handoff may only use a swing that formed
                    # after the completed sweep. The primary n=10 structure is
                    # also subject to this rule once evaluation moves beyond
                    # the original confirmation window.
                    if break_idx > primary_end and swing_ts <= sweep_ts:
                        continue
                    if structure_n != self.swing_lookback and swing_ts <= sweep_ts:
                        continue

                choch_level = float(swing_levels.iloc[-1])
                last_choch_level = choch_level
                last_break_time = break_time

                choch = (
                    close > choch_level
                    if direction == "LONG"
                    else close < choch_level
                )
                if not choch:
                    continue

                saw_choch = True
                if break_idx > primary_end:
                    handoff_choch_indices.append(break_idx)

                if sweep_ts is not None and break_ts is not None and break_ts <= sweep_ts:
                    saw_choch_before_sweep = True
                    continue

                fvg = self._detect_fvg_near(
                    closed, direction, break_idx=break_idx
                )
                if not fvg:
                    if break_idx > primary_end:
                        handoff_fvg_indices.append(break_idx)
                    saw_choch_without_fvg = True
                    continue

                return {
                    "passed": True,
                    "choch_level": choch_level,
                    "fvg": fvg,
                    "break_idx": break_idx,
                    "break_time": break_time,
                    "structure_lookback": structure_n,
                    "structure_handoff": break_idx > primary_end,
                    "handoff_candidates_checked": len(handoff_candidates),
                }

        if saw_choch_before_sweep and sweep_time is not None and not saw_choch_without_fvg:
            return {
                "passed": False,
                "reason": "choch_not_after_sweep",
                "choch_level": last_choch_level,
                "handoff_diagnostics": {
                    "primary_end": primary_end,
                    "handoff_end": handoff_end,
                    "handoff_candidates": handoff_candidates,
                    "handoff_ready_details": handoff_ready_details,
                    "handoff_choch_indices": handoff_choch_indices,
                    "handoff_choch_without_fvg_indices": handoff_fvg_indices,
                },
            }

        if saw_choch_without_fvg:
            return {
                "passed": False,
                "reason": "choch_without_break_fvg",
                "choch_level": last_choch_level,
                "break_time": last_break_time,
                "handoff_diagnostics": {
                "primary_end": primary_end,
                "handoff_end": handoff_end,
                "handoff_candidates": handoff_candidates,
                "handoff_ready_details": handoff_ready_details,
                "handoff_choch_indices": handoff_choch_indices,
                "handoff_choch_without_fvg_indices": handoff_fvg_indices,
            },
            }

        return {
            "passed": False,
            "reason": "no_choch",
            "choch_level": last_choch_level,
            "saw_choch": saw_choch,
            "handoff_diagnostics": {
                "primary_end": primary_end,
                "handoff_end": handoff_end if sweep_ts is not None else None,
                "handoff_candidates": handoff_candidates,
                "handoff_ready_details": handoff_ready_details,
                "handoff_choch_indices": handoff_choch_indices,
                "handoff_choch_without_fvg_indices": handoff_fvg_indices,
            },
        }

    # ── Stage 4: EXECUTION (LTF, finest) ─────────────────────────────────
    def _order_block(self, df: pd.DataFrame, direction: str, break_idx: int = None,
                      lookback: int = 15) -> dict | None:
        """Valid OB is the exact opposite-colored candle before the CHOCH break."""
        if break_idx is not None and break_idx >= 2 and break_idx < len(df):
            break_candle = df.iloc[break_idx]
            prev = df.iloc[break_idx - 1]
            body = abs(break_candle["close"] - break_candle["open"])
            window = df.iloc[max(0, break_idx - 10):break_idx]
            avg_body = (window["close"] - window["open"]).abs().mean() if len(window) else None
            is_impulsive = avg_body and body > 1.2 * avg_body

            prev_down = prev["close"] < prev["open"]
            prev_up = prev["close"] > prev["open"]

            if direction == "LONG" and prev_down:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": True, "impulsive": bool(is_impulsive)}
            if direction == "SHORT" and prev_up:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": True, "impulsive": bool(is_impulsive)}
            return None

        return None

    def stage4_execution(self, df_exec: pd.DataFrame, direction: str,
                          fvg: dict, sweep_extreme: float,
                          opposite_pool_level: float, break_idx: int = None,
                          max_rr_cap: float = 4.0) -> dict:
        ob = self._order_block(df_exec, direction, break_idx=break_idx)
        if not ob:
            return {"valid": False, "reason": "no_anchored_order_block"}

        entry = (ob["top"] + ob["bottom"]) / 2.0

        # Use ATR from the CHOCH break candle when available. The break_idx
        # is anchored to the closed-candle confirmation sequence, so this keeps
        # the execution buffer temporally aligned with the setup rather than
        # using a later candle's volatility.
        atr = None
        if "atr" in df_exec.columns:
            atr_idx = break_idx if break_idx is not None else len(df_exec) - 2
            if 0 <= atr_idx < len(df_exec):
                atr_value = df_exec["atr"].iloc[atr_idx]
                if not pd.isna(atr_value) and float(atr_value) > 0:
                    atr = float(atr_value)
        buffer = atr * 0.3 if atr is not None else abs(entry) * 0.003

        if direction == "LONG":
            sl = sweep_extreme - buffer
        else:
            sl = sweep_extreme + buffer

        risk = abs(entry - sl)

        if direction == "LONG":
            raw_tp = opposite_pool_level
            capped_tp = entry + max_rr_cap * risk
            tp = min(raw_tp, capped_tp) if raw_tp > entry else capped_tp
        else:
            raw_tp = opposite_pool_level
            capped_tp = entry - max_rr_cap * risk
            tp = max(raw_tp, capped_tp) if raw_tp < entry else capped_tp

        rr = abs(tp - entry) / risk if risk > 0 else 0.0

        return {
            "valid": True,
            "entry": round(entry, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8),
            "rr": round(rr, 2),
            "order_block": ob,
        }

    # ── Full sequence, strictly gated ────────────────────────────────────
    def evaluate(self, df_htf: pd.DataFrame, df_mtf: pd.DataFrame,
                 df_ltf_confirm: pd.DataFrame, df_ltf_exec: pd.DataFrame,
                 direction: str, price: float, patience_bars: int = 6, confirmation_bars: int = 3) -> dict:
        """Runs the full 4-stage RRCE sequence as hard sequential gates."""
        result = {"valid": False, "failed_at": None, "stage1": None,
                   "stage2": None, "stage3": None, "stage4": None, "bonus": 0.0}

        s1 = self.stage1_range(df_htf, direction, price)
        result["stage1"] = s1
        if not s1 or not s1["passed"]:
            result["failed_at"] = "stage1_range"
            return result

        s2 = self.stage2_retail_liquidity(
            df_mtf, direction, s1["range_low"], s1["range_high"],
            patience_bars=patience_bars,
        )
        result["stage2"] = s2
        if not s2 or not s2["passed"]:
            result["failed_at"] = "stage2_retail_liquidity"
            return result

        s3 = self.stage3_confirmation(
            df_ltf_confirm, direction,
            sweep_time=s2.get("sweep_time"),
            confirmation_bars=confirmation_bars,
        )
        result["stage3"] = s3
        if not s3 or not s3["passed"]:
            result["failed_at"] = "stage3_confirmation"
            return result

        # Stage 3 returns a positional break_idx. Stage 4 must resolve that
        # index to the exact same LTF candle. Production currently passes the
        # same dataframe to both stages, but the engine contract is hardened
        # here so a future caller cannot silently mix differently aligned
        # confirmation/execution frames.
        break_idx = s3.get("break_idx")
        if break_idx is None or break_idx < 0:
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "missing_break_idx"
            return result

        if "timestamp" not in df_ltf_confirm.columns or "timestamp" not in df_ltf_exec.columns:
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "missing_execution_timestamp"
            return result

        if break_idx >= len(df_ltf_confirm) or break_idx >= len(df_ltf_exec):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "break_idx_out_of_range"
            return result

        try:
            confirm_ts = pd.to_datetime(
                df_ltf_confirm["timestamp"].iloc[break_idx], utc=True, errors="raise"
            )
            exec_ts = pd.to_datetime(
                df_ltf_exec["timestamp"].iloc[break_idx], utc=True, errors="raise"
            )
        except (TypeError, ValueError, OverflowError):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "invalid_execution_timestamp"
            return result

        if confirm_ts != exec_ts:
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "break_candle_timestamp_mismatch"
            result["stage3"]["confirm_break_time"] = str(confirm_ts)
            result["stage3"]["exec_break_time"] = str(exec_ts)
            return result

        # The positional handoff is safe only when the actual break candle
        # contents also match. Timestamp equality alone is insufficient if a
        # future caller supplies separately assembled confirmation/execution
        # frames with stale or otherwise divergent OHLC/ATR data.
        for column in ("open", "high", "low", "close"):
            if column not in df_ltf_confirm.columns or column not in df_ltf_exec.columns:
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "missing_break_candle_field"
                result["stage3"]["field"] = column
                return result
            try:
                confirm_value = float(df_ltf_confirm[column].iloc[break_idx])
                exec_value = float(df_ltf_exec[column].iloc[break_idx])
            except (TypeError, ValueError, OverflowError):
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "invalid_break_candle_field"
                result["stage3"]["field"] = column
                return result
            if not np.isfinite(confirm_value) or not np.isfinite(exec_value):
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "invalid_break_candle_field"
                result["stage3"]["field"] = column
                return result
            if confirm_value != exec_value:
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "break_candle_data_mismatch"
                result["stage3"]["field"] = column
                return result

        if ("atr" in df_ltf_confirm.columns) != ("atr" in df_ltf_exec.columns):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "break_candle_atr_presence_mismatch"
            return result
        if "atr" in df_ltf_confirm.columns:
            try:
                confirm_atr = float(df_ltf_confirm["atr"].iloc[break_idx])
                exec_atr = float(df_ltf_exec["atr"].iloc[break_idx])
            except (TypeError, ValueError, OverflowError):
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "invalid_break_candle_atr"
                return result
            if not (np.isfinite(confirm_atr) and np.isfinite(exec_atr)):
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "invalid_break_candle_atr"
                return result
            if confirm_atr != exec_atr:
                result["failed_at"] = "stage3_dataframe_alignment"
                result["stage3"]["reason"] = "break_candle_atr_mismatch"
                return result

        opposite_pool = s1["range_high"] if direction == "LONG" else s1["range_low"]
        s4 = self.stage4_execution(
            df_ltf_exec, direction, s3["fvg"], s2["sweep_extreme"],
            opposite_pool, break_idx=break_idx
        )
        result["stage4"] = s4
        if not s4.get("valid"):
            result["failed_at"] = "stage4_execution"
            return result

        result["valid"] = True
        result["bonus"] = 15.0
        return result