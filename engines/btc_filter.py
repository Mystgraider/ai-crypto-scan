"""
BTC Market Filter — V5.5
==========================
Enhanced with anti-SL-hit protections for SHORT signals.

Key problem solved:
  BTC BEAR on 1H but bouncing → alts bounce harder (higher beta)
  → Short SL hit on bounce even though overall trend is down

Solutions added:
  1. BTC 4H must ALSO be bearish for SHORT signals
     (1H bear + 4H bull = bounce in progress, wrong time to short)
  2. Block SHORT when BTC RSI < 42
     (RSI < 42 = already low = bounce imminent = dangerous to short)
  3. Block LONG when BTC RSI > 72
     (RSI > 72 = already high = pullback imminent = dangerous to long)

Regime logic:
  BULL  → LONG only
  BEAR  → SHORT only, but only if RSI >= 42 AND 4H also bearish
  RANGE → both allowed but only near key S/R levels
  CAUTION_BEAR → 1H bear but 4H not confirmed OR RSI < 42 → no signals
"""

import pandas as pd


class BTCFilter:

    ADX_MIN          = 20
    RSI_BLOCK_SHORT  = 42   # below this = bounce risk, block shorts
    RSI_BLOCK_LONG   = 72   # above this = pullback risk, block longs
    RSI_EXTREME_LOW  = 22   # deep oversold = block shorts completely
    RSI_EXTREME_HIGH = 80   # deep overbought = block longs completely

    def analyze(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame = None) -> dict:

        latest_1h = df_1h.iloc[-1]

        price_1h = float(latest_1h["close"])
        ema20_1h = float(latest_1h["ema_20"])
        ema50_1h = float(latest_1h["ema_50"])
        adx_1h   = float(latest_1h["adx"])
        rsi_1h   = float(latest_1h["rsi"])

        # ── 4H structure ──────────────────────────────────────────────
        btc_4h_bear = False
        btc_4h_bull = False

        if df_4h is not None and len(df_4h) > 0:
            latest_4h = df_4h.iloc[-1]
            p4   = float(latest_4h["close"])
            e20  = float(latest_4h["ema_20"])
            e50  = float(latest_4h["ema_50"])
            adx4 = float(latest_4h["adx"])
            btc_4h_bear = e20 < e50 and p4 < e20 and adx4 >= self.ADX_MIN
            btc_4h_bull = e20 > e50 and p4 > e20 and adx4 >= self.ADX_MIN

        # ── Extreme RSI — protect capital ────────────────────────────
        if rsi_1h <= self.RSI_EXTREME_LOW:
            return self._result("EXTREME_BEAR", adx_1h, rsi_1h,
                                allow_long=True, allow_short=False,
                                reason="BTC RSI extreme oversold — bounce imminent")

        if rsi_1h >= self.RSI_EXTREME_HIGH:
            return self._result("EXTREME_BULL", adx_1h, rsi_1h,
                                allow_long=False, allow_short=True,
                                reason="BTC RSI extreme overbought — pullback imminent")

        # ── BULL market ───────────────────────────────────────────────
        if ema20_1h > ema50_1h and price_1h > ema20_1h and adx_1h >= self.ADX_MIN:

            # Block longs near overbought
            if rsi_1h > self.RSI_BLOCK_LONG:
                return self._result("BULL_CAUTION", adx_1h, rsi_1h,
                                    allow_long=False, allow_short=False,
                                    reason=f"BTC BULL but RSI {rsi_1h:.1f} > {self.RSI_BLOCK_LONG} — pullback risk")

            return self._result("BULL", adx_1h, rsi_1h,
                                allow_long=True, allow_short=False,
                                reason="BTC bullish structure confirmed")

        # ── BEAR market ───────────────────────────────────────────────
        if ema20_1h < ema50_1h and price_1h < ema20_1h and adx_1h >= self.ADX_MIN:

            # Block shorts when RSI already low (bounce imminent)
            if rsi_1h < self.RSI_BLOCK_SHORT:
                return self._result("BEAR_CAUTION", adx_1h, rsi_1h,
                                    allow_long=False, allow_short=False,
                                    reason=f"BTC BEAR but RSI {rsi_1h:.1f} < {self.RSI_BLOCK_SHORT} — dead cat bounce risk")

            # Block shorts when 4H is NOT also bearish
            # (1H bear + 4H neutral/bull = likely a bounce on 1H, not trend)
            if not btc_4h_bear:
                return self._result("BEAR_CAUTION", adx_1h, rsi_1h,
                                    allow_long=False, allow_short=False,
                                    reason="BTC 1H BEAR but 4H not confirmed — bounce likely")

            # Full bear confirmation: 1H bear + 4H bear + RSI >= 42
            return self._result("BEAR", adx_1h, rsi_1h,
                                allow_long=False, allow_short=True,
                                reason="BTC bearish confirmed on 1H + 4H")

        # ── Ranging ───────────────────────────────────────────────────
        return self._result("RANGE", adx_1h, rsi_1h,
                            allow_long=True, allow_short=True,
                            reason="BTC ranging — signals allowed near key S/R only")

    @staticmethod
    def _result(regime, adx, rsi, allow_long, allow_short, reason=""):
        return {
            "regime":       regime,
            "allow_long":   allow_long,
            "allow_short":  allow_short,
            "adx":          round(adx, 2),
            "rsi":          round(rsi, 2),
            "reason":       reason,
        }
