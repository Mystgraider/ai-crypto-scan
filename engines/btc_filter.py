"""
BTC Market Filter — Phase 4
============================
Checks the overall BTC market direction before allowing signals.

Rules:
- BTC BULLISH  → allow LONG signals, suppress SHORT signals
- BTC BEARISH  → allow SHORT signals, suppress LONG signals
- BTC RANGING  → allow both but reduce score bonus
- BTC EXTREME  → suppress ALL signals (protect capital)

This is the most important filter for avoiding counter-trend trades.
"""

import pandas as pd


class BTCFilter:

    # Thresholds
    ADX_TREND    = 20    # min ADX for BTC to be considered trending
    RSI_BULL_MIN = 45    # BTC RSI above this = bullish bias
    RSI_BEAR_MAX = 55    # BTC RSI below this = bearish bias
    RSI_EXTREME_HIGH = 80  # overbought — suppress all longs
    RSI_EXTREME_LOW  = 20  # oversold — suppress all shorts

    def analyze(self, df: pd.DataFrame) -> dict:
        """
        Analyze BTC market structure.
        Returns dict with regime, bias, and allow_long/allow_short flags.
        """
        latest = df.iloc[-1]

        price  = float(latest["close"])
        ema20  = float(latest["ema_20"])
        ema50  = float(latest["ema_50"])
        adx    = float(latest["adx"])
        rsi    = float(latest["rsi"])

        # Extreme RSI — protect capital
        if rsi >= self.RSI_EXTREME_HIGH:
            return {
                "regime":      "EXTREME_BULL",
                "bias":        "OVERBOUGHT",
                "allow_long":  False,
                "allow_short": True,
                "adx":         round(adx, 2),
                "rsi":         round(rsi, 2),
            }

        if rsi <= self.RSI_EXTREME_LOW:
            return {
                "regime":      "EXTREME_BEAR",
                "bias":        "OVERSOLD",
                "allow_long":  True,
                "allow_short": False,
                "adx":         round(adx, 2),
                "rsi":         round(rsi, 2),
            }

        # Bullish structure: price > EMA20 > EMA50, ADX trending
        if ema20 > ema50 and price > ema20 and adx >= self.ADX_TREND:
            return {
                "regime":      "BULL",
                "bias":        "BULLISH",
                "allow_long":  True,
                "allow_short": False,   # no counter-trend shorts
                "adx":         round(adx, 2),
                "rsi":         round(rsi, 2),
            }

        # Bearish structure
        if ema20 < ema50 and price < ema20 and adx >= self.ADX_TREND:
            return {
                "regime":      "BEAR",
                "bias":        "BEARISH",
                "allow_long":  False,   # no counter-trend longs
                "allow_short": True,
                "adx":         round(adx, 2),
                "rsi":         round(rsi, 2),
            }

        # Ranging / choppy — allow both but with caution
        return {
            "regime":      "RANGE",
            "bias":        "NEUTRAL",
            "allow_long":  True,
            "allow_short": True,
            "adx":         round(adx, 2),
            "rsi":         round(rsi, 2),
        }
