"""
Dynamic Position Sizer — Phase 5
==================================
Recommends position size based on:
- Signal confidence score
- Grade (S/A/B/C)
- Account risk tolerance (default 1% per trade)

Output: recommended risk % and leverage suggestion.

This does NOT execute trades — it gives the recommendation
so the trader can decide how much to allocate.

Kelly-inspired sizing:
  Grade S (confidence > 75%) → 2.0% account risk
  Grade A (confidence > 65%) → 1.5% account risk
  Grade B (confidence > 55%) → 1.0% account risk
  Grade C                    → 0.5% account risk (minimum)
"""

import math


class PositionSizer:

    # Max risk % per trade (conservative defaults)
    RISK_TABLE = {
        "S": 2.0,
        "A": 1.5,
        "B": 1.0,
        "C": 0.5,
    }

    # Suggested leverage by grade (for futures)
    # V6.5: lowered for small-capital accounts (₱500-1,000 / ~$9-18) —
    # liquidation risk from normal volatility hits harder on tiny
    # accounts than on larger ones, so even "high confidence" signals
    # get capped conservatively.
    LEVERAGE_TABLE = {
        "S": 5,
        "A": 4,
        "B": 3,
        "C": 2,
    }

    def calculate(
        self,
        grade:      str,
        confidence: float,
        entry:      float,
        sl:         float,
        account:    float = 1000.0,   # USDT account size
        risk_contract: str = "STANDARD",
        fallback_max_risk_pct: float = 0.5,
    ) -> dict:

        if grade not in self.RISK_TABLE:
            raise ValueError("invalid_grade")
        if not isinstance(confidence, (int, float)) or not math.isfinite(confidence):
            raise ValueError("invalid_confidence")
        if not 0 <= confidence <= 100:
            raise ValueError("confidence_out_of_range")
        if not isinstance(entry, (int, float)) or not math.isfinite(entry) or entry <= 0:
            raise ValueError("invalid_entry")
        if not isinstance(sl, (int, float)) or not math.isfinite(sl) or sl <= 0:
            raise ValueError("invalid_sl")
        if not isinstance(account, (int, float)) or not math.isfinite(account) or account <= 0:
            raise ValueError("invalid_account")

        base_risk_pct = self.RISK_TABLE[grade]
        if risk_contract not in {"STANDARD", "RRCE", "ATR_FALLBACK"}:
            raise ValueError("invalid_risk_contract")
        if not isinstance(fallback_max_risk_pct, (int, float)) or not math.isfinite(fallback_max_risk_pct) or fallback_max_risk_pct <= 0:
            raise ValueError("invalid_fallback_max_risk_pct")

        # Confidence adjustment: < 50% confidence = halve the risk
        if confidence < 50:
            base_risk_pct *= 0.5
        elif confidence > 75:
            base_risk_pct *= 1.0   # full size — already at max
        else:
            # Scale linearly between 50-75% confidence
            scale = 0.5 + (confidence - 50) / 50
            base_risk_pct *= scale

        base_risk_pct = round(min(base_risk_pct, 2.0), 2)
        # ATR fallback has materially weaker recent realized outcomes than
        # RRCE-qualified candidates. Keep it eligible, but quarantine its
        # account risk until the fallback path is revalidated with a larger
        # out-of-sample sample. This changes exposure, not signal admission.
        if risk_contract == "ATR_FALLBACK":
            base_risk_pct = round(min(base_risk_pct, fallback_max_risk_pct), 2)

        # Risk in USDT
        risk_usdt = round(account * (base_risk_pct / 100), 2)

        # Position size based on SL distance
        sl_dist_pct = abs(entry - sl) / entry
        if sl_dist_pct == 0:
            position_usdt = 0
        else:
            position_usdt = round(risk_usdt / sl_dist_pct, 2)

        leverage = self.LEVERAGE_TABLE.get(grade, 3)

        return {
            "grade":          grade,
            "confidence":     round(confidence, 1),
            "risk_pct":       base_risk_pct,
            "risk_usdt":      risk_usdt,
            "position_usdt":  position_usdt,
            "leverage":       leverage,
            "account":        account,
        }

    def format_recommendation(self, sizing: dict) -> str:
        return (
            f"💰 Risk: <b>{sizing['risk_pct']}%</b> "
            f"(${sizing['risk_usdt']})\n"
            f"📦 Position: <b>${sizing['position_usdt']}</b> "
            f"@ {sizing['leverage']}x leverage"
        )
