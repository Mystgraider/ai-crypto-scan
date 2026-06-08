import ccxt

"""
Funding Rate Engine — V5.8
============================
Checks perpetual swap funding rate before allowing signals.

Funding rate = periodic payment between longs and shorts.

Positive funding (+):
  Longs PAY shorts → market is crowded LONG
  → SHORT signal = dangerous (squeeze risk if funding resets)
  → LONG signal = fine (you get paid)

Negative funding (-):
  Shorts PAY longs → market is crowded SHORT
  → SHORT signal = dangerous (short squeeze if too crowded)
  → LONG signal = fine (market oversold bias)

Near-zero funding (neutral):
  Balanced market → both directions okay

Thresholds (OKX 8H funding rate):
  LONG  blocked if funding < -0.05% (too many shorts already)
  SHORT blocked if funding > +0.01% (crowded longs = squeeze risk)
  SHORT ideal  if funding <= 0.00% (neutral to negative = safe to short)
"""


class FundingEngine:

    # Block SHORT if funding above this (crowded longs = squeeze risk)
    SHORT_BLOCK_ABOVE  =  0.0001   # +0.01%

    # Block LONG if funding below this (crowded shorts = squeeze risk)
    LONG_BLOCK_BELOW   = -0.0005   # -0.05%

    # Ideal SHORT zone
    SHORT_IDEAL_BELOW  =  0.0000   # 0% or negative

    def analyze(self, funding_rate: float) -> dict:
        """
        funding_rate: raw value from OKX (e.g. 0.0001 = 0.01%)
        """

        pct = round(funding_rate * 100, 4)  # convert to %

        # ── LONG assessment ────────────────────────────────────────────
        if funding_rate < self.LONG_BLOCK_BELOW:
            long_ok  = False
            long_msg = f"Funding {pct}% too negative — crowded shorts, squeeze risk for LONG"
        else:
            long_ok  = True
            long_msg = f"Funding {pct}% OK for LONG"

        # ── SHORT assessment ───────────────────────────────────────────
        if funding_rate > self.SHORT_BLOCK_ABOVE:
            short_ok  = False
            short_msg = f"Funding {pct}% positive — crowded longs, squeeze risk for SHORT"
        else:
            short_ok  = True
            if funding_rate <= self.SHORT_IDEAL_BELOW:
                short_msg = f"Funding {pct}% ideal for SHORT (negative/neutral)"
            else:
                short_msg = f"Funding {pct}% OK for SHORT"

        # ── Score bonus/penalty for AI ranker ─────────────────────────
        # SHORT score adjustment based on funding
        if funding_rate <= -0.0003:
            short_score_adj = -10   # too negative = crowded shorts = risky
        elif funding_rate <= 0.0000:
            short_score_adj = +5    # ideal: neutral to slightly negative
        elif funding_rate <= self.SHORT_BLOCK_ABOVE:
            short_score_adj = 0     # slightly positive but within limit
        else:
            short_score_adj = -999  # blocked

        return {
            "funding_rate":     funding_rate,
            "funding_pct":      pct,
            "long_ok":          long_ok,
            "short_ok":         short_ok,
            "long_msg":         long_msg,
            "short_msg":        short_msg,
            "short_score_adj":  short_score_adj,
        }

    def fetch_funding(self, exchange, symbol: str) -> float:
        """
        Fetch current funding rate from OKX via ccxt.
        Returns 0.0 if unavailable (fail-safe = allow signal).

        OKX ccxt uses fetch_funding_rate() which returns:
        {"fundingRate": 0.0001, ...}
        Symbol must be in OKX swap format: BTC/USDT:USDT
        """
        try:
            # ccxt fetch_funding_rate for perpetual swaps
            data = exchange.fetch_funding_rate(symbol)

            # ccxt returns fundingRate as a decimal (0.0001 = 0.01%)
            rate = (
                data.get("fundingRate") or
                data.get("info", {}).get("fundingRate") or
                0.0
            )
            return float(rate)

        except ccxt.BadSymbol:
            # Symbol doesn't support funding rate (e.g. dated futures)
            return 0.0

        except ccxt.NetworkError as e:
            print(f"  ⚠️  Funding network error {symbol}: {e}")
            return 0.0

        except Exception:
            # Silent fail — never block signal on API error
            return 0.0
