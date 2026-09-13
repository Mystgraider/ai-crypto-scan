from reports.execution_outcome import calculate_canonical_trade_r
from storage.signal_logger import load_signals

ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}
TERMINAL_STATUSES = {"TP3_HIT", "SL_HIT", "EXPIRED"}


class AnalyticsEngine:

    @staticmethod
    def _terminal_r(signal: dict):
        """Return the canonical trade R for a terminal signal."""
        outcome = calculate_canonical_trade_r(signal)
        return outcome.realized_r if outcome.resolved else None

    def compute(self) -> dict:
        signals = load_signals()
        closed = [s for s in signals if s.get("status") in TERMINAL_STATUSES]
        active = [s for s in signals if s.get("status") in ACTIVE_STATUSES]

        # EXPIRED is not a win/loss. It is reported separately so stale
        # signals cannot distort win rate or profit factor.
        resolved = [s for s in closed if s.get("status") in {"TP3_HIT", "SL_HIT"}]
        wins = [s for s in resolved if (self._terminal_r(s) or 0.0) > 0]
        losses = [s for s in resolved if (self._terminal_r(s) or 0.0) <= 0]

        r_values = [self._terminal_r(s) for s in resolved]
        r_values = [r for r in r_values if r is not None]
        gross_profit = sum(r for r in r_values if r > 0)
        gross_loss = abs(sum(r for r in r_values if r < 0))
        net_r = sum(r_values)

        resolved_total = len(resolved)
        win_rate = round((len(wins) / resolved_total) * 100, 2) if resolved_total else 0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0
        avg_win = round(gross_profit / len(wins), 2) if wins else 0
        avg_loss = round(gross_loss / len(losses), 2) if losses else 0
        expectancy = round(net_r / resolved_total, 2) if resolved_total else 0

        grade_stats = {}
        for grade in ("S", "A", "B", "C"):
            g_signals = [s for s in signals if s.get("grade") == grade]
            g_resolved = [s for s in g_signals if s.get("status") in {"TP3_HIT", "SL_HIT"}]
            g_wins = [s for s in g_resolved if (self._terminal_r(s) or 0.0) > 0]
            g_r = [self._terminal_r(s) for s in g_resolved]
            g_r = [r for r in g_r if r is not None]
            grade_stats[grade] = {
                "total": len(g_signals),
                "resolved": len(g_resolved),
                "wins": len(g_wins),
                "wr": round(len(g_wins) / len(g_resolved) * 100, 1) if g_resolved else 0,
                "net_r": round(sum(g_r), 2),
            }

        return {
            "total_signals": len(signals),
            "open": len(active),
            "closed": len(closed),
            "expired": len([s for s in closed if s.get("status") == "EXPIRED"]),
            "resolved": resolved_total,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "expectancy_r": expectancy,
            "avg_win_r": avg_win,
            "avg_loss_r": avg_loss,
            "gross_profit_r": round(gross_profit, 2),
            "gross_loss_r": round(gross_loss, 2),
            "net_r": round(net_r, 2),
            "grade_stats": grade_stats,
        }
