from reports.execution_outcome import calculate_canonical_trade_r
from storage.signal_logger import load_signals

ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}
TERMINAL_STATUSES = {"TP3_HIT", "SL_HIT", "EXPIRED"}
RESOLVED_STATUSES = {"TP3_HIT", "SL_HIT"}


class AnalyticsEngine:

    @staticmethod
    def _terminal_r(signal: dict):
        """Return the canonical trade R for a terminal signal."""
        outcome = calculate_canonical_trade_r(signal)
        return outcome.realized_r if outcome.resolved else None

    @staticmethod
    def _resolved_outcomes(signals):
        """Return only terminal trades with a resolved canonical outcome."""
        outcomes = []
        for signal in signals:
            if signal.get("status") not in RESOLVED_STATUSES:
                continue
            outcome = calculate_canonical_trade_r(signal)
            if outcome.resolved:
                outcomes.append((signal, outcome.realized_r))
        return outcomes

    def compute(self) -> dict:
        signals = load_signals()
        closed = [s for s in signals if s.get("status") in TERMINAL_STATUSES]
        active = [s for s in signals if s.get("status") in ACTIVE_STATUSES]

        # A terminal lifecycle status is not sufficient to classify a trade.
        # Only trades with a resolved canonical outcome enter performance stats.
        resolved_outcomes = self._resolved_outcomes(signals)
        unresolved_terminal = [
            s for s in closed
            if s.get("status") in RESOLVED_STATUSES
            and not calculate_canonical_trade_r(s).resolved
        ]
        wins = [(s, r) for s, r in resolved_outcomes if r > 0]
        losses = [(s, r) for s, r in resolved_outcomes if r <= 0]
        r_values = [r for _, r in resolved_outcomes]

        gross_profit = sum(r for r in r_values if r > 0)
        gross_loss = abs(sum(r for r in r_values if r < 0))
        net_r = sum(r_values)

        resolved_total = len(resolved_outcomes)
        win_rate = round((len(wins) / resolved_total) * 100, 2) if resolved_total else 0
        profit_factor = round(gross_profit / gross_loss, 2) if gross_loss else 0
        avg_win = round(gross_profit / len(wins), 2) if wins else 0
        avg_loss = round(gross_loss / len(losses), 2) if losses else 0
        expectancy = round(net_r / resolved_total, 2) if resolved_total else 0

        grade_stats = {}
        for grade in ("S", "A", "B", "C"):
            g_signals = [s for s in signals if s.get("grade") == grade]
            g_resolved = [(s, r) for s, r in resolved_outcomes if s.get("grade") == grade]
            g_wins = [(s, r) for s, r in g_resolved if r > 0]
            grade_stats[grade] = {
                "total": len(g_signals),
                "resolved": len(g_resolved),
                "wins": len(g_wins),
                "wr": round(len(g_wins) / len(g_resolved) * 100, 1) if g_resolved else 0,
                "net_r": round(sum(r for _, r in g_resolved), 2),
            }

        return {
            "total_signals": len(signals),
            "open": len(active),
            "closed": len(closed),
            "expired": len([s for s in closed if s.get("status") == "EXPIRED"]),
            "resolved": resolved_total,
            "unresolved": len(unresolved_terminal),
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
