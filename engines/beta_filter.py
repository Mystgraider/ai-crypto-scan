"""
Beta Filter — V5.8
====================
Classifies coins by their volatility relative to BTC.

High beta coins bounce harder when BTC bounces.
For SHORT signals, high beta = dangerous = likely SL hit.

Beta calculation:
  Compare coin's 20-period price change magnitude vs BTC's.
  Beta = std(coin returns) / std(BTC returns)

  Beta > 1.5 = HIGH  (1.5x more volatile than BTC) → SHORT blocked
  Beta 0.8-1.5 = MEDIUM → SHORT allowed
  Beta < 0.8  = LOW   (less volatile than BTC) → SHORT preferred

Known high-beta coins that should be avoided for SHORT:
  Meme coins: DOGE, SHIB, PEPE, BONK, WIF, FLOKI
  Low cap alts: PEOPLE, MOVE, BASED, PLUME, SIGN, HUMA, BZ
  These are excluded from SHORT regardless of beta calculation
"""

import pandas as pd


KNOWN_HIGH_BETA = {
    "DOGE/USDT:USDT", "SHIB/USDT:USDT", "PEPE/USDT:USDT",
    "BONK/USDT:USDT", "WIF/USDT:USDT",  "FLOKI/USDT:USDT",
    "PEOPLE/USDT:USDT", "MOVE/USDT:USDT", "BASED/USDT:USDT",
    "PLUME/USDT:USDT",  "SIGN/USDT:USDT", "HUMA/USDT:USDT",
    "MEME/USDT:USDT",   "NEIRO/USDT:USDT","1000SATS/USDT:USDT",
}

# Coins consistently profitable for SHORT (lower beta, real fundamentals)
PREFERRED_SHORT = {
    "BNB/USDT:USDT",  "ETH/USDT:USDT",  "SOL/USDT:USDT",
    "BTC/USDT:USDT",  "LINK/USDT:USDT", "AVAX/USDT:USDT",
    "DOT/USDT:USDT",  "ADA/USDT:USDT",  "MATIC/USDT:USDT",
    "UNI/USDT:USDT",  "AAVE/USDT:USDT", "MKR/USDT:USDT",
}


class BetaFilter:

    HIGH_BETA_THRESHOLD   = 1.5
    MEDIUM_BETA_THRESHOLD = 0.8

    def calculate_beta(
        self,
        coin_closes: list[float],
        btc_closes:  list[float],
        periods:     int = 20,
    ) -> float:
        """Calculate realized beta of coin vs BTC."""

        if len(coin_closes) < periods + 1 or len(btc_closes) < periods + 1:
            return 1.0  # assume neutral if not enough data

        coin_returns = pd.Series(coin_closes[-periods:]).pct_change().dropna()
        btc_returns  = pd.Series(btc_closes[-periods:]).pct_change().dropna()

        btc_std = btc_returns.std()

        if btc_std == 0:
            return 1.0

        return round(coin_returns.std() / btc_std, 3)

    def classify(self, symbol: str, beta: float) -> dict:
        """
        Classify coin beta and determine if SHORT is allowed.
        """

        # Known high-beta override
        if symbol in KNOWN_HIGH_BETA:
            return {
                "beta":         beta,
                "beta_label":   "HIGH",
                "short_ok":     False,
                "preferred":    False,
                "reason":       f"Known high-beta coin — SHORT blocked",
            }

        # Preferred LOW beta coins
        if symbol in PREFERRED_SHORT:
            return {
                "beta":         beta,
                "beta_label":   "LOW",
                "short_ok":     True,
                "preferred":    True,
                "reason":       "Preferred low-beta coin — SHORT allowed",
            }

        # Dynamic beta classification
        if beta >= self.HIGH_BETA_THRESHOLD:
            return {
                "beta":         beta,
                "beta_label":   "HIGH",
                "short_ok":     False,
                "preferred":    False,
                "reason":       f"Beta {beta} >= {self.HIGH_BETA_THRESHOLD} — SHORT blocked",
            }

        if beta >= self.MEDIUM_BETA_THRESHOLD:
            return {
                "beta":         beta,
                "beta_label":   "MEDIUM",
                "short_ok":     True,
                "preferred":    False,
                "reason":       f"Beta {beta} — SHORT allowed with caution",
            }

        return {
            "beta":         beta,
            "beta_label":   "LOW",
            "short_ok":     True,
            "preferred":    True,
            "reason":       f"Beta {beta} < {self.MEDIUM_BETA_THRESHOLD} — SHORT preferred",
        }

    def evaluate(
        self,
        symbol:      str,
        direction:   str,
        coin_closes: list[float],
        btc_closes:  list[float],
    ) -> dict:
        """Full evaluation — calculate beta and classify."""

        beta   = self.calculate_beta(coin_closes, btc_closes)
        result = self.classify(symbol, beta)

        # For LONG signals, beta doesn't matter as much
        if direction == "LONG":
            result["short_ok"] = True  # beta doesn't block longs

        return result
