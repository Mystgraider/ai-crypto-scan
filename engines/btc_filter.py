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
