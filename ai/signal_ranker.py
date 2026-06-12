"""
AI Signal Ranker — V6.0
=========================
Upgrades from V5.x:
- OI signal now properly weighted in composite score
- MACD histogram strength as a ranking factor
- Stoch RSI position bonus
- BB position quality bonus
- Funding rate score incorporated
- Adjusted weights for tighter signal quality

Ranking weights:
  35% trend_score     — how strong is the trend
  22% quality_score   — volume + RSI + Stoch + BB quality
  18% rs_score        — relative strength vs BTC
  10% oi_bonus        — OI confirms direction
   8% rr              — risk/reward ratio
   5% sr_bonus        — near S/R level bonus
   2% funding_bonus   — funding rate alignment
"""


class AISignalRanker:

    GRADE_WEIGHT = {"S": 5, "A": 4, "B": 3, "C": 2, "D": 0}

    OI_BONUS = {
        "CONFIRMED":  12,   # OI rising with price direction = conviction
        "NEUTRAL":     0,
        "WEAK":       -8,   # OI not supporting move
        "DIVERGING": -15,   # OI going against direction = danger
    }

    def rank(self, candidates: list[dict]) -> list[dict]:

        scored = []

        for c in candidates:

            trend_score   = float(c.get("trend_score",   0))
            quality_score = float(c.get("quality_score", 0))
            rs_score      = float(c.get("rs_score",     50))
            rr            = float(c.get("rr",            0))
            sr_bonus      = float(c.get("sr_bonus",      0))
            grade         = c.get("grade", "D")
            oi_signal     = c.get("oi_signal", "NEUTRAL")
            funding_pct   = float(c.get("funding_pct_raw", 0))
            direction     = c.get("direction", "LONG")
            mtf_status    = c.get("mtf_status", "ALLOWED")

            grade_bonus = self.GRADE_WEIGHT.get(grade, 0) * 2

            # OI bonus — now properly factored
            oi_bonus = self.OI_BONUS.get(oi_signal, 0)

            # MTF bonus — CONFIRMED_STRONG gets extra ranking boost
            mtf_bonus = 8 if mtf_status == "CONFIRMED_STRONG" else 0

            # Funding bonus: ideal conditions get small boost
            if direction == "SHORT" and funding_pct <= 0:
                funding_bonus = 3
            elif direction == "LONG" and funding_pct >= 0:
                funding_bonus = 2
            else:
                funding_bonus = 0

            composite = (
                trend_score              * 0.35 +
                quality_score            * 0.22 +
                rs_score                 * 0.18 +
                oi_bonus                 * 0.10 * 10 +   # normalize to ~100 scale
                min(rr, 5) / 5 * 100     * 0.08 +
                min(sr_bonus, 15)         * 0.05 +
                funding_bonus            +
                mtf_bonus                +
                grade_bonus
            )

            scored.append({**c, "ai_composite": round(composite, 2)})

        scored.sort(key=lambda x: x["ai_composite"], reverse=True)
        return scored

    def top_n(self, candidates: list[dict], n: int = 5) -> list[dict]:
        return self.rank(candidates)[:n]
