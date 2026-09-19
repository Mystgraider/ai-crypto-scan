""" 
BTC Market Filter — V5.9.6
============================
Fail-closed BTC safety context.

BTC is market context only, not a signal generator.
If BTC market data is unavailable or insufficient, the filter returns
UNKNOWN and blocks both LONG and SHORT signals.

Normal BULL/BEAR regimes remain context only: they do not select a coin
signal direction. Direction-specific discovery is handled downstream.
"""

import pandas as pd


class BTCFilter:

    ADX_MIN          = 20
    RSI_BLOCK_SHORT  = 42
    RSI_EXTREME_LOW  = 25
    RSI_EXTREME_HIGH = 80
    RSI_BLOCK_LONG   = 72

    def analyze(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame = None) -> dict:
        """Analyze BTC regime; unexpected analysis errors fail closed."""
        try:
            return self._analyze(df_1h, df_4h)
        except Exception as exc:
            return self._r(
                "UNKNOWN", 0, 50,
                allow_long=False,
                allow_short=False,
                reason=f"BTC filter analysis failed ({type(exc).__name__}) — no signals",
            )

    def _analyze(self, df_1h: pd.DataFrame, df_4h: pd.DataFrame = None) -> dict:
        # Fail closed for explicit loader fallback or insufficient BTC data.
        if bool(getattr(df_1h, "attrs", {}).get("btc_data_unavailable", False)):
            return self._r(
                "UNKNOWN", 0, 50, allow_long=False, allow_short=False,
                reason="BTC market data unavailable — no signals",
            )

        if len(df_1h) < 2:
            return self._r(
                "UNKNOWN", 0, 50, allow_long=False, allow_short=False,
                reason="Insufficient BTC 1H data — no signals",
            )

        live = df_1h.iloc[-1]
        prev = df_1h.iloc[-2]

        price = float(live["close"])
        ema20 = float(prev["ema_20"])
        ema50 = float(prev["ema_50"])
        adx = float(prev["adx"])
        rsi = float(prev["rsi"])

        btc_4h_bear = False
        btc_4h_bull = False
        if df_4h is not None and len(df_4h) >= 2:
            try:
                l4 = df_4h.iloc[-1]
                p4_prev = df_4h.iloc[-2]
                p4 = float(l4["close"])
                e20 = float(p4_prev["ema_20"])
                e50 = float(p4_prev["ema_50"])
                adx4 = float(p4_prev["adx"])
                btc_4h_bear = e20 < e50 and p4 < e20 and adx4 >= self.ADX_MIN
                btc_4h_bull = e20 > e50 and p4 > e20 and adx4 >= self.ADX_MIN
            except Exception:
                pass

        if rsi <= self.RSI_EXTREME_LOW:
            return self._r(
                "EXTREME_BEAR", adx, rsi,
                allow_long=False, allow_short=False,
                reason=f"BTC RSI {rsi:.1f} extreme oversold — bounce imminent, no signals",
            )

        if rsi >= self.RSI_EXTREME_HIGH:
            return self._r(
                "EXTREME_BULL", adx, rsi,
                allow_long=False, allow_short=True,
                reason=f"BTC RSI {rsi:.1f} extreme overbought",
            )

        if ema20 > ema50 and price > ema20 and adx >= self.ADX_MIN:
            if rsi > self.RSI_BLOCK_LONG:
                return self._r(
                    "BULL_CAUTION", adx, rsi,
                    allow_long=False, allow_short=True,
                    reason=f"BTC BULL but RSI {rsi:.1f} > {self.RSI_BLOCK_LONG}",
                )
            return self._r(
                "BULL", adx, rsi,
                allow_long=True, allow_short=True,
                reason="BTC bullish structure confirmed — context only",
            )

        if ema20 < ema50 and price < ema20 and adx >= self.ADX_MIN:
            if btc_4h_bear:
                if rsi < self.RSI_BLOCK_SHORT:
                    return self._r(
                        "BEAR_CAUTION", adx, rsi,
                        allow_long=True, allow_short=True,
                        reason=f"BTC BEAR + 4H confirmed. RSI {rsi:.1f} low — coin direction independent",
                    )
                return self._r(
                    "BEAR", adx, rsi,
                    allow_long=True, allow_short=True,
                    reason="BTC bearish confirmed 1H + 4H — context only",
                )

            if rsi < self.RSI_BLOCK_SHORT:
                return self._r(
                    "BEAR_CAUTION", adx, rsi,
                    allow_long=True, allow_short=True,
                    reason=f"BTC 1H bear but 4H unconfirmed + RSI {rsi:.1f} low — context only",
                )
            return self._r(
                "BEAR_UNCONFIRMED", adx, rsi,
                allow_long=True, allow_short=True,
                reason="BTC 1H bear but 4H not confirmed — context only",
            )

        return self._r(
            "RANGE", adx, rsi,
            allow_long=True, allow_short=True,
            reason="BTC ranging — signals allowed at key S/R",
        )

    @staticmethod
    def _r(regime, adx, rsi, allow_long, allow_short, reason=""):
        return {
            "regime": regime,
            "allow_long": allow_long,
            "allow_short": allow_short,
            "adx": round(adx, 2),
            "rsi": round(rsi, 2),
            "reason": reason,
        }
