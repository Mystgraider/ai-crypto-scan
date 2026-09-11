"""
Signal Validator — V5.4
========================
Final gate before a signal is sent.
All conditions must pass.
"""

from config import CONFIG


class SignalValidator:

    def validate(
        self,
        direction:     str,
        trend_score:   float,
        quality_score: float,
        risk_levels:   dict | None,
    ) -> bool:

        if direction == "NONE":
            return False

        if risk_levels is None:
            return False

        min_score = CONFIG["min_score"]

        if CONFIG.get("require_trend_gate", True) and trend_score < min_score:
            return False

        if CONFIG.get("require_quality_engine", True) and quality_score < min_score:
            return False

        return True
