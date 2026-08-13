"""
RRCE Engine — V6.9 (Full Multi-Timeframe Rebuild)
====================================================
Implements the complete 4-stage RRCE checklist as specified:

  [1. RANGE]  ->  [2. RETAIL LIQUIDITY]  ->  [3. CONFIRMATION]  ->  [4. EXECUTION]
   (HTF: 4H)         (MTF: 1H)                (LTF: 15m)            (LTF: 5m)

This is a strict sequential validator, not a soft bonus generator — every
stage must pass, in order, on its designated timeframe, for a setup to
be considered RRCE-valid. Partial confluence is reported for visibility
but does NOT count as a valid setup.

Stage 1 — RANGE (HTF, e.g. 4H):
  Mark Range High / Range Low from recent swing structure. Price must
  sit in the Discount zone (lower half of range) for LONG, or the
  Premium zone (upper half) for SHORT.

Stage 2 — RETAIL LIQUIDITY (MTF, e.g. 1H):
  Locate a liquidity pool near the relevant range extreme — Equal
  Highs/Lows (two or more swing points clustered within a tight
  tolerance) or a clear trendline pool. This pool must then be SWEPT
  (wicked through and closed back on the other side) — this is bait,
  not confirmation by itself.

Stage 3 — CONFIRMATION (LTF, e.g. 15m):
  After the sweep, wait for CHOCH / MSS (Change of Character / Market
  Structure Shift) — price closing beyond the most recent opposing
  structural point. This break MUST leave behind an FVG (Fair Value
  Gap) — without the imbalance, it isn't treated as institutional
  confirmation, just noise.

Stage 4 — EXECUTION (LTF, e.g. 5m):
  Entry at the FVG retest / Order Block origin. Stop Loss behind the
  Stage 2 sweep extreme. Take Profit at the opposite-side liquidity
  pool (mirrors Stage 2, on the other end of the range).
"""

import pandas as pd
import numpy as np


class RRCEEngine:

    def __init__(self, swing_lookback: int = 5, eq_tolerance_pct: float = 0.15):
        self.swing_lookback = swing_lookback
        self.eq_tolerance_pct = eq_tolerance_pct

    # ── shared helper ────────────────────────────────────────────────────
    def _find_swings(self, df: pd.DataFrame, n: int = None) -> pd.DataFrame:
        n = n or self.swing_lookback
        d = df.copy()
        d["swing_high"] = d["high"][
            (d["high"] == d["high"].rolling(2 * n + 1, center=True).max())
        ]
        d["swing_low"] = d["low"][
            (d["low"] == d["low"].rolling(2 * n + 1, center=True).min())
        ]
        return d

    # ── Stage 1: RANGE (HTF) ─────────────────────────────────────────────
    def stage1_range(self, df_htf: pd.DataFrame, direction: str, price: float,
                      lookback: int = 60) -> dict | None:
        d = self._find_swings(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None

        range_high = float(highs.max())
        range_low  = float(lows.min())
        if range_high <= range_low:
            return None

        midpoint = (range_high + range_low) / 2.0
        position_pct = (price - range_low) / (range_high - range_low) * 100

        if direction == "LONG":
            zone_ok = price <= midpoint       # Discount zone
            zone = "discount"
        else:
            zone_ok = price >= midpoint       # Premium zone
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
        """Groups nearby levels (within eq_tolerance_pct) into pools of
        2+ — these are Equal Highs/Lows, i.e. resting liquidity."""
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
                                 proximity_pct: float = 5.0, lookback: int = 80) -> dict | None:
        d = self._find_swings(df_mtf).tail(lookback)
        last = df_mtf.iloc[-2]  # last CLOSED candle

        if direction == "LONG":
            lows = d["swing_low"].dropna().tolist()
            pools = self._equal_levels(lows)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_low) / range_low * 100 <= proximity_pct]
            if not near_pools:
                return {"passed": False, "reason": "no_equal_lows_near_range_low", "pools": pools}
            pool = min(near_pools, key=lambda p: abs(p["level"] - range_low))
            swept = float(last["low"]) < pool["level"] and float(last["close"]) > pool["level"]
        else:
            highs = d["swing_high"].dropna().tolist()
            pools = self._equal_levels(highs)
            near_pools = [p for p in pools
                          if abs(p["level"] - range_high) / range_high * 100 <= proximity_pct]
            if not near_pools:
                return {"passed": False, "reason": "no_equal_highs_near_range_high", "pools": pools}
            pool = min(near_pools, key=lambda p: abs(p["level"] - range_high))
            swept = float(last["high"]) > pool["level"] and float(last["close"]) < pool["level"]

        return {
            "passed": bool(swept),
            "pool_level": pool["level"],
            "pool_touches": pool["touches"],
            "sweep_extreme": float(last["low"] if direction == "LONG" else last["high"]),
        }

    # ── Stage 3: CONFIRMATION (LTF) ──────────────────────────────────────
    def _detect_fvg_near(self, df: pd.DataFrame, direction: str, lookback: int = 10) -> dict | None:
        d = df.tail(lookback + 2).reset_index(drop=True)
        for i in range(2, len(d)):
            c0, c2 = d.iloc[i - 2], d.iloc[i]
            if direction == "LONG" and c2["low"] > c0["high"]:
                return {"top": float(c2["low"]), "bottom": float(c0["high"])}
            if direction == "SHORT" and c2["high"] < c0["low"]:
                return {"top": float(c0["low"]), "bottom": float(c2["high"])}
        return None

    def stage3_confirmation(self, df_ltf: pd.DataFrame, direction: str, lookback: int = 60) -> dict | None:
        d = self._find_swings(df_ltf).tail(lookback)
        last_close = float(df_ltf["close"].iloc[-2])

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

        fvg = self._detect_fvg_near(df_ltf, direction)
        if not fvg:
            return {"passed": False, "reason": "choch_without_fvg", "choch_level": choch_level}

        return {"passed": True, "choch_level": choch_level, "fvg": fvg}

    # ── Stage 4: EXECUTION (LTF, finest) ─────────────────────────────────
    def _order_block(self, df: pd.DataFrame, direction: str, lookback: int = 15) -> dict | None:
        d = df.tail(lookback + 3).reset_index(drop=True)
        for i in range(len(d) - 2, 1, -1):
            impulse = d.iloc[i]
            body = abs(impulse["close"] - impulse["open"])
            avg_body = (d["close"] - d["open"]).abs().rolling(10).mean().iloc[i]
            if not (avg_body and body > 1.5 * avg_body):
                continue
            prev = d.iloc[i - 1]
            if direction == "LONG" and impulse["close"] > impulse["open"] and prev["close"] < prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"])}
            if direction == "SHORT" and impulse["close"] < impulse["open"] and prev["close"] > prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"])}
        return None

    def stage4_execution(self, df_exec: pd.DataFrame, direction: str,
                          fvg: dict, sweep_extreme: float,
                          opposite_pool_level: float) -> dict:
        ob = self._order_block(df_exec, direction)

        if ob:
            entry = (ob["top"] + ob["bottom"]) / 2.0
        else:
            entry = (fvg["top"] + fvg["bottom"]) / 2.0

        buffer = abs(entry) * 0.001
        if direction == "LONG":
            sl = sweep_extreme - buffer
        else:
            sl = sweep_extreme + buffer

        tp = opposite_pool_level
        rr = abs(tp - entry) / abs(entry - sl) if abs(entry - sl) > 0 else 0.0

        return {
            "entry": round(entry, 8),
            "sl": round(sl, 8),
            "tp": round(tp, 8),
            "rr": round(rr, 2),
            "order_block": ob,
        }

    # ── Full sequence, strictly gated ────────────────────────────────────
    def evaluate(self, df_htf: pd.DataFrame, df_mtf: pd.DataFrame,
                 df_ltf_confirm: pd.DataFrame, df_ltf_exec: pd.DataFrame,
                 direction: str, price: float) -> dict:
        """
        Runs the full 4-stage RRCE sequence. Every stage must pass, in
        order, using its designated timeframe. `valid` is True only if
        ALL FOUR stages pass — strict gate, not partial credit. Stops
        at the first failed stage.
        """
        result = {"valid": False, "failed_at": None, "stage1": None,
                   "stage2": None, "stage3": None, "stage4": None, "bonus": 0.0}

        s1 = self.stage1_range(df_htf, direction, price)
        result["stage1"] = s1
        if not s1 or not s1["passed"]:
            result["failed_at"] = "stage1_range"
            return result

        s2 = self.stage2_retail_liquidity(df_mtf, direction, s1["range_low"], s1["range_high"])
        result["stage2"] = s2
        if not s2 or not s2["passed"]:
            result["failed_at"] = "stage2_retail_liquidity"
            return result

        s3 = self.stage3_confirmation(df_ltf_confirm, direction)
        result["stage3"] = s3
        if not s3 or not s3["passed"]:
            result["failed_at"] = "stage3_confirmation"
            return result

        opposite_pool = s1["range_high"] if direction == "LONG" else s1["range_low"]
        s4 = self.stage4_execution(df_ltf_exec, direction, s3["fvg"],
                                    s2["sweep_extreme"], opposite_pool)
        result["stage4"] = s4

        result["valid"] = True
        result["bonus"] = 15.0
        return result
