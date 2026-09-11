class ConfidenceEngine:
    """
    Phase 5 — Confidence Engine.

    Produces a bounded confidence HEURISTIC from current signal quality and
    historical win rate. This value is a ranking/communication aid, NOT a
    calibrated probability of winning a trade.
    """

    def estimate(
        self,
        trend_score: float,
        quality_score: float,
        historical_wr: float = 50.0,
    ) -> float:
        """Return a bounded 0-100 confidence heuristic, not win probability."""
        # Keep the existing model unchanged for Phase 2D-A; calibration will
        # require sufficient historical observations and belongs in Phase 2D-B.
        base = (float(trend_score) + float(quality_score)) / 2
        wr = max(0.0, min(100.0, float(historical_wr)))
        wr_factor = (wr - 50.0) / 50.0

        confidence = base + (wr_factor * 10.0)
        confidence = max(0.0, min(100.0, confidence))
        return round(confidence, 2)
