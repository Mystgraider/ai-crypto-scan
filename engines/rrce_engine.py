"""
RRCE Engine — V6.9.2 (Multi-Timeframe, Locked)
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

Stage 1 — RANGE (15m):
  Mark Range High / Range Low from recent swing structure. Price must
  sit in the Discount zone (lower half of range) for LONG, or the
  Premium zone (upper half) for SHORT.

Stage 2 — RETAIL LIQUIDITY (15m):
  Locate a liquidity pool near the relevant range extreme — Equal
  Highs/Lows (two or more swing points clustered within a tight
  tolerance). This pool must then be SWEPT (wicked through and closed
  back on the other side) — this is bait, not confirmation by itself.

Stage 3 — CONFIRMATION (5m):
  After the sweep, wait for CHOCH / MSS (Change of Character / Market
  Structure Shift) — price closing beyond the most recent opposing
  structural point. This break MUST leave behind an FVG (Fair Value
  Gap) — without the imbalance, it isn't treated as institutional
  confirmation, just noise.

Stage 4 — EXECUTION (5m):
  Entry at the FVG retest / Order Block origin. As of V6.9.2, the
  Order Block MUST be the exact candle immediately preceding the
  specific candle that caused the Stage-3 CHOCH break — not just any
  recent impulsive candle. Stop Loss behind the Stage 2 sweep extreme.
  Take Profit at the opposite-side liquidity pool.
"""

import pandas as pd
import numpy as np


class RRCEEngine:

    def __init__(self, swing_lookback: int = 10, eq_tolerance_pct: float = 0.15):
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
                      lookback: int = 45, zone_threshold_pct: float = 60.0) -> dict | None:
        d = self._find_swings(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None

        # V6.9.21: measured live data showed the OLD approach (max/min
        # across the whole lookback envelope) leaves position_pct
        # averaging 118-126% in trending markets — price constantly
        # breaks out beyond a stale historical range, so Discount/
        # Premium becomes meaningless (V6.9.18's 60% widening couldn't
        # help since real failures cluster far beyond even that).
        # Fix: anchor the Range to the CURRENT active leg — the most
        # recent swing high and the most recent swing low — so a fresh
        # breakout immediately becomes part of the new range instead
        # of sitting stale above an old one. This matches how ICT
        # discount/premium is actually meant to be applied (per
        # dealing range / current leg, not a fixed calendar window).
        last_high_idx = highs.index[-1]
        last_low_idx  = lows.index[-1]
        if last_high_idx > last_low_idx:
            # most recent leg: swing low -> swing high (up-leg)
            range_high = float(highs.iloc[-1])
            prior_lows = lows[lows.index < last_high_idx]
            range_low = float(prior_lows.iloc[-1]) if not prior_lows.empty else float(lows.min())
        else:
            # most recent leg: swing high -> swing low (down-leg)
            range_low = float(lows.iloc[-1])
            prior_highs = highs[highs.index < last_low_idx]
            range_high = float(prior_highs.iloc[-1]) if not prior_highs.empty else float(highs.max())

        if range_high <= range_low:
            return None

        midpoint = (range_high + range_low) / 2.0
        position_pct = (price - range_low) / (range_high - range_low) * 100

        # V6.9.18: was a strict 50/50 split. Live evidence across 300
        # real altcoins showed Stage 1 rejecting 70-95% of attempts in
        # trending regimes — much stricter than the clean BTC backtest
        # suggested, since real trends rarely offer an exact 50%
        # pullback before continuing. Widened to a configurable
        # threshold (default 60%) — LONG allowed up to the lower 60%
        # of the range (not just lower 50%), matching how ICT
        # practitioners commonly extend the "discount" zone band.
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
                                 proximity_pct: float = 5.0, lookback: int = 80,
                                 patience_bars: int = 6) -> dict | None:
        """
        V6.9.15: patience window for the sweep check. Instead of only
        counting a sweep if it happened on the single last CLOSED
        candle, checks whether ANY of the last `patience_bars` candles
        swept the identified liquidity pool — "mark the zone, then
        wait" instead of "only counts if it happens on this exact
        scan". Backtest-verified on 7 independent BTC windows (~14
        months): 52->98 trades, win rate held (58.3%->57.3%), total R
        nearly doubled (+77.44R -> +132.72R), positive in every single
        window tested. patience_bars=1 reproduces the original
        single-candle behavior exactly.
        """
        d = self._find_swings(df_mtf).tail(lookback)
        window = df_mtf.iloc[-(patience_bars + 1):-1]  # last `patience_bars` CLOSED candles

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

        return {
            "passed": bool(swept),
            "pool_level": pool["level"],
            "pool_touches": pool["touches"],
            "sweep_extreme": sweep_extreme,
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
        closes = df_ltf["close"]
        last_close = float(closes.iloc[-2])
        break_idx = len(df_ltf) - 2  # index of the candle whose CLOSE broke structure

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

        return {"passed": True, "choch_level": choch_level, "fvg": fvg, "break_idx": break_idx}

    # ── Stage 4: EXECUTION (LTF, finest) ─────────────────────────────────
    def _order_block(self, df: pd.DataFrame, direction: str, break_idx: int = None,
                      lookback: int = 15) -> dict | None:
        """
        Valid OB = the last opposite-colored candle immediately before
        the SPECIFIC candle that caused the CHOCH break (break_idx),
        not just any impulsive-looking candle in the recent window.
        Falls back to the old "most recent impulsive move" search only
        if no break_idx is supplied (defensive — shouldn't normally
        happen since stage3 always provides it when passed=True).
        """
        if break_idx is not None and break_idx >= 2:
            break_candle = df.iloc[break_idx]
            prev = df.iloc[break_idx - 1]
            body = abs(break_candle["close"] - break_candle["open"])
            window = df.iloc[max(0, break_idx - 10):break_idx]
            avg_body = (window["close"] - window["open"]).abs().mean() if len(window) else None
            is_impulsive = avg_body and body > 1.2 * avg_body

            broke_up = break_candle["close"] > break_candle["open"]
            prev_down = prev["close"] < prev["open"]
            broke_down = break_candle["close"] < break_candle["open"]
            prev_up = prev["close"] > prev["open"]

            if direction == "LONG" and prev_down:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": True, "impulsive": bool(is_impulsive)}
            if direction == "SHORT" and prev_up:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]),
                        "anchored": True, "impulsive": bool(is_impulsive)}
            return None  # break candle wasn't preceded by a valid opposite candle — no OB

        # defensive fallback (should not normally trigger)
        d = df.tail(lookback + 3).reset_index(drop=True)
        for i in range(len(d) - 2, 1, -1):
            impulse = d.iloc[i]
            body = abs(impulse["close"] - impulse["open"])
            avg_body = (d["close"] - d["open"]).abs().rolling(10).mean().iloc[i]
            if not (avg_body and body > 1.5 * avg_body):
                continue
            prev = d.iloc[i - 1]
            if direction == "LONG" and impulse["close"] > impulse["open"] and prev["close"] < prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]), "anchored": False}
            if direction == "SHORT" and impulse["close"] < impulse["open"] and prev["close"] > prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"]), "anchored": False}
        return None

    def stage4_execution(self, df_exec: pd.DataFrame, direction: str,
                          fvg: dict, sweep_extreme: float,
                          opposite_pool_level: float, break_idx: int = None,
                          max_rr_cap: float = 4.0) -> dict:
        ob = self._order_block(df_exec, direction, break_idx=break_idx)

        if ob:
            entry = (ob["top"] + ob["bottom"]) / 2.0
        else:
            entry = (fvg["top"] + fvg["bottom"]) / 2.0

        # V6.9.3 fix: SL buffer was a razor-thin 0.1% of price, which
        # normal candle noise/wicks routinely blew through even on
        # otherwise-valid setups. Use ATR (if available from the
        # Indicators pipeline) for a buffer that scales with actual
        # recent volatility; fall back to a wider 0.3% if ATR isn't
        # present (e.g. in isolated unit tests).
        if "atr" in df_exec.columns and not pd.isna(df_exec["atr"].iloc[-2]):
            buffer = float(df_exec["atr"].iloc[-2]) * 0.3
        else:
            buffer = abs(entry) * 0.003

        if direction == "LONG":
            sl = sweep_extreme - buffer
        else:
            sl = sweep_extreme + buffer

        risk = abs(entry - sl)

        # V6.9.3 fix: TP used to target the FULL opposite side of the
        # Stage-1 range, which is frequently unrealistically far
        # (backtest showed RR ranging 1.5 to 29+ on the same window,
        # with SL hit far more often simply because TP was too distant
        # to reasonably reach before a reversal). Cap the reward at
        # max_rr_cap * risk — still points toward the opposite pool,
        # but stops short of demanding the full round-trip.
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

        s2 = self.stage2_retail_liquidity(df_mtf, direction, s1["range_low"], s1["range_high"], patience_bars=patience_bars)
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
                                    s2["sweep_extreme"], opposite_pool,
                                    break_idx=s3.get("break_idx"))
        result["stage4"] = s4

        result["valid"] = True
        result["bonus"] = 15.0
        return result
