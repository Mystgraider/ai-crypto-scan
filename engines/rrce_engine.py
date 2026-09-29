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

    def stage3_v69_shadow(self, df_ltf: pd.DataFrame, direction: str,
                           lookback: int = 60) -> dict | None:
        """Non-blocking replay of the raw V6.9 Stage 3 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_ltf).tail(lookback)
        if len(df_ltf) < 3:
            return {"passed": False, "reason": "insufficient_closed_candles"}
        last_close = float(df_ltf["close"].iloc[-2])
        if direction == "LONG":
            levels = d["swing_high"].dropna()
            if levels.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(levels.iloc[-1])
            choch = last_close > choch_level
        elif direction == "SHORT":
            levels = d["swing_low"].dropna()
            if levels.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(levels.iloc[-1])
            choch = last_close < choch_level
        else:
            return {"passed": False, "reason": "invalid_direction"}
        if not choch:
            return {"passed": False, "reason": "no_choch", "choch_level": choch_level}
        fvg = self._detect_fvg_near_v69_shadow(df_ltf, direction)
        if not fvg:
            return {"passed": False, "reason": "choch_without_fvg", "choch_level": choch_level}
        return {"passed": True, "choch_level": choch_level, "fvg": fvg,
                "break_idx": len(df_ltf) - 2,
                "break_time": df_ltf["timestamp"].iloc[-2] if "timestamp" in df_ltf.columns else None}

    def _detect_fvg_near_v69_shadow(self, df: pd.DataFrame, direction: str,
                                    lookback: int = 10) -> dict | None:
        d = df.tail(lookback + 2).reset_index(drop=True)
        for i in range(2, len(d)):
            c0, c2 = d.iloc[i - 2], d.iloc[i]
            if direction == "LONG" and c2["low"] > c0["high"]:
                return {"top": float(c2["low"]), "bottom": float(c0["high"]), "break_idx": i}
            if direction == "SHORT" and c2["high"] < c0["low"]:
                return {"top": float(c0["low"]), "bottom": float(c2["high"]), "break_idx": i}
        return None

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
        """Detect a recent swing-liquidity sweep using restored V6.7.2 semantics.

        Equal-high/equal-low clustering and range-extreme proximity are
        diagnostics only; neither is a hard requirement. Liquidity is sourced
        only from candles that precede the bounded sweep window, preserving
        the no-look-ahead rule.
        """
        pool_window_start = max(0, len(df_mtf) - (patience_bars + 1))
        pool_source = df_mtf.iloc[:pool_window_start]
        d = self._find_swings(pool_source).tail(lookback)
        window = df_mtf.iloc[-(patience_bars + 1):-1]
        base_window = {
            "sweep_window_start": str(window["timestamp"].iloc[0])
            if "timestamp" in window.columns and not window.empty else None,
            "sweep_window_end": str(window["timestamp"].iloc[-1])
            if "timestamp" in window.columns and not window.empty else None,
            "proximity_pct": float(proximity_pct),
            "patience_bars": int(patience_bars),
        }
        if window.empty:
            return {"passed": False, "reason": "empty_sweep_window",
                    "pools": [], **base_window}
        if direction == "LONG":
            levels, side, range_extreme = d["swing_low"].dropna(), "low", range_low
        elif direction == "SHORT":
            levels, side, range_extreme = d["swing_high"].dropna(), "high", range_high
        else:
            return {"passed": False, "reason": "invalid_direction", "pools": [],
                    **base_window}
        if levels.empty:
            return {"passed": False, "reason": f"no_liquidity_swing_{side}",
                    "pools": [], "near_pool_count": 0, "all_pool_count": 0,
                    **base_window}
        pools = [{"level": float(level), "touches": 1} for level in levels.tolist()]
        swept_candidates = []
        for pool in reversed(pools):
            level = pool["level"]
            mask = ((window["low"] < level) & (window["close"] > level)
                    if direction == "LONG"
                    else (window["high"] > level) & (window["close"] < level))
            if bool(mask.any()):
                swept_candidates.append((pool, mask))
                break
        pool = swept_candidates[0][0] if swept_candidates else pools[-1]
        level = float(pool["level"])
        swept_mask = ((window["low"] < level) & (window["close"] > level)
                      if direction == "LONG"
                      else (window["high"] > level) & (window["close"] < level))
        distance = abs(level - range_extreme) / abs(range_extreme) * 100 if range_extreme else None
        result = {
            "pools": pools, "pool_level": level,
            "selected_pool_side": side, "pool_side": side,
            "proximity_pct": float(proximity_pct),
            "pool_touches": int(pool.get("touches", 1)),
            "pool_distance_from_range_extreme_pct": round(distance, 4) if distance is not None else None,
            "near_pool_count": len(pools), "all_pool_count": len(pools),
            **base_window,
        }
        if not bool(swept_mask.any()):
            return {"passed": False, "reason": "pool_found_not_swept", **result}
        sweep_idx = swept_mask[swept_mask].index[-1]
        sweep_extreme = float(window.loc[sweep_idx, "low"] if direction == "LONG" else window.loc[sweep_idx, "high"])
        sweep_candle_time = window.loc[sweep_idx, "timestamp"] if "timestamp" in window.columns else None
        sweep_time = (pd.to_datetime(sweep_candle_time, utc=True, errors="raise") + pd.Timedelta(hours=1)
                      if sweep_candle_time is not None else None)
        return {"passed": True, "reason": None, **result,
                "sweep_extreme": sweep_extreme, "sweep_candle_time": sweep_candle_time,
                "sweep_time": sweep_time}


    def _detect_fvg_near(self, df: pd.DataFrame, direction: str,
                         lookback: int = 10, break_idx: int = None) -> dict | None:
        """Detect a recent FVG without requiring it to be the CHOCH candle."""
        if len(df) < 3:
            return None
        if break_idx is not None:
            end = min(int(break_idx), len(df) - 1)
            start = max(0, end - int(lookback) - 1)
            indices = range(start + 2, end + 1)
        else:
            start = max(0, len(df) - int(lookback) - 2)
            indices = range(start + 2, len(df))
        for i in indices:
            c0, c2 = df.iloc[i - 2], df.iloc[i]
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
            # A centered swing of width N is only knowable after N
            # future candles exist. The old handoff ended after only N
            # candles, which could stop the search exactly before a
            # post-sweep N=10 swing became confirmable. That made the
            # "wait for confirmed structure" rule self-defeating.
            #
            # Reserve one max-width interval to CONFIRM the post-sweep swing,
            # then another max-width interval to WAIT FOR THE BREAK from it.
            # This remains bounded; it does not become an unbounded
            # "eventually wait for CHOCH" rule.
            max_extension = max(structure_lookbacks)
            handoff_end = min(
                window_end,
                primary_end + (2 * max_extension),
            )
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
                    # A swing used to confirm CHOCH must be structurally
                    # knowable before the break candle itself.
                    if swing_idx >= break_idx:
                        continue
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
                # Never use the break candle itself as its own confirmed
                # structural reference.
                if swing_idx >= break_idx:
                    continue
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

                # FVG is optional under the restored strategy. Keep it as
                # an entry-zone candidate when present, but CHOCH is the gate.
                fvg = self._detect_fvg_near(
                    closed, direction, break_idx=break_idx
                )
                return {
                    "passed": True,
                    "choch": True,
                    "bos": False,
                    "choch_level": choch_level,
                    "fvg": fvg,
                    "break_idx": break_idx,
                    "break_time": break_time,
                    "structure_lookback": structure_n,
                    "structure_handoff": break_idx > primary_end,
                    "handoff_candidates_checked": len(handoff_candidates),
                    "fvg_exact_choch_required": False,
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
        """Legacy-style OB: opposite-colored candle before an impulsive move."""
        if len(df) < 3:
            return None
        end = min(max(2, break_idx if break_idx is not None else len(df) - 2), len(df) - 1)
        start = max(2, end - int(lookback))
        for i in range(end, start - 1, -1):
            impulse = df.iloc[i]
            body = abs(float(impulse["close"]) - float(impulse["open"]))
            prior = (df.iloc[max(0, i - 10):i]["close"] - df.iloc[max(0, i - 10):i]["open"]).abs()
            avg_body = float(prior.mean()) if len(prior) else 0.0
            prev = df.iloc[i - 1]
            impulsive = avg_body <= 0 or body > 1.2 * avg_body
            if direction == "LONG" and prev["close"] < prev["open"] and impulsive:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": False, "impulsive": True, "source_idx": i - 1}
            if direction == "SHORT" and prev["close"] > prev["open"] and impulsive:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": False, "impulsive": True, "source_idx": i - 1}
        return None


    def stage4_execution(self, df_exec: pd.DataFrame, direction: str,
                          fvg: dict | None, sweep_extreme: float,
                          opposite_pool_level: float, break_idx: int = None,
                          max_rr_cap: float = 4.0) -> dict:
        """Use FVG OR OB as the execution entry structure."""
        ob = self._order_block(df_exec, direction, break_idx=break_idx)
        if ob:
            entry = (ob["top"] + ob["bottom"]) / 2.0
            entry_zone = "OB"
        elif fvg:
            entry = (float(fvg["top"]) + float(fvg["bottom"])) / 2.0
            entry_zone = "FVG"
        else:
            return {"valid": False, "reason": "no_fvg_or_order_block"}
        atr = None
        if "atr" in df_exec.columns:
            atr_idx = break_idx if break_idx is not None else len(df_exec) - 2
            if 0 <= atr_idx < len(df_exec):
                atr_value = df_exec["atr"].iloc[atr_idx]
                if not pd.isna(atr_value) and float(atr_value) > 0:
                    atr = float(atr_value)
        buffer = atr * 0.3 if atr is not None else abs(entry) * 0.003
        sl = sweep_extreme - buffer if direction == "LONG" else sweep_extreme + buffer
        risk = abs(entry - sl)
        if risk <= 0:
            return {"valid": False, "reason": "invalid_risk"}
        raw_tp = float(opposite_pool_level)
        if direction == "LONG":
            capped_tp = entry + max_rr_cap * risk
            tp = min(raw_tp, capped_tp) if raw_tp > entry else capped_tp
        else:
            capped_tp = entry - max_rr_cap * risk
            tp = max(raw_tp, capped_tp) if raw_tp < entry else capped_tp
        return {"valid": True, "entry": round(entry, 8), "sl": round(sl, 8),
                "tp": round(tp, 8), "rr": round(abs(tp - entry) / risk, 2),
                "order_block": ob, "fvg": fvg, "entry_zone": entry_zone}


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

        # Stage 3 runs on the 15m confirmation dataframe while Stage 4
        # intentionally runs on the finer 5m execution dataframe. The old
        # implementation compared the same positional index in both frames,
        # which is invalid across timeframes and would reject every otherwise
        # valid Stage-3 setup with a timestamp mismatch. Resolve the exact
        # 15m CHOCH-open timestamp into the corresponding 5m candle instead.
        break_idx = s3.get("break_idx")
        if break_idx is None or break_idx < 0 or break_idx >= len(df_ltf_confirm):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "missing_or_invalid_break_idx"
            return result

        if "timestamp" not in df_ltf_confirm.columns or "timestamp" not in df_ltf_exec.columns:
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "missing_execution_timestamp"
            return result

        try:
            confirm_ts = pd.to_datetime(
                df_ltf_confirm["timestamp"].iloc[break_idx], utc=True, errors="raise"
            )
            exec_ts_series = pd.to_datetime(
                df_ltf_exec["timestamp"], utc=True, errors="raise"
            )
        except (TypeError, ValueError, OverflowError):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "invalid_execution_timestamp"
            return result

        if exec_ts_series.duplicated().any():
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "duplicate_execution_timestamps"
            return result

        matching_exec_positions = [
            i for i, ts in enumerate(exec_ts_series) if ts == confirm_ts
        ]
        if len(matching_exec_positions) != 1:
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = (
                "execution_candle_not_found"
                if not matching_exec_positions
                else "multiple_execution_candles_at_break_time"
            )
            result["stage3"]["confirm_break_time"] = str(confirm_ts)
            return result

        exec_break_idx = matching_exec_positions[0]
        if exec_break_idx < 1 or exec_break_idx >= len(df_ltf_exec):
            result["failed_at"] = "stage3_dataframe_alignment"
            result["stage3"]["reason"] = "execution_break_idx_out_of_range"
            return result

        result["stage3"]["execution_break_idx"] = exec_break_idx
        result["stage3"]["execution_break_time"] = str(confirm_ts)

        opposite_pool = s1["range_high"] if direction == "LONG" else s1["range_low"]
        s4 = self.stage4_execution(
            df_ltf_exec, direction, s3["fvg"], s2["sweep_extreme"],
            opposite_pool, break_idx=exec_break_idx
        )
        result["stage4"] = s4
        if not s4.get("valid"):
            result["failed_at"] = "stage4_execution"
            return result

        result["valid"] = True
        result["bonus"] = 15.0
        return result