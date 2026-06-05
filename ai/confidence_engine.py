class ConfidenceEngine:
    """
    Phase 5 — Confidence Engine.
    Estimates signal confidence based on historical win rate
    and current signal quality metrics.
    """

    def estimate(
        self,
        trend_score:   float,
        quality_score: float,
        historical_wr: float = 50.0,  # % from AnalyticsEngine
    ) -> float:
        """
        Returns confidence 0-100.
        """

        # Base: average of trend + quality
        base = (trend_score + quality_score) / 2

        # Historical win rate adjustment
        wr_factor = (historical_wr - 50) / 50  # -1 to +1

        confidence = base + (wr_factor * 10)
        confidence = max(0.0, min(100.0, confidence))

        return round(confidence, 2)
