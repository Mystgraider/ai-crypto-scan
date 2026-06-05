"""
AI Signal Ranker — Phase 5 upgrade
=====================================
Now incorporates Relative Strength score into ranking.

Ranking weights:
  40% trend_score     — how strong is the trend
  25% quality_score   — volume + RSI quality
  20% rs_score        — relative strength vs BTC
  10% rr              — risk/reward ratio
   5% sr_bonus        — near S/R level bonus
"""


class AISignalRanker:

    GRADE_WEIGHT = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}

    def rank(self, candidates: list[dict]) -> list[dict]:

        scored = []

        for c in candidates:

            trend_score   = float(c.get("trend_score",   0))
            quality_score = float(c.get("quality_score", 0))
            rs_score      = float(c.get("rs_score",     50))   # default neutral
            rr            = float(c.get("rr",            0))
            sr_bonus      = float(c.get("sr_bonus",      0))
            grade         = c.get("grade", "D")

            grade_bonus = self.GRADE_WEIGHT.get(grade, 0) * 2

            composite = (
                trend_score            * 0.40 +
                quality_score          * 0.25 +
                rs_score               * 0.20 +
                min(rr, 5) / 5 * 100   * 0.10 +
                min(sr_bonus, 15)       * 0.05 +
                grade_bonus
            )

            scored.append({**c, "ai_composite": round(composite, 2)})

        scored.sort(key=lambda x: x["ai_composite"], reverse=True)

        return scored

    def top_n(self, candidates: list[dict], n: int = 5) -> list[dict]:
        return self.rank(candidates)[:n]
