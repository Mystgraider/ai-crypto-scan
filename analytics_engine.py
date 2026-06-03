class AnalyticsEngine:

    def win_rate(
        self,
        wins,
        losses
    ):

        total = wins + losses

        if total == 0:
            return 0

        return round(
            (wins / total) * 100,
            2
        )

    def profit_factor(
        self,
        gross_profit,
        gross_loss
    ):

        if gross_loss == 0:
            return 0

        return round(
            gross_profit /
            gross_loss,
            2
        )

    def expectancy(
        self,
        win_rate,
        avg_win,
        avg_loss
    ):

        wr = win_rate / 100

        result = (
            wr * avg_win
        ) - (
            (1 - wr) * avg_loss
        )

        return round(
            result,
            2
        )
