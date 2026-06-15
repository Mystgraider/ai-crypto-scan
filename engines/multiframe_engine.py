"""
Multi-Timeframe Confirmation Engine — V6.0
============================================
Upgrades from V5.9.5:
- Added 15M timeframe as entry precision layer
- MACD confirmation on 4H (not just EMA structure)
- Stoch RSI check on 4H (overbought/oversold)
- Tiered multipliers: CONFIRMED_STRONG (1.15) vs CONFIRMED (1.10)
- 15M misalignment = penalty (prevents bad entries)

Confirmation hierarchy:
  1H direction → 4H confirms/rejects → 15M refines entry

Multipliers:
  CONFIRMED_STRONG  (4H + 15M aligned)      = 1.15
  CONFIRMED         (4H aligned)             = 1.10
  ALLOWED           (4H neutral/risky)       = 1.00
  ALLOWED_WEAK      (4H ok but 15M against)  = 0.92
  REJECTED          (counter-trend)          = 0.00
"""

import pandas as pd


class MultiFrameEngine:

    ADX_MIN = 18

    RSI_OVERBOUGHT_4H = 75
    RSI_OVERSOLD_4H   = 25
    STOCH_OB_4H       = 80   # new: stoch RSI overbought on 4H
    STOCH_OS_4H       = 20   # new: stoch RSI oversold on 4H

    def analyze_4h(self, df: pd.DataFrame) -> dict:
        if len(df) < 2:
            return {"direction": "NEUTRAL", "adx": 0.0, "rsi": 50.0,
                    "macd_bull": None, "stoch_k": 50.0}

        live = df.iloc[-1]    # forming 4H candle — live price only
        prev = df.iloc[-2]    # last closed 4H candle — indicators

        price    = float(live["close"])
        ema20    = float(prev["ema_20"])
        ema50    = float(prev["ema_50"])
        adx      = float(prev["adx"])
        rsi      = float(prev["rsi"])   if "rsi"      in prev.index else 50.0
        macd     = float(prev["macd"])  if "macd"     in prev.index else 0.0
        macd_sig = float(prev["macd_sig"]) if "macd_sig" in prev.index else 0.0
        stoch_k  = float(prev["stoch_k"])  if "stoch_k"  in prev.index else 50.0

        if ema20 > ema50 and price > ema20 and adx >= self.ADX_MIN:
            return {
                "direction": "BULLISH", "adx": round(adx, 2), "rsi": round(rsi, 2),
                "macd_bull": macd > macd_sig, "stoch_k": round(stoch_k, 2),
            }
        if ema20 < ema50 and price < ema20 and adx >= self.ADX_MIN:
            return {
                "direction": "BEARISH", "adx": round(adx, 2), "rsi": round(rsi, 2),
                "macd_bull": macd > macd_sig, "stoch_k": round(stoch_k, 2),
            }

        return {
            "direction": "NEUTRAL", "adx": round(adx, 2), "rsi": round(rsi, 2),
            "macd_bull": None, "stoch_k": round(stoch_k, 2),
        }

    def analyze_15m(self, df: pd.DataFrame) -> dict:
        """15M: entry precision — are we aligned on the lower timeframe?"""
        if len(df) < 2:
            return {"direction": "NEUTRAL", "adx": 0.0}

        live = df.iloc[-1]    # forming 15M candle — live price only
        prev = df.iloc[-2]    # last closed 15M candle — indicators

        price = float(live["close"])
        ema20 = float(prev["ema_20"])
        ema50 = float(prev["ema_50"])
        adx   = float(prev["adx"])

        if ema20 > ema50 and price > ema20:
            return {"direction": "BULLISH", "adx": round(adx, 2)}
        if ema20 < ema50 and price < ema20:
            return {"direction": "BEARISH", "adx": round(adx, 2)}
        return {"direction": "NEUTRAL", "adx": round(adx, 2)}

    def confirm(self, signal_direction: str, trend_4h: dict, trend_15m: dict = None) -> dict:

        dir_4h   = trend_4h.get("direction", "NEUTRAL")
        rsi_4h   = trend_4h.get("rsi", 50.0)
        stoch_4h = trend_4h.get("stoch_k", 50.0)
        macd_bull= trend_4h.get("macd_bull", None)
        dir_15m  = trend_15m.get("direction", "NEUTRAL") if trend_15m else "NEUTRAL"

        if signal_direction == "LONG":

            if dir_4h == "BULLISH":
                # Risky if 4H overbought
                if rsi_4h > self.RSI_OVERBOUGHT_4H or stoch_4h > self.STOCH_OB_4H:
                    return {"status": "ALLOWED", "multiplier": 0.95,
                            "note": f"4H RSI:{rsi_4h} StochK:{stoch_4h} overbought"}

                # MACD aligned + 15M aligned = strongest confirmation
                macd_ok = macd_bull is True or macd_bull is None
                if macd_ok and dir_15m == "BULLISH":
                    return {"status": "CONFIRMED_STRONG", "multiplier": 1.15,
                            "note": "4H+MACD+15M all bullish"}

                # 4H confirmed but 15M not aligned
                if macd_ok:
                    if dir_15m == "BEARISH":
                        return {"status": "ALLOWED_WEAK", "multiplier": 0.92,
                                "note": "4H confirmed but 15M counter-trend"}
                    return {"status": "CONFIRMED", "multiplier": 1.10}

                # MACD bearish on 4H even if EMA bullish — downgrade
                return {"status": "ALLOWED", "multiplier": 0.97,
                        "note": "4H EMA bull but MACD bearish"}

            elif dir_4h == "NEUTRAL":
                if dir_15m == "BULLISH":
                    return {"status": "ALLOWED", "multiplier": 1.02,
                            "note": "4H neutral, 15M confirms"}
                return {"status": "ALLOWED", "multiplier": 1.00}
            else:
                return {"status": "REJECTED", "multiplier": 0.00}

        else:  # SHORT

            if dir_4h == "BEARISH":
                if rsi_4h < self.RSI_OVERSOLD_4H or stoch_4h < self.STOCH_OS_4H:
                    return {"status": "ALLOWED", "multiplier": 0.95,
                            "note": f"4H RSI:{rsi_4h} StochK:{stoch_4h} oversold"}

                macd_ok = macd_bull is False or macd_bull is None
                if macd_ok and dir_15m == "BEARISH":
                    return {"status": "CONFIRMED_STRONG", "multiplier": 1.15,
                            "note": "4H+MACD+15M all bearish"}

                if macd_ok:
                    if dir_15m == "BULLISH":
                        return {"status": "ALLOWED_WEAK", "multiplier": 0.92,
                                "note": "4H confirmed but 15M counter-trend"}
                    return {"status": "CONFIRMED", "multiplier": 1.10}

                return {"status": "ALLOWED", "multiplier": 0.97,
                        "note": "4H EMA bear but MACD bullish"}

            elif dir_4h == "NEUTRAL":
                if dir_15m == "BEARISH":
                    return {"status": "ALLOWED", "multiplier": 1.02,
                            "note": "4H neutral, 15M confirms"}
                return {"status": "ALLOWED", "multiplier": 1.00}
            else:
                return {"status": "REJECTED", "multiplier": 0.00}
