"""
AI Signal Ranker — V6.1
=========================
Ranks eligible candidates separately from the trading composite score.

Important:
- ``composite`` remains the trading/decision score produced by the scanner.
- ``ai_rank_score`` is a bounded 0-100 ranking score used only to order
  already-eligible candidates.
- ``ai_composite`` is retained as a backward-compatible alias of
  ``ai_rank_score``.
- AI rank score is NOT a win probability or confidence percentage.

Ranking inputs:
  35% trend_score
  22% quality_score
  18% rs_score
  10% OI alignment
   8% risk/reward
   5% S/R bonus
  plus small categorical bonuses for funding, MTF and grade.
"""


class AISignalRanker:

    # Historical ranking preference. This affects ordering only; it does not
    # redefine the scanner's trading score or imply a probability of success.
    GRADE_WEIGHT = {"S": 3, "A": 3, "B": 5, "C": 1, "D": 0}

    OI_BONUS = {
        "CONFIRMED": 12,
        "NEUTRAL": 0,
        "WEAK": -8,
        "DIVERGING": -15,
    }

    @staticmethod
    def _bounded_score(value: float) -> float:
        """Return a finite ranking score on an explicit 0-100 scale."""
        if value != value:  # NaN
            return 0.0
        if value == float("inf"):
            return 100.0
        if value == float("-inf"):
            return 0.0
        return max(0.0, min(100.0, value))

    def rank(self, candidates: list[dict]) -> list[dict]:
        scored = []

        for c in candidates:
            trend_score = float(c.get("trend_score", 0))
            quality_score = float(c.get("quality_score", 0))
            rs_score = float(c.get("rs_score", 50))
            rr = float(c.get("rr", 0))
            sr_bonus = float(c.get("sr_bonus", 0))
            grade = c.get("grade", "D")
            oi_signal = c.get("oi_signal", "NEUTRAL")
            funding_pct = float(c.get("funding_pct_raw", 0))
            direction = c.get("direction", "LONG")
            mtf_status = c.get("mtf_status", "ALLOWED")

            grade_bonus = self.GRADE_WEIGHT.get(grade, 0) * 2
            oi_bonus = self.OI_BONUS.get(oi_signal, 0)
            mtf_bonus = 8 if mtf_status == "CONFIRMED_STRONG" else 0

            if direction == "SHORT" and funding_pct <= 0:
                funding_bonus = 3
            elif direction == "LONG" and funding_pct >= 0:
                funding_bonus = 2
            else:
                funding_bonus = 0

            raw_score = (
                trend_score * 0.35
                + quality_score * 0.22
                + rs_score * 0.18
                + oi_bonus * 0.10 * 10
                + min(rr, 5) / 5 * 100 * 0.08
                + min(sr_bonus, 15) * 0.05
                + funding_bonus
                + mtf_bonus
                + grade_bonus
            )

            ai_rank_score = round(self._bounded_score(raw_score), 2)
            scored.append(
                {
                    **c,
                    "ai_rank_score": ai_rank_score,
                    "ai_rank_raw": round(raw_score, 2),
                    "ai_composite": ai_rank_score,
                }
            )

        scored.sort(key=lambda x: x["ai_rank_score"], reverse=True)
        return scored

    def top_n(self, candidates: list[dict], n: int = 5) -> list[dict]:
        return self.rank(candidates)[:n]
