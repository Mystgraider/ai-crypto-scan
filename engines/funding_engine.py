"""
Funding Rate Engine — V6.9.25
=============================
Checks perpetual-swap funding before allowing signals.

Unavailable funding is represented explicitly. It is never converted into
0.0, because zero funding is a real market observation while an API failure
is missing data.
"""

import ccxt


class FundingEngine:

    SHORT_BLOCK_ABOVE = 0.0001   # +0.01%
    LONG_BLOCK_BELOW = -0.0005   # -0.05%
    SHORT_IDEAL_BELOW = 0.0000   # 0% or negative

    def analyze(self, funding_rate: float) -> dict:
        """Analyze a known funding-rate observation."""
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

    def fetch_funding(self, exchange, symbol: str) -> dict:
        """
        Fetch current funding rate from the exchange.

        Returns a structured result so an API failure cannot masquerade as
        a legitimate 0.0 funding observation.
        """
        try:
            data = exchange.fetch_funding_rate(symbol)
            raw_rate = data.get("fundingRate")
            if raw_rate is None:
                raw_rate = data.get("info", {}).get("fundingRate")
            if raw_rate is None:
                return {
                    "available": False,
                    "funding_rate": None,
                    "reason": "funding_rate_missing",
                }

            rate = float(raw_rate)
            result = self.analyze(rate)
            result["funding_rate"] = rate
            return result

        except ccxt.BadSymbol:
            return {
                "available": False,
                "funding_rate": None,
                "reason": "unsupported_symbol",
            }
        except ccxt.NetworkError as e:
            print(f"  ⚠️  Funding network error {symbol}: {e}")
            return {
                "available": False,
                "funding_rate": None,
                "reason": "network_error",
            }
        except Exception as e:
            print(f"  ⚠️  Funding fetch failed {symbol}: {e}")
            return {
                "available": False,
                "funding_rate": None,
                "reason": "fetch_error",
            }
