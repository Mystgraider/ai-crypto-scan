"""
Multi-Timeframe Confirmation Engine — V5.9.5
=============================================
Confirms 1H signal using 4H trend direction AND 4H RSI.

Rules:
- 1H LONG  + 4H BULLISH + 4H RSI <= 75 = CONFIRMED (+10% score)
- 1H LONG  + 4H BULLISH + 4H RSI >  75 = ALLOWED   (overbought 4H, risky)
- 1H LONG  + 4H NEUTRAL             = ALLOWED   (no strong bias)
- 1H LONG  + 4H BEARISH             = REJECTED  (counter-trend)

- 1H SHORT + 4H BEARISH + 4H RSI >= 25 = CONFIRMED (+10% score)
- 1H SHORT + 4H BEARISH + 4H RSI <  25 = ALLOWED   (oversold 4H, risky)
- 1H SHORT + 4H NEUTRAL             = ALLOWED
- 1H SHORT + 4H BULLISH             = REJECTED

BAT lesson: 4H RSI 84.27 = overbought on 4H = should have been ALLOWED not CONFIRMED
"""

import pandas as pd


class MultiFrameEngine:

    ADX_MIN = 18

    # 4H RSI extremes — reduce confidence when 4H is overbought/oversold
    RSI_OVERBOUGHT_4H  = 75   # above this = risky for LONG
    RSI_OVERSOLD_4H    = 25   # below this = risky for SHORT

    def analyze_4h(self, df: pd.DataFrame) -> dict:
        """Analyze 4H candles for trend direction and RSI."""

        latest = df.iloc[-1]

        price = float(latest["close"])
        ema20 = float(latest["ema_20"])
        ema50 = float(latest["ema_50"])
        adx   = float(latest["adx"])
        rsi   = float(latest["rsi"]) if "rsi" in latest.index else 50.0

        if ema20 > ema50 and price > ema20 and adx >= self.ADX_MIN:
            return {"direction": "BULLISH", "adx": round(adx, 2), "rsi": round(rsi, 2)}

        if ema20 < ema50 and price < ema20 and adx >= self.ADX_MIN:
            return {"direction": "BEARISH", "adx": round(adx, 2), "rsi": round(rsi, 2)}

        return {"direction": "NEUTRAL", "adx": round(adx, 2), "rsi": round(rsi, 2)}

    def confirm(self, signal_direction: str, trend_4h: str, rsi_4h: float = 50.0) -> dict:
        """
        Cross-check 1H signal vs 4H trend + RSI.
        4H RSI overbought/oversold = downgrade to ALLOWED even if trend confirms.
        """

        if signal_direction == "LONG":
            if trend_4h == "BULLISH":
                # Check 4H RSI — if overbought, downgrade confidence
                if rsi_4h > self.RSI_OVERBOUGHT_4H:
                    return {"status": "ALLOWED", "multiplier": 0.95,
                            "note": f"4H RSI {rsi_4h} overbought"}
                return {"status": "CONFIRMED", "multiplier": 1.10}
            elif trend_4h == "NEUTRAL":
                return {"status": "ALLOWED",  "multiplier": 1.00}
            else:
                return {"status": "REJECTED", "multiplier": 0.00}

        else:  # SHORT
            if trend_4h == "BEARISH":
                if rsi_4h < self.RSI_OVERSOLD_4H:
                    return {"status": "ALLOWED", "multiplier": 0.95,
                            "note": f"4H RSI {rsi_4h} oversold"}
                return {"status": "CONFIRMED", "multiplier": 1.10}
            elif trend_4h == "NEUTRAL":
                return {"status": "ALLOWED",  "multiplier": 1.00}
            else:
                return {"status": "REJECTED", "multiplier": 0.00}
