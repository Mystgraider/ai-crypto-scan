"""
Multi-Timeframe Confirmation Engine — Phase 4
==============================================
Confirms 1H signal using 4H trend direction.

Rules:
- 1H LONG  + 4H BULLISH = CONFIRMED (full score)
- 1H SHORT + 4H BEARISH = CONFIRMED (full score)
- 1H LONG  + 4H NEUTRAL = ALLOWED   (reduced score)
- 1H SHORT + 4H NEUTRAL = ALLOWED   (reduced score)
- 1H LONG  + 4H BEARISH = REJECTED  (counter-trend)
- 1H SHORT + 4H BULLISH = REJECTED  (counter-trend)
"""

import pandas as pd


class MultiFrameEngine:

    ADX_MIN = 18  # slightly lower for 4H (slower timeframe)

    def analyze_4h(self, df: pd.DataFrame) -> dict:
        """Analyze 4H candles for trend direction."""

        latest = df.iloc[-1]

        price = float(latest["close"])
        ema20 = float(latest["ema_20"])
        ema50 = float(latest["ema_50"])
        adx   = float(latest["adx"])

        if ema20 > ema50 and price > ema20 and adx >= self.ADX_MIN:
            return {"direction": "BULLISH", "adx": round(adx, 2)}

        if ema20 < ema50 and price < ema20 and adx >= self.ADX_MIN:
            return {"direction": "BEARISH", "adx": round(adx, 2)}

        return {"direction": "NEUTRAL", "adx": round(adx, 2)}

    def confirm(self, signal_direction: str, trend_4h: str) -> dict:
        """
        Cross-check 1H signal vs 4H trend.

        V5.8.3 change: 4H NEUTRAL is now REJECTED for both LONG and SHORT.
        Reason: TAO LONG with 4H NEUTRAL hit SL — no 4H confirmation
        means the higher timeframe does not support the trade.
        Only fire when 4H fully agrees with 1H direction.
        """

        if signal_direction == "LONG":
            if trend_4h == "BULLISH":
                return {"status": "CONFIRMED", "multiplier": 1.10}
            else:  # NEUTRAL or BEARISH — both rejected
                return {"status": "REJECTED",  "multiplier": 0.00}

        else:  # SHORT
            if trend_4h == "BEARISH":
                return {"status": "CONFIRMED", "multiplier": 1.10}
            else:  # NEUTRAL or BULLISH — both rejected
                return {"status": "REJECTED",  "multiplier": 0.00}
