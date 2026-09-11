"""
RRCE Engine — V6.9.24 (Multi-Timeframe, Locked)
====================================================
Implements the complete 4-stage RRCE checklist as specified, with
timeframes locked per explicit instruction:

  [1. RANGE]  ->  [2. RETAIL LIQUIDITY]  ->  [3. CONFIRMATION]  ->  [4. EXECUTION]
      (15m: Setup/Sweep)                        (5m: CHOCH/Confirmation/Entry)

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

    # ── Stage 1: RANGE (HTF) ─────────────────────────────────────────────
    def stage1_range(self, df_htf: pd.DataFrame, direction: str, price: float,
                      lookback: int = 45, zone_threshold_pct: float = 60.0) -> dict | None:
        d = self._find_swings(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None

        last_high_idx = highs.index[-1]
        last_low_idx  = lows.index[-1]
        if last_high_idx > last_low_idx:
            range_high = float(highs.iloc[-1])
            prior_lows = lows[lows.index < last_high_idx]
            range_low = float(prior_lows.iloc[-1]) if not prior_lows.empty else float(lows.min())
        else:
            range_low = float(lows.iloc[-1])
            prior_highs = highs[highs.index < last_low_idx]
            range_high = float(prior_highs.iloc[-1]) if not prior_highs.empty else float(highs.max())

        if range_high <= range_low:
            return None

        midpoint = (range_high + range_low) / 2.0
        position_pct = (price - range_low) / (range_high - range_low) * 100

        if direction == "LONG":
            zone_ok = position_pct <= zone_threshold_pct
            zone = "discount"
        else:
            zone_ok = position_pct >= (100 - zone_threshold_pct)
            zone = "premium"

        return {
            "passed": zone_ok,
            "range_high": range_high,
            "range_low": range_low,
            "midpoint": midpoint,
            "zone": zone,
            "position_pct": round(position_pct, 1),
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
        d = self._find_swings(df_mtf).tail(lookback)
        window = df_mtf.iloc[-(patience_bars + 1):-1]

        if direction == "LONG":
            lows = d["swing_low"].dropna().tolist()
            pools = self._equal_levels(lows)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_low) / range_low * 100 <= proximity_pct]
            if not near_pools:
                return {"passed": False, "reason": "no_equal_lows_near_range_low", "pools": pools}
            pool = min(near_pools, key=lambda p: abs(p["level"] - range_low))
            swept_mask = (window["low"] < pool["level"]) & (window["close"] > pool["level"])
            swept = bool(swept_mask.any())
            sweep_extreme = float(window.loc[swept_mask, "low"].min()) if swept else float(window["low"].min())
        else:
            highs = d["swing_high"].dropna().tolist()
            pools = self._equal_levels(highs)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_high) / range_high * 100 <= proximity_pct]
            if not near_pools:
                return {"passed": False, "reason": "no_equal_highs_near_range_high", "pools": pools}
            pool = min(near_pools, key=lambda p: abs(p["level"] - range_high))
            swept_mask = (window["high"] > pool["level"]) & (window["close"] < pool["level"])
            swept = bool(swept_mask.any())
            sweep_extreme = float(window.loc[swept_mask, "high"].max()) if swept else float(window["high"].max())

        sweep_time = None
        if swept and "timestamp" in window.columns:
            sweep_time = window.loc[swept_mask, "timestamp"].iloc[-1]

        return {
            "passed": bool(swept),
            "reason": None if swept else "pool_found_not_swept",
            "pools": pools,
            "pool_level": pool["level"],
            "pool_touches": pool["touches"],
            "sweep_extreme": sweep_extreme,
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
                            lookback: int = 60, sweep_time=None) -> dict | None:
        closed = df_ltf.iloc[:-1].copy() if len(df_ltf) >= 2 else df_ltf.iloc[0:0].copy()
        if len(closed) < 3:
            return {"passed": False, "reason": "insufficient_closed_candles"}

        d = self._find_swings(closed).tail(lookback)
        last_close = float(closed["close"].iloc[-1])
        break_idx = len(closed) - 1
        break_time = closed["timestamp"].iloc[-1] if "timestamp" in closed.columns else None

        if sweep_time is not None and break_time is not None:
            try:
                if pd.Timestamp(break_time) <= pd.Timestamp(sweep_time):
                    return {"passed": False, "reason": "choch_not_after_sweep"}
            except Exception:
                pass

        if direction == "LONG":
            swing_highs = d["swing_high"].dropna()
            if swing_highs.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(swing_highs.iloc[-1])
            choch = last_close > choch_level
        else:
            swing_lows = d["swing_low"].dropna()
            if swing_lows.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(swing_lows.iloc[-1])
            choch = last_close < choch_level

        if not choch:
            return {"passed": False, "reason": "no_choch", "choch_level": choch_level}

        fvg = self._detect_fvg_near(closed, direction, break_idx=break_idx)
        if not fvg:
            return {"passed": False, "reason": "choch_without_break_fvg", "choch_level": choch_level}

        return {
            "passed": True,
            "choch_level": choch_level,
            "fvg": fvg,
            "break_idx": break_idx,
            "break_time": break_time,
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

        if "atr" in df_exec.columns and not pd.isna(df_exec["atr"].iloc[-2]):
            buffer = float(df_exec["atr"].iloc[-2]) * 0.3
        else:
            buffer = abs(entry) * 0.003

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
                 direction: str, price: float, patience_bars: int = 6) -> dict:
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
            df_ltf_confirm, direction, sweep_time=s2.get("sweep_time")
        )
        result["stage3"] = s3
        if not s3 or not s3["passed"]:
            result["failed_at"] = "stage3_confirmation"
            return result

        opposite_pool = s1["range_high"] if direction == "LONG" else s1["range_low"]
        s4 = self.stage4_execution(
            df_ltf_exec, direction, s3["fvg"], s2["sweep_extreme"],
            opposite_pool, break_idx=s3.get("break_idx")
        )
        result["stage4"] = s4
        if not s4.get("valid"):
            result["failed_at"] = "stage4_execution"
            return result

        result["valid"] = True
        result["bonus"] = 15.0
        return result
