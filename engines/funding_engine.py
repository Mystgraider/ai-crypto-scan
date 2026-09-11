"""
Funding Rate Engine — V6.9.25
=============================
Checks perpetual-swap funding before allowing signals.

The scanner's existing fetch_funding() contract returns a numeric funding
rate. To preserve that interface, unavailable data is represented by NaN and
analyze() converts that sentinel into an explicit UNAVAILABLE result. A real
0.0 funding rate remains a valid observation.
"""

import math
import ccxt


class FundingEngine:

    SHORT_BLOCK_ABOVE = 0.0001   # +0.01%
    LONG_BLOCK_BELOW = -0.0005   # -0.05%
    SHORT_IDEAL_BELOW = 0.0000   # 0% or negative

    def analyze(self, funding_rate: float) -> dict:
        """Analyze a known funding-rate observation or unavailable sentinel."""
        try:
            funding_rate = float(funding_rate)
        except (TypeError, ValueError):
            funding_rate = float("nan")

        if math.isnan(funding_rate):
            return {
                "available": False,
                "funding_rate": None,
                "funding_pct": None,
                "long_ok": False,
                "short_ok": False,
                "long_msg": "Funding unavailable — LONG blocked",
                "short_msg": "Funding unavailable — SHORT blocked",
                "short_score_adj": 0,
                "reason": "funding_unavailable",
            }

        pct = round(funding_rate * 100, 4)

        if funding_rate < self.LONG_BLOCK_BELOW:
            long_ok = False
            long_msg = f"Funding {pct}% too negative — crowded shorts, squeeze risk for LONG"
        else:
            long_ok = True
            long_msg = f"Funding {pct}% OK for LONG"

        if funding_rate > self.SHORT_BLOCK_ABOVE:
            short_ok = False
            short_msg = f"Funding {pct}% positive — crowded longs, squeeze risk for SHORT"
        else:
            short_ok = True
            if funding_rate <= self.SHORT_IDEAL_BELOW:
                short_msg = f"Funding {pct}% ideal for SHORT (negative/neutral)"
            else:
                short_msg = f"Funding {pct}% OK for SHORT"

        if funding_rate <= -0.0003:
            short_score_adj = -10
        elif funding_rate <= 0.0000:
            short_score_adj = +5
        elif funding_rate <= self.SHORT_BLOCK_ABOVE:
            short_score_adj = 0
        else:
            short_score_adj = -999

        return {
            "available": True,
            "funding_rate": funding_rate,
            "funding_pct": pct,
            "long_ok": long_ok,
            "short_ok": short_ok,
            "long_msg": long_msg,
            "short_msg": short_msg,
            "short_score_adj": short_score_adj,
        }

    def fetch_funding(self, exchange, symbol: str) -> float:
        """Fetch funding rate; return NaN when the observation is unavailable."""
        try:
            data = exchange.fetch_funding_rate(symbol)
            raw_rate = data.get("fundingRate")
            if raw_rate is None:
                raw_rate = data.get("info", {}).get("fundingRate")
            if raw_rate is None:
                return float("nan")
            return float(raw_rate)

        except ccxt.BadSymbol:
            return float("nan")
        except ccxt.NetworkError as e:
            print(f"  ⚠️  Funding network error {symbol}: {e}")
            return float("nan")
        except Exception as e:
            print(f"  ⚠️  Funding fetch failed {symbol}: {e}")
            return float("nan")
