"""
RRCE Engine — V6.7
====================
Reaction -> Rejection (Liquidity Sweep) -> Confirmation (CHOCH/BOS) ->
Entry Zone (FVG/OB, 0.5-0.618 pullback) -> Execution (candle confirmation)

Implements the RRCE sequence as a state machine over recent price action.
This is a from-scratch reimplementation of the described mechanics
(standard SMC/ICT concepts — swing structure, liquidity sweeps, fair
value gaps, order blocks, OTE zone, candle patterns), not copied code.

All functions operate on a standard OHLCV pandas DataFrame (needs at
least ~50 bars of history for reliable swing detection).
"""

import pandas as pd
import numpy as np


class RRCEEngine:

    def __init__(self, swing_lookback: int = 5, structure_window: int = 50):
        self.swing_lookback = swing_lookback
        self.structure_window = structure_window

    # ── Step 0: Swing structure (needed by every later step) ───────────
    def find_swings(self, df: pd.DataFrame) -> pd.DataFrame:
        """Marks local swing highs/lows using a simple fractal (N bars
        on each side lower/higher than the pivot)."""
        n = self.swing_lookback
        d = df.copy()
        d["swing_high"] = d["high"][
            (d["high"] == d["high"].rolling(2 * n + 1, center=True).max())
        ]
        d["swing_low"] = d["low"][
            (d["low"] == d["low"].rolling(2 * n + 1, center=True).min())
        ]
        return d

    # ── Step 1: Rejection / Liquidity Sweep ─────────────────────────────
    def detect_liquidity_sweep(self, df: pd.DataFrame, direction: str) -> dict | None:
        """
        LONG: price wicks BELOW a recent swing low (sweeping resting
        sell-side liquidity / stops) then closes back ABOVE it — a
        stop hunt, not a real breakdown.
        SHORT: mirror, wicks above a recent swing high then closes
        back below.
        """
        d = self.find_swings(df).tail(self.structure_window)
        last = df.iloc[-2]  # last CLOSED candle

        if direction == "LONG":
            recent_lows = d["swing_low"].dropna()
            if recent_lows.empty:
                return None
            level = float(recent_lows.iloc[-1])
            wicked_below = float(last["low"]) < level
            closed_back_above = float(last["close"]) > level
            if wicked_below and closed_back_above:
                return {"level": level, "wick_low": float(last["low"])}
        else:
            recent_highs = d["swing_high"].dropna()
            if recent_highs.empty:
                return None
            level = float(recent_highs.iloc[-1])
            wicked_above = float(last["high"]) > level
            closed_back_below = float(last["close"]) < level
            if wicked_above and closed_back_below:
                return {"level": level, "wick_high": float(last["high"])}
        return None

    # ── Step 2: Confirmation — CHOCH / BOS ──────────────────────────────
    def detect_choch_bos(self, df: pd.DataFrame, direction: str) -> dict | None:
        """
        CHOCH (Change of Character): price breaks the most recent
        opposite-side swing point — first sign the prior trend may be
        reversing.
        BOS (Break of Structure): a further break confirming the NEW
        direction is continuing (not just a one-off CHOCH).
        We require at least CHOCH; BOS is a stronger (bonus) confirm.
        """
        d = self.find_swings(df).tail(self.structure_window)
        closes = df["close"]
        last_close = float(closes.iloc[-2])

        if direction == "LONG":
            swing_highs = d["swing_high"].dropna()
            if len(swing_highs) < 2:
                return None
            choch_level = float(swing_highs.iloc[-2])   # prior lower high
            bos_level   = float(swing_highs.iloc[-1])    # most recent high
            choch = last_close > choch_level
            bos   = last_close > bos_level
        else:
            swing_lows = d["swing_low"].dropna()
            if len(swing_lows) < 2:
                return None
            choch_level = float(swing_lows.iloc[-2])
            bos_level   = float(swing_lows.iloc[-1])
            choch = last_close < choch_level
            bos   = last_close < bos_level

        if not choch:
            return None
        return {"choch": True, "bos": bool(bos), "choch_level": choch_level, "bos_level": bos_level}

    # ── Step 3: Entry Zone — FVG / OB + OTE pullback ────────────────────
    def detect_fvg(self, df: pd.DataFrame, direction: str, lookback: int = 15) -> list[dict]:
        """
        Fair Value Gap: 3-candle imbalance where candle[0] high/low
        doesn't overlap candle[2] low/high — a gap the market often
        returns to fill before continuing.
        """
        d = df.tail(lookback + 2).reset_index(drop=True)
        gaps = []
        for i in range(2, len(d)):
            c0, c2 = d.iloc[i - 2], d.iloc[i]
            if direction == "LONG":
                if c2["low"] > c0["high"]:
                    gaps.append({"top": float(c2["low"]), "bottom": float(c0["high"])})
            else:
                if c2["high"] < c0["low"]:
                    gaps.append({"top": float(c0["low"]), "bottom": float(c2["high"])})
        return gaps

    def detect_order_block(self, df: pd.DataFrame, direction: str, lookback: int = 15) -> dict | None:
        """
        Order Block: the last opposite-colored candle immediately
        before an impulsive move in the trade direction — where
        institutional orders are assumed to sit.
        """
        d = df.tail(lookback + 3).reset_index(drop=True)
        for i in range(len(d) - 2, 1, -1):
            impulse = d.iloc[i]
            body = abs(impulse["close"] - impulse["open"])
            avg_body = (d["close"] - d["open"]).abs().rolling(10).mean().iloc[i]
            is_impulsive = avg_body and body > 1.5 * avg_body
            if not is_impulsive:
                continue
            prev = d.iloc[i - 1]
            if direction == "LONG" and impulse["close"] > impulse["open"] and prev["close"] < prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"])}
            if direction == "SHORT" and impulse["close"] < impulse["open"] and prev["close"] > prev["open"]:
                return {"top": float(prev["high"]), "bottom": float(prev["low"])}
        return None

    def in_ote_zone(self, price: float, sweep_level: float, structure_level: float) -> bool:
        """
        OTE (Optimal Trade Entry): pullback into the 0.5-0.618
        retracement of the most recent impulse leg (sweep -> break).
        """
        lo, hi = sorted([sweep_level, structure_level])
        rng = hi - lo
        if rng <= 0:
            return False
        fib_50  = hi - 0.5 * rng
        fib_618 = hi - 0.618 * rng
        zone_lo, zone_hi = sorted([fib_50, fib_618])
        return zone_lo <= price <= zone_hi

    # ── Step 4: Execution — candle confirmation ─────────────────────────
    def candle_confirmation(self, df: pd.DataFrame, direction: str) -> str | None:
        """Doji / Hammer-ish rejection / Bullish-Bearish Engulfing on the
        last CLOSED candle, in the trade direction."""
        c1 = df.iloc[-3]
        c2 = df.iloc[-2]   # last closed
        body2 = abs(c2["close"] - c2["open"])
        range2 = c2["high"] - c2["low"]
        if range2 <= 0:
            return None

        # Doji: tiny body relative to range
        if body2 / range2 < 0.15:
            return "doji"

        # Engulfing
        bull_engulf = (c2["close"] > c2["open"] and c1["close"] < c1["open"]
                       and c2["close"] >= c1["open"] and c2["open"] <= c1["close"])
        bear_engulf = (c2["close"] < c2["open"] and c1["close"] > c1["open"]
                       and c2["close"] <= c1["open"] and c2["open"] >= c1["close"])
        if direction == "LONG" and bull_engulf:
            return "bullish_engulfing"
        if direction == "SHORT" and bear_engulf:
            return "bearish_engulfing"

        # Harami (inside bar of opposite prior candle)
        harami = (c2["high"] <= c1["high"] and c2["low"] >= c1["low"])
        if harami:
            return "harami"

        return None

    # ── IDM (Inducement) ─────────────────────────────────────────────────
    def detect_idm(self, df: pd.DataFrame, direction: str, main_sweep_level: float) -> dict | None:
        """
        Inducement: a MINOR liquidity grab that happens shortly before
        the main sweep — a small pool of stops taken out first to
        "induce" early entries before the real move. Uses a tighter
        fractal (smaller lookback) than the main swing structure, and
        only counts if the minor pivot sits between current price and
        the main sweep level (i.e. it was taken out on the way to the
        main sweep, not somewhere unrelated).
        """
        minor = self.find_swings(df.copy())
        minor_n = max(2, self.swing_lookback - 3)
        d = df.copy()
        d["minor_high"] = d["high"][
            (d["high"] == d["high"].rolling(2 * minor_n + 1, center=True).max())
        ]
        d["minor_low"] = d["low"][
            (d["low"] == d["low"].rolling(2 * minor_n + 1, center=True).min())
        ]
        recent = d.tail(self.structure_window)
        last = df.iloc[-2]

        if direction == "LONG":
            minor_lows = recent["minor_low"].dropna()
            candidates = [lvl for lvl in minor_lows if lvl > main_sweep_level]
            if not candidates:
                return None
            idm_level = max(candidates)  # nearest minor low above the main sweep
            taken_out = float(last["low"]) < idm_level
        else:
            minor_highs = recent["minor_high"].dropna()
            candidates = [lvl for lvl in minor_highs if lvl < main_sweep_level]
            if not candidates:
                return None
            idm_level = min(candidates)
            taken_out = float(last["high"]) > idm_level

        if taken_out:
            return {"idm_level": float(idm_level)}
        return None

    # ── Multi-swing Fibonacci confluence ─────────────────────────────────
    def multi_leg_ote(self, df: pd.DataFrame, direction: str, price: float) -> dict:
        """
        Instead of a single impulse leg, builds OTE (0.5-0.618) zones
        from the last several swing legs and checks how many overlap
        at the current price — confluence of multiple fib grids is a
        stronger zone than any single one.
        """
        d = self.find_swings(df).tail(self.structure_window)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()

        legs = []
        if direction == "LONG":
            # pair each recent swing low with the swing high that preceded it
            for lo_idx, lo_val in lows.items():
                prior_highs = highs[highs.index < lo_idx]
                if prior_highs.empty:
                    continue
                hi_val = float(prior_highs.iloc[-1])
                if hi_val > lo_val:
                    legs.append((float(lo_val), hi_val))
        else:
            for hi_idx, hi_val in highs.items():
                prior_lows = lows[lows.index < hi_idx]
                if prior_lows.empty:
                    continue
                lo_val = float(prior_lows.iloc[-1])
                if hi_val > lo_val:
                    legs.append((lo_val, float(hi_val)))

        legs = legs[-4:]  # last few legs only — older ones lose relevance
        hits = 0
        for lo, hi in legs:
            rng = hi - lo
            if rng <= 0:
                continue
            fib_50, fib_618 = hi - 0.5 * rng, hi - 0.618 * rng
            zone_lo, zone_hi = sorted([fib_50, fib_618])
            if zone_lo <= price <= zone_hi:
                hits += 1

        return {"legs_checked": len(legs), "confluence_hits": hits}


    def evaluate(self, df: pd.DataFrame, direction: str, price: float) -> dict:
        """
        Runs the full RRCE sequence. Returns a dict describing which
        stages passed and a composite bonus (more stages confirmed =
        higher bonus). Nothing here HARD BLOCKS a signal by default —
        it's additive, same pattern as squeeze_bonus / vp_bonus, so we
        don't collapse signal volume to zero while this gets validated.
        """
        result = {
            "sweep": None, "idm": None, "choch_bos": None, "fvg": [], "ob": None,
            "in_ote": False, "fib_confluence": None, "candle": None,
            "stages_passed": 0, "bonus": 0.0,
        }

        sweep = self.detect_liquidity_sweep(df, direction)
        result["sweep"] = sweep
        if sweep:
            result["stages_passed"] += 1

            # IDM only evaluated relative to a confirmed main sweep level
            idm = self.detect_idm(df, direction, sweep["level"])
            result["idm"] = idm
            if idm:
                result["stages_passed"] += 1

        cb = self.detect_choch_bos(df, direction)
        result["choch_bos"] = cb
        if cb:
            result["stages_passed"] += 2 if cb["bos"] else 1

        fvg = self.detect_fvg(df, direction)
        ob = self.detect_order_block(df, direction)
        result["fvg"] = fvg
        result["ob"] = ob
        if fvg or ob:
            result["stages_passed"] += 1

        if sweep and cb:
            sweep_level = sweep.get("level")
            structure_level = cb.get("bos_level", cb.get("choch_level"))
            if sweep_level and structure_level:
                result["in_ote"] = self.in_ote_zone(price, sweep_level, structure_level)
                if result["in_ote"]:
                    result["stages_passed"] += 1

        # Multi-swing fib confluence — stronger than the single-leg OTE
        # check above; requires at least 2 legs agreeing.
        fib_conf = self.multi_leg_ote(df, direction, price)
        result["fib_confluence"] = fib_conf
        if fib_conf["confluence_hits"] >= 2:
            result["stages_passed"] += 1

        candle = self.candle_confirmation(df, direction)
        result["candle"] = candle
        if candle:
            result["stages_passed"] += 1

        # Bonus scales with how many of the (now up to 8) stages lined
        # up. Full RRCE + IDM + fib confluence is rare and gets the
        # largest bonus; partial confluence still gets something small.
        # Kept comparable in scale to before (max ~15) so this doesn't
        # dwarf squeeze_bonus/vp_bonus in the composite score.
        bonus_table = {0: 0, 1: 1, 2: 3, 3: 5, 4: 7, 5: 9, 6: 11, 7: 13, 8: 15}
        result["bonus"] = bonus_table.get(min(result["stages_passed"], 8), 15)

        return result
