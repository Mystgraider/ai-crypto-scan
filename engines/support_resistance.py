"""
Support & Resistance Engine — V5.5
=====================================
Now REQUIRED for SHORT signals (not optional).

SHORT signals must be near resistance — this gives a defined ceiling
and prevents shorting in open air where a squeeze can run indefinitely.

LONG signals get a bonus if near support (not required, but preferred).

Pivot detection: swing high/low using rolling window of 5 candles each side.
"""

import pandas as pd


class SupportResistanceEngine:

    def __init__(self, pivot_window: int = 5):
        self.window = pivot_window

    def find_levels(self, df: pd.DataFrame) -> dict:

        highs = df["high"].tolist()
        lows  = df["low"].tolist()
        price = float(df["close"].iloc[-1])

        swing_highs = []
        swing_lows  = []
        w = self.window

        for i in range(w, len(highs) - w):
            if highs[i] == max(highs[i - w: i + w + 1]):
                swing_highs.append(highs[i])
            if lows[i] == min(lows[i - w: i + w + 1]):
                swing_lows.append(lows[i])

        supports    = sorted([l for l in swing_lows  if l < price], reverse=True)
        resistances = sorted([h for h in swing_highs if h > price])

        nearest_support    = supports[0]    if supports    else None
        nearest_resistance = resistances[0] if resistances else None

        support_dist_pct    = round(abs(price - nearest_support)    / price * 100, 2) if nearest_support    else None
        resistance_dist_pct = round(abs(nearest_resistance - price) / price * 100, 2) if nearest_resistance else None

        return {
            "price":               round(price, 8),
            "nearest_support":     round(nearest_support, 8)    if nearest_support    else None,
            "nearest_resistance":  round(nearest_resistance, 8) if nearest_resistance else None,
            "support_dist_pct":    support_dist_pct,
            "resistance_dist_pct": resistance_dist_pct,
            "swing_lows":          sorted(swing_lows, reverse=True)[:5],
            "swing_highs":         sorted(swing_highs)[:5],
        }

    def score_bonus(self, direction: str, levels: dict) -> float:
        """Bonus score 0-15 based on proximity to key levels."""

        bonus = 0.0

        if direction == "LONG" and levels["support_dist_pct"] is not None:
            dist = levels["support_dist_pct"]
            if dist <= 1.0:   bonus = 15.0
            elif dist <= 2.0: bonus = 10.0
            elif dist <= 3.0: bonus = 5.0

        elif direction == "SHORT" and levels["resistance_dist_pct"] is not None:
            dist = levels["resistance_dist_pct"]
            if dist <= 1.0:   bonus = 15.0
            elif dist <= 2.0: bonus = 10.0
            elif dist <= 3.0: bonus = 5.0

        return bonus

    def short_has_ceiling(self, levels: dict, max_dist_pct: float = 3.0) -> bool:
        """
        Returns True if there is a resistance level within max_dist_pct above price.
        SHORT signals REQUIRE this — no ceiling = no short.
        """
        if levels["resistance_dist_pct"] is None:
            return False
        return levels["resistance_dist_pct"] <= max_dist_pct
