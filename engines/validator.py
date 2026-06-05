from config import CONFIG


class SignalValidator:
    """
    Final gate. Returns True only when all conditions are met.
    """

    def validate(
        self,
        direction: str,
        trend_score: float,
        quality_score: float,
        risk_levels: dict | None,
    ) -> bool:

        if risk_levels is None:
            return False

        if direction == "NONE":
            return False

        min_score = CONFIG["min_score"]

        if trend_score < min_score:
            return False

        if quality_score < min_score:
            return False

        return True
