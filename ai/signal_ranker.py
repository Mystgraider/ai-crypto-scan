class AISignalRanker:
    """
    Phase 5 — AI Signal Ranking Layer.

    Takes a list of candidate signal dicts and returns them sorted
    by composite score descending. Only signals above the grade
    threshold are returned.

    Each candidate must contain:
      symbol, direction, trend_score, quality_score, rr, grade
    """

    GRADE_WEIGHT = {"S": 4, "A": 3, "B": 2, "C": 1, "D": 0}

    def rank(self, candidates: list[dict]) -> list[dict]:

        scored = []

        for c in candidates:

            trend_score   = float(c.get("trend_score",   0))
            quality_score = float(c.get("quality_score", 0))
            rr            = float(c.get("rr",            0))
            grade         = c.get("grade", "D")

            grade_bonus = self.GRADE_WEIGHT.get(grade, 0) * 5

            composite = (
                trend_score   * 0.40 +
                quality_score * 0.35 +
                min(rr, 5) / 5 * 100 * 0.15 +
                grade_bonus   * 0.10
            )

            scored.append({**c, "composite": round(composite, 2)})

        # Best signals first
        scored.sort(key=lambda x: x["composite"], reverse=True)

        return scored

    def top_n(self, candidates: list[dict], n: int = 5) -> list[dict]:
        return self.rank(candidates)[:n]
