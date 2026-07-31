"""
Volume Profile Zone Engine — V6.6
===================================
Concept observed from external chart review: instead of plain swing-point
S/R (which only looks at price pivots), mark zones where the MOST VOLUME
was historically traded — "High Volume Nodes" (HVN). These zones tend to
act as stronger support/resistance than simple swing highs/lows because
they represent actual traded interest, not just a single wick.

Also marks "Low Volume Nodes" (LVN) — thin zones where price historically
moved through quickly. Price tends to move fast through LVNs and slow
down / react at HVNs.

This does not replace the existing swing-based SupportResistanceEngine —
it's a second, independent lens. Both can contribute bonus points.
"""

import numpy as np
import pandas as pd


class VolumeProfileEngine:

    def __init__(self, bins: int = 24, lookback: int = 200):
        self.bins = bins
        self.lookback = lookback

    def build_profile(self, df: pd.DataFrame) -> dict | None:
        """
        Bins the price range of the lookback window and sums volume
        traded at each price level (using each candle's typical price:
        (H+L+C)/3, weighted by that candle's volume).
        """
        d = df.tail(self.lookback)
        if len(d) < 20:
            return None

        lo = float(d["low"].min())
        hi = float(d["high"].max())
        if hi <= lo:
            return None

        typical = (d["high"] + d["low"] + d["close"]) / 3.0
        vol = d["volume"]

        edges = np.linspace(lo, hi, self.bins + 1)
        bin_idx = np.clip(np.digitize(typical, edges) - 1, 0, self.bins - 1)

        vol_by_bin = np.zeros(self.bins)
        for idx, v in zip(bin_idx, vol):
            vol_by_bin[idx] += v

        total_vol = vol_by_bin.sum()
        if total_vol <= 0:
            return None

        bin_centers = (edges[:-1] + edges[1:]) / 2.0
        poc_idx = int(np.argmax(vol_by_bin))
        poc_price = float(bin_centers[poc_idx])

        # High Volume Nodes = bins with volume share notably above average
        avg_share = 1.0 / self.bins
        hvn_mask = (vol_by_bin / total_vol) >= (avg_share * 1.5)
        hvn_prices = sorted(float(p) for p in bin_centers[hvn_mask])

        # Low Volume Nodes = thin zones (below half the average share)
        lvn_mask = (vol_by_bin / total_vol) <= (avg_share * 0.5)
        lvn_prices = sorted(float(p) for p in bin_centers[lvn_mask])

        return {
            "poc":         round(poc_price, 8),
            "hvn_levels":  [round(p, 8) for p in hvn_prices],
            "lvn_levels":  [round(p, 8) for p in lvn_prices],
            "range_low":   round(lo, 8),
            "range_high":  round(hi, 8),
        }

    def nearest_hvn(self, price: float, profile: dict, direction: str):
        """Nearest HVN below price (support, for LONG) or above (resistance, for SHORT)."""
        if not profile:
            return None, None
        levels = profile["hvn_levels"]
        if direction == "LONG":
            below = [l for l in levels if l < price]
            if not below:
                return None, None
            nearest = max(below)
        else:
            above = [l for l in levels if l > price]
            if not above:
                return None, None
            nearest = min(above)
        dist_pct = round(abs(price - nearest) / price * 100, 2)
        return nearest, dist_pct

    def score_bonus(self, direction: str, price: float, profile: dict) -> float:
        """
        Bonus for being near a High Volume Node in the favorable direction
        (near HVN support for LONG, near HVN resistance for SHORT) —
        mirrors the "reaction zone" markings seen in the reference charts.
        Also a small bonus if price is currently inside a Low Volume Node
        (thin zone) — likely to move quickly through, i.e. still early,
        not already extended into a high-traffic area.
        """
        if not profile:
            return 0.0

        bonus = 0.0
        _, dist_pct = self.nearest_hvn(price, profile, direction)
        if dist_pct is not None:
            if dist_pct <= 1.0:   bonus += 8.0
            elif dist_pct <= 2.5: bonus += 5.0
            elif dist_pct <= 4.0: bonus += 2.0

        lvn_levels = profile.get("lvn_levels", [])
        if lvn_levels:
            rng = profile["range_high"] - profile["range_low"]
            if rng > 0:
                for lvn in lvn_levels:
                    if abs(price - lvn) / rng < 0.02:
                        bonus += 3.0
                        break

        return round(bonus, 2)
