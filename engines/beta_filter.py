"""
Beta Filter — V6.9.25
=====================
Classifies coins by statistical beta relative to BTC.

Beta is calculated as:
    Cov(asset returns, BTC returns) / Var(BTC returns)

This is directional market beta, not a volatility ratio. A volatility
ratio can be useful as a separate metric, but it must not be labeled beta.
"""

import pandas as pd


KNOWN_HIGH_BETA = {
    "DOGE/USDT:USDT", "SHIB/USDT:USDT", "PEPE/USDT:USDT",
    "BONK/USDT:USDT", "WIF/USDT:USDT", "FLOKI/USDT:USDT",
    "PEOPLE/USDT:USDT", "MOVE/USDT:USDT", "BASED/USDT:USDT",
    "PLUME/USDT:USDT", "SIGN/USDT:USDT", "HUMA/USDT:USDT",
    "MEME/USDT:USDT", "NEIRO/USDT:USDT", "1000SATS/USDT:USDT",
}

PREFERRED_SHORT = {
    "BNB/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
    "BTC/USDT:USDT", "LINK/USDT:USDT", "AVAX/USDT:USDT",
    "DOT/USDT:USDT", "ADA/USDT:USDT", "MATIC/USDT:USDT",
    "UNI/USDT:USDT", "AAVE/USDT:USDT", "MKR/USDT:USDT",
}


class BetaFilter:

    # Production SHORT hard-gate threshold. Kept aligned with config.py.
    HIGH_BETA_THRESHOLD = 1.5
    MEDIUM_BETA_THRESHOLD = 0.8

    def calculate_beta(
        self,
        coin_closes: list[float],
        btc_closes: list[float],
        periods: int = 20,
    ) -> float | None:
        """Calculate statistical beta; return None when beta is unavailable."""
        if periods < 2:
            return None
        if len(coin_closes) < periods + 1 or len(btc_closes) < periods + 1:
            return None

        coin = pd.Series(coin_closes[-(periods + 1):], dtype="float64")
        btc = pd.Series(btc_closes[-(periods + 1):], dtype="float64")
        returns = pd.concat(
            [coin.pct_change().rename("coin"), btc.pct_change().rename("btc")],
            axis=1,
        ).dropna()

        if len(returns) < 2:
            return None

        btc_variance = returns["btc"].var()
        if pd.isna(btc_variance) or btc_variance <= 0:
            return None

        covariance = returns["coin"].cov(returns["btc"])
        if pd.isna(covariance):
            return None

        return round(float(covariance / btc_variance), 3)

    def classify(self, symbol: str, beta: float | None) -> dict:
        """Classify coin beta and determine if SHORT is allowed."""
        # Unavailable beta is supporting evidence, not a hard discovery gate.
        # Do not convert missing/invalid beta data into a fake neutral 1.0 beta.
        if beta is None or pd.isna(beta):
            return {
                "beta": None,
                "beta_label": "UNAVAILABLE",
                "short_ok": True,
                "preferred": False,
                "reason": "Beta unavailable — no beta adjustment",
            }

        # Explicit known high-beta symbols remain a hard SHORT block.
        if symbol in KNOWN_HIGH_BETA:
            return {
                "beta": beta,
                "beta_label": "HIGH",
                "short_ok": False,
                "preferred": False,
                "reason": "Known high-beta coin — SHORT blocked",
            }

        # Measured beta hard gate must take precedence over the preferred list.
        # A preferred symbol is not allowed to override an actually high beta.
        if beta >= self.HIGH_BETA_THRESHOLD:
            return {
                "beta": beta,
                "beta_label": "HIGH",
                "short_ok": False,
                "preferred": False,
                "reason": f"Beta {beta} >= {self.HIGH_BETA_THRESHOLD} — SHORT blocked",
            }

        if symbol in PREFERRED_SHORT:
            return {
                "beta": beta,
                "beta_label": "LOW",
                "short_ok": True,
                "preferred": True,
                "reason": "Preferred short-list coin — SHORT allowed",
            }

        if beta >= self.MEDIUM_BETA_THRESHOLD:
            return {
                "beta": beta,
                "beta_label": "MEDIUM",
                "short_ok": True,
                "preferred": False,
                "reason": f"Beta {beta} — SHORT allowed with caution",
            }

        return {
            "beta": beta,
            "beta_label": "LOW",
            "short_ok": True,
            "preferred": True,
            "reason": f"Beta {beta} < {self.MEDIUM_BETA_THRESHOLD} — SHORT preferred",
        }

    def evaluate(
        self,
        symbol: str,
        direction: str,
        coin_closes: list[float],
        btc_closes: list[float],
    ) -> dict:
        """Full evaluation — calculate beta and classify."""
        beta = self.calculate_beta(coin_closes, btc_closes)
        result = self.classify(symbol, beta)
        if direction == "LONG":
            result["short_ok"] = True
        return result
