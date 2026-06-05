"""
Support & Resistance Engine — Phase 5
=======================================
Detects key S/R levels from recent swing highs/lows.

Used to:
1. Tighten SL when price is near a support level (LONG)
   or resistance level (SHORT) — better risk management
2. Confirm breakout: signal near a key level = higher conviction
3. Score bonus when price just broke through S/R

Method: pivot point detection using rolling windows.
A swing high = candle whose high is the highest in N candles around it.
A swing low  = candle whose low  is the lowest  in N candles around it.
"""

import pandas as pd


class SupportResistanceEngine:

    def __init__(self, pivot_window: int = 5):
        # Number of candles on each side to confirm a pivot
        self.window = pivot_window

    def find_levels(self, df: pd.DataFrame) -> dict:
        """
        Find key S/R levels from swing highs/lows.
        Returns nearest support below and resistance above current price.
        """

        highs = df["high"].tolist()
        lows  = df["low"].tolist()
        price = float(df["close"].iloc[-1])

        swing_highs = []
        swing_lows  = []

        w = self.window

        for i in range(w, len(highs) - w):

            # Swing high: highest in window
            if highs[i] == max(highs[i - w: i + w + 1]):
                swing_highs.append(highs[i])

            # Swing low: lowest in window
            if lows[i] == min(lows[i - w: i + w + 1]):
                swing_lows.append(lows[i])

        # Nearest support (swing low below current price)
        supports = sorted([l for l in swing_lows if l < price], reverse=True)
        # Nearest resistance (swing high above current price)
        resistances = sorted([h for h in swing_highs if h > price])

        nearest_support    = supports[0]    if supports    else None
        nearest_resistance = resistances[0] if resistances else None

        # Distance % from current price
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
        """
        Bonus score (0-15) based on S/R proximity and alignment.

        LONG near support = high bonus (good entry)
        SHORT near resistance = high bonus (good entry)
        LONG near resistance = 0 bonus (bad entry, hitting ceiling)
        SHORT near support = 0 bonus (bad entry, hitting floor)
        """

        bonus = 0.0

        if direction == "LONG" and levels["support_dist_pct"] is not None:
            dist = levels["support_dist_pct"]
            if dist <= 1.0:
                bonus = 15.0   # very close to support = excellent entry
            elif dist <= 2.0:
                bonus = 10.0
            elif dist <= 3.0:
                bonus = 5.0

        elif direction == "SHORT" and levels["resistance_dist_pct"] is not None:
            dist = levels["resistance_dist_pct"]
            if dist <= 1.0:
                bonus = 15.0   # very close to resistance = excellent entry
            elif dist <= 2.0:
                bonus = 10.0
            elif dist <= 3.0:
                bonus = 5.0

        return bonus
