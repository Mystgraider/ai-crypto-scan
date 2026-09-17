"""
AI Signal Ranker — V6.2
=========================
Ranks eligible candidates separately from the trading composite score.

Important:
- ``composite`` remains the trading/decision score produced by the scanner.
- ``ai_rank_score`` is a bounded 0-100 ranking score used only to order
  already-eligible candidates.
- ``ai_composite`` is retained as a backward-compatible alias of
  ``ai_rank_score``.
- AI rank score is NOT a win probability or confidence percentage.

The ranking components are normalized to their declared ranges before the
weighted score is calculated. This keeps the ranking scale bounded without
clipping multiple strong candidates to the same score.
"""

from ai.attribution import build_attribution


class AISignalRanker:
    # Declared component weights. These sum to 98%; the remaining 2% is
    # reserved for the small categorical adjustments below.
    WEIGHT_TREND = 35.0
    WEIGHT_QUALITY = 22.0
    WEIGHT_RS = 18.0
    WEIGHT_OI = 10.0
    WEIGHT_RR = 8.0
    WEIGHT_SR = 5.0
    WEIGHT_CATEGORY = 2.0

    GRADE_WEIGHT = {"S": 3, "A": 3, "B": 5, "C": 1, "D": 0}
    OI_BONUS = {
        "CONFIRMED": 12,
        "NEUTRAL": 0,
        "WEAK": -8,
        "DIVERGING": -15,
    }

    @staticmethod
    def _clamp(value: float, low: float, high: float) -> float:
        if value != value:  # NaN
            return low
        if value == float("inf"):
            return high
        if value == float("-inf"):
            return low
        return max(low, min(high, value))

    def rank(self, candidates: list[dict]) -> list[dict]:
        scored = []

        for c in candidates:
            trend_score = self._clamp(float(c.get("trend_score", 0)), 0.0, 100.0)
            quality_score = self._clamp(float(c.get("quality_score", 0)), 0.0, 100.0)
            rs_score = self._clamp(float(c.get("rs_score", 50)), 0.0, 100.0)
            rr = self._clamp(float(c.get("rr", 0)), 0.0, 5.0)
            sr_bonus = self._clamp(float(c.get("sr_bonus", 0)), 0.0, 15.0)
            grade = c.get("grade", "D")
            oi_signal = c.get("oi_signal", "NEUTRAL")
            funding_pct = float(c.get("funding_pct_raw", 0))
            direction = c.get("direction", "LONG")
            mtf_status = c.get("mtf_status", "ALLOWED")

            trend_component = trend_score / 100.0 * self.WEIGHT_TREND
            quality_component = quality_score / 100.0 * self.WEIGHT_QUALITY
            rs_component = rs_score / 100.0 * self.WEIGHT_RS
            rr_component = rr / 5.0 * self.WEIGHT_RR
            sr_component = sr_bonus / 15.0 * self.WEIGHT_SR

            # OI alignment occupies a signed component within the 10-point
            # budget rather than being added as an unbounded bonus.
            oi_raw = self.OI_BONUS.get(oi_signal, 0)
            oi_component = self._clamp((oi_raw + 15.0) / 27.0 * self.WEIGHT_OI, 0.0, self.WEIGHT_OI)

            if direction == "SHORT" and funding_pct <= 0:
                funding_bonus = 1.0
            elif direction == "LONG" and funding_pct >= 0:
                funding_bonus = 1.0
            else:
                funding_bonus = 0.0

            mtf_bonus = 1.0 if mtf_status == "CONFIRMED_STRONG" else 0.0
            grade_bonus = self._clamp(self.GRADE_WEIGHT.get(grade, 0) / 5.0, 0.0, 1.0)
            category_component = self._clamp(
                (funding_bonus + mtf_bonus + grade_bonus) / 3.0 * self.WEIGHT_CATEGORY,
                0.0,
                self.WEIGHT_CATEGORY,
            )

            raw_score = (
                trend_component
                + quality_component
                + rs_component
                + oi_component
                + rr_component
                + sr_component
                + category_component
            )
            ai_rank_score = round(self._clamp(raw_score, 0.0, 100.0), 2)
            attribution = build_attribution(
                trend_component=trend_component,
                quality_component=quality_component,
                rs_component=rs_component,
                oi_component=oi_component,
                rr_component=rr_component,
                sr_component=sr_component,
                category_component=category_component,
                ai_rank_score=ai_rank_score,
                ai_rank_raw=raw_score,
            )

            scored.append(
                {
                    **c,
                    "ai_rank_score": ai_rank_score,
                    "ai_rank_raw": round(raw_score, 2),
                    "ai_composite": ai_rank_score,
                    "ai_attribution": attribution,
                }
            )

        scored.sort(key=lambda x: x["ai_rank_score"], reverse=True)
        return scored

    def top_n(self, candidates: list[dict], n: int = 5) -> list[dict]:
        return self.rank(candidates)[:n]
