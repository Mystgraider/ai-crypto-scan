"""
BTC Market Filter — V5.9.6
============================
Fixed BEAR_CAUTION: was blocking ALL signals when BTC RSI < 42.
In a real BEAR market, BTC RSI stays 35-42 for days/weeks.
This made the system silent for extended periods.

New logic:
  BEAR_CAUTION: only block LONG signals (not SHORT)
  BTC RSI 35-42 + bearish structure = still valid for SHORT
  
  Only block ALL signals when:
  - RSI < 25 (extreme oversold = big bounce imminent)
  - Or 4H structure not confirmed bearish (counter-trend risk)
"""

import pandas as pd


class BTCFilter:

    ADX_MIN          = 20
    RSI_BLOCK_SHORT  = 42    # block SHORT if BTC RSI < 42 originally
    RSI_EXTREME_LOW  = 25    # extreme oversold = block ALL (was 22)
    RSI_EXTREME_HIGH = 80
    RSI_BLOCK_LONG   = 72

    def analyze(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame = None) -> dict:

        latest = df_1h.iloc[-1]
        price  = float(latest["close"])
        ema20  = float(latest["ema_20"])
        ema50  = float(latest["ema_50"])
        adx    = float(latest["adx"])
        rsi    = float(latest["rsi"])

        # 4H structure check
        btc_4h_bear = False
        btc_4h_bull = False
        if df_4h is not None and len(df_4h) > 0:
            try:
                l4   = df_4h.iloc[-1]
                p4   = float(l4["close"])
                e20  = float(l4["ema_20"])
                e50  = float(l4["ema_50"])
                adx4 = float(l4["adx"])
                btc_4h_bear = e20 < e50 and p4 < e20 and adx4 >= self.ADX_MIN
                btc_4h_bull = e20 > e50 and p4 > e20 and adx4 >= self.ADX_MIN
            except Exception:
                pass

        # Extreme oversold — imminent big bounce, block ALL
        if rsi <= self.RSI_EXTREME_LOW:
            return self._r("EXTREME_BEAR", adx, rsi,
                           allow_long=False, allow_short=False,
                           reason=f"BTC RSI {rsi:.1f} extreme oversold — bounce imminent, no signals")

        # Extreme overbought — block all longs
        if rsi >= self.RSI_EXTREME_HIGH:
            return self._r("EXTREME_BULL", adx, rsi,
                           allow_long=False, allow_short=True,
                           reason=f"BTC RSI {rsi:.1f} extreme overbought")

        # BULL structure
        if ema20 > ema50 and price > ema20 and adx >= self.ADX_MIN:
            if rsi > self.RSI_BLOCK_LONG:
                return self._r("BULL_CAUTION", adx, rsi,
                               allow_long=False, allow_short=False,
                               reason=f"BTC BULL but RSI {rsi:.1f} > {self.RSI_BLOCK_LONG}")
            return self._r("BULL", adx, rsi,
                           allow_long=True, allow_short=False,
                           reason="BTC bullish structure confirmed")

        # BEAR structure
        if ema20 < ema50 and price < ema20 and adx >= self.ADX_MIN:

            # 4H also bearish = full confirmation
            if btc_4h_bear:
                if rsi < self.RSI_BLOCK_SHORT:
                    # FIXED: Previously blocked ALL signals when RSI < 42
                    # Now: only block LONG, allow SHORT (BEAR market)
                    return self._r("BEAR_CAUTION", adx, rsi,
                                   allow_long=False, allow_short=True,
                                   reason=f"BTC BEAR + 4H confirmed. RSI {rsi:.1f} low but SHORT allowed")
                return self._r("BEAR", adx, rsi,
                               allow_long=False, allow_short=True,
                               reason="BTC bearish confirmed 1H + 4H")

            # 1H bear but 4H not confirmed
            if rsi < self.RSI_BLOCK_SHORT:
                return self._r("BEAR_CAUTION", adx, rsi,
                               allow_long=False, allow_short=False,
                               reason=f"BTC 1H bear but 4H unconfirmed + RSI {rsi:.1f} low")
            return self._r("BEAR_UNCONFIRMED", adx, rsi,
                           allow_long=False, allow_short=False,
                           reason="BTC 1H bear but 4H not confirmed — wait")

        # Ranging
        return self._r("RANGE", adx, rsi,
                       allow_long=True, allow_short=True,
                       reason="BTC ranging — signals allowed at key S/R")

    @staticmethod
    def _r(regime, adx, rsi, allow_long, allow_short, reason=""):
        return {
            "regime":      regime,
            "allow_long":  allow_long,
            "allow_short": allow_short,
            "adx":         round(adx, 2),
            "rsi":         round(rsi, 2),
            "reason":      reason,
        }
