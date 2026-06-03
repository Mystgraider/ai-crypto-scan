import time


class OIEngine:

    def __init__(self):
        self.history = {}

    def update(
        self,
        symbol,
        current_oi
    ):

        now = time.time()

        if symbol not in self.history:

            self.history[symbol] = {
                "oi": current_oi,
                "timestamp": now
            }

            return {
                "grade": "NEW",
                "score": 0,
                "change_pct": 0
            }

        previous_oi = self.history[symbol]["oi"]

        self.history[symbol] = {
            "oi": current_oi,
            "timestamp": now
        }

        if previous_oi <= 0:

            return {
                "grade": "INVALID",
                "score": 0,
                "change_pct": 0
            }

        change_pct = (
            (
                current_oi -
                previous_oi
            )
            /
            previous_oi
        ) * 100

        grade = self.get_grade(
            change_pct
        )

        score = self.get_score(
            grade
        )

        return {
            "grade": grade,
            "score": score,
            "change_pct": round(
                change_pct,
                2
            )
        }

    def get_grade(
        self,
        change_pct
    ):

        if change_pct >= 10:
            return "ELITE"

        if change_pct >= 5:
            return "STRONG"

        if change_pct >= 2:
            return "GOOD"

        if change_pct >= 0:
            return "NEUTRAL"

        return "WEAK"

    def get_score(
        self,
        grade
    ):

        scores = {

            "ELITE": 4,

            "STRONG": 3,

            "GOOD": 2,

            "NEUTRAL": 1,

            "WEAK": 0,

            "NEW": 0,

            "INVALID": 0
        }

        return scores.get(
            grade,
            0
        )
