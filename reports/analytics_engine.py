from storage.signal_logger import load_signals


class AnalyticsEngine:

    def compute(self) -> dict:

        signals = load_signals()
        closed  = [s for s in signals if s["status"] in ("TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT")]
        open_   = [s for s in signals if s["status"] == "OPEN"]

        wins   = [s for s in closed if s["status"] != "SL_HIT"]
        losses = [s for s in closed if s["status"] == "SL_HIT"]

        total = len(closed)
        w     = len(wins)
        l     = len(losses)

        win_rate = round((w / total) * 100, 2) if total else 0

        tp_r = {"TP1_HIT": 2.25, "TP2_HIT": 3.5, "TP3_HIT": 5.5}
        gross_profit = sum(tp_r.get(s["status"], 0) for s in wins)
        gross_loss   = float(l)

        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0

        avg_win  = round(gross_profit / w, 2) if w else 0
        avg_loss = 1.0
        wr_dec   = win_rate / 100
        expectancy = round(wr_dec * avg_win - (1 - wr_dec) * avg_loss, 2)

        # Grade breakdown
        grade_stats = {}
        for g in ("S", "A", "B", "C"):
            g_signals = [s for s in signals if s.get("grade") == g]
            g_closed  = [s for s in g_signals if s["status"] in ("TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT")]
            g_wins    = [s for s in g_closed  if s["status"] != "SL_HIT"]
            grade_stats[g] = {
                "total": len(g_signals),
                "wins":  len(g_wins),
                "wr":    round(len(g_wins) / len(g_closed) * 100, 1) if g_closed else 0,
            }

        return {
            "total_signals":  len(signals),
            "open":           len(open_),
            "closed":         total,
            "wins":           w,
            "losses":         l,
            "win_rate":       win_rate,
            "profit_factor":  profit_factor,
            "expectancy_r":   expectancy,
            "gross_profit_r": round(gross_profit, 2),
            "gross_loss_r":   round(gross_loss, 2),
            "grade_stats":    grade_stats,
        }
