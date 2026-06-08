"""
Adaptive Engine — V5.7
========================
Monitors signal performance and auto-adjusts conservative
parameters when losing streaks are detected.

What it CAN auto-adjust (safe):
  - signal_cooldown_hours (longer cooldown = fewer signals in bad market)
  - max_signals_per_run (reduce signals when system is losing)
  - min_score threshold (raise bar when losing = only high-confidence signals)

What it NEVER auto-adjusts (dangerous, requires human):
  - SL/TP multipliers (core risk structure)
  - BTC filter logic
  - ADX minimum

Losing streak levels:
  LEVEL 0 — Normal    : 0-1 losses in last 5  → no change
  LEVEL 1 — Caution   : 2 losses in last 5    → raise min_score +5, reduce max signals
  LEVEL 2 — Warning   : 3 losses in last 5    → raise min_score +10, cooldown +2h
  LEVEL 3 — Danger    : 4-5 losses in last 5  → only Grade S signals, alert owner
"""

from storage.signal_logger    import load_signals
from alerts.telegram_alerts   import send_telegram_alert
from config                   import CONFIG


class AdaptiveEngine:

    # Last N closed signals to evaluate
    WINDOW = 5

    LEVELS = {
        0: {"name": "NORMAL",  "min_score_add": 0,  "max_signals": 5, "cooldown_add": 0},
        1: {"name": "CAUTION", "min_score_add": 5,  "max_signals": 3, "cooldown_add": 0},
        2: {"name": "WARNING", "min_score_add": 10, "max_signals": 2, "cooldown_add": 2},
        3: {"name": "DANGER",  "min_score_add": 20, "max_signals": 1, "cooldown_add": 4},
    }

    def evaluate(self) -> dict:
        """
        Evaluate recent performance and return adjusted parameters.
        Returns dict with adjusted values to use this run.
        """

        signals  = load_signals()
        closed   = [
            s for s in signals
            if s["status"] in ("TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT")
        ]

        # Not enough data yet — use defaults
        if len(closed) < 3:
            return self._apply_level(0, closed)

        recent   = closed[-self.WINDOW:]
        losses   = [s for s in recent if s["status"] == "SL_HIT"]
        loss_count = len(losses)

        if loss_count >= 4:
            level = 3
        elif loss_count == 3:
            level = 2
        elif loss_count == 2:
            level = 1
        else:
            level = 0

        return self._apply_level(level, recent)

    def _apply_level(self, level: int, recent: list) -> dict:

        cfg   = self.LEVELS[level]
        name  = cfg["name"]

        # Adjusted parameters for this run
        adj_min_score   = CONFIG["min_score"]         + cfg["min_score_add"]
        adj_max_signals = cfg["max_signals"]
        adj_cooldown    = CONFIG["signal_cooldown_hours"] + cfg["cooldown_add"]

        # Grade filter: DANGER = S only, WARNING = S+A only, else all
        if level == 3:
            allowed_grades = {"S"}
        elif level == 2:
            allowed_grades = {"S", "A"}
        else:
            allowed_grades = {"S", "A", "B", "C"}

        result = {
            "level":          level,
            "level_name":     name,
            "min_score":      adj_min_score,
            "max_signals":    adj_max_signals,
            "cooldown_hours": adj_cooldown,
            "allowed_grades": allowed_grades,
            "recent_losses":  len([s for s in recent if s["status"] == "SL_HIT"]),
            "recent_wins":    len([s for s in recent if s["status"] != "SL_HIT"]),
            "window":         len(recent),
        }

        # Alert owner on WARNING and DANGER
        if level >= 2:
            self._send_alert(result)

        return result

    def _send_alert(self, result: dict):

        level   = result["level"]
        name    = result["level_name"]
        losses  = result["recent_losses"]
        wins    = result["recent_wins"]
        window  = result["window"]

        icon = "⚠️" if level == 2 else "🚨"

        msg = (
            f"{icon} <b>ELITE V5 — Adaptive Alert</b>\n\n"
            f"Status: <b>{name}</b> (Level {level})\n"
            f"Last {window} closed: {wins}W / {losses}L\n\n"
            f"<b>Auto-adjustments this run:</b>\n"
            f"  Min score: <b>{result['min_score']}</b> "
            f"(+{result['min_score'] - CONFIG['min_score']})\n"
            f"  Max signals: <b>{result['max_signals']}</b>\n"
            f"  Cooldown: <b>{result['cooldown_hours']}H</b>\n"
            f"  Allowed grades: <b>{', '.join(sorted(result['allowed_grades']))}</b>\n\n"
        )

        if level == 3:
            msg += (
                f"🚨 <b>DANGER: 4-5 losses in last {window} signals!</b>\n"
                f"Only Grade S signals will fire.\n"
                f"Consider pausing manually if losses continue."
            )
        else:
            msg += (
                f"System raising quality bar automatically.\n"
                f"Will return to normal when win rate recovers."
            )

        send_telegram_alert(msg)
        print(f"  ⚠️ Adaptive alert sent: {name}")
