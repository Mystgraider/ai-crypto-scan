from storage.signal_logger import load_signals


class AnalyticsEngine:

    def compute(self) -> dict:

        signals = load_signals()
        closed  = [
            s for s in signals
            if s["status"] in ("TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT")
        ]

        wins   = [s for s in closed if s["status"] != "SL_HIT"]
        losses = [s for s in closed if s["status"] == "SL_HIT"]

        total  = len(closed)
        w      = len(wins)
        l      = len(losses)

        win_rate = round((w / total) * 100, 2) if total else 0

        # Approximate P&L in R-multiples
        # TP1=2R, TP2=3R, TP3=5R, SL=-1R
        tp_r = {"TP1_HIT": 2.0, "TP2_HIT": 3.0, "TP3_HIT": 5.0}
        gross_profit = sum(tp_r.get(s["status"], 0) for s in wins)
        gross_loss   = len(losses) * 1.0

        profit_factor = (
            round(gross_profit / gross_loss, 2) if gross_loss else 0
        )

        avg_win  = round(gross_profit / w, 2) if w else 0
        avg_loss = 1.0

        wr_dec   = win_rate / 100
        expectancy = round(
            wr_dec * avg_win - (1 - wr_dec) * avg_loss, 2
        )

        return {
            "total_signals":  len(signals),
            "closed":         total,
            "open":           len([s for s in signals if s["status"] == "OPEN"]),
            "wins":           w,
            "losses":         l,
            "win_rate":       win_rate,
            "profit_factor":  profit_factor,
            "expectancy_r":   expectancy,
            "gross_profit_r": round(gross_profit, 2),
            "gross_loss_r":   round(gross_loss, 2),
        }

    def win_rate(self, wins, losses):
        total = wins + losses
        return round((wins / total) * 100, 2) if total else 0

    def profit_factor(self, gross_profit, gross_loss):
        return round(gross_profit / gross_loss, 2) if gross_loss else 0

    def expectancy(self, win_rate, avg_win, avg_loss):
        wr = win_rate / 100
        return round(wr * avg_win - (1 - wr) * avg_loss, 2)
