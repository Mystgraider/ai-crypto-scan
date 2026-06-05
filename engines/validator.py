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

        if trend_score < min_score:
            return False

        # Quality score: slightly relaxed — quality engine
        # already hard-caps overbought/oversold at score 20
        # so fake signals are caught there, not here
        if quality_score < min_score:
            return False

        return True
