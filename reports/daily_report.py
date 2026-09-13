"""
Daily Report — V6.2
Shows TODAY's signals only and respects the active/terminal lifecycle.

Uses canonical realized R from Phase 2D-H.5 instead of fixed TP assumptions.
"""

from datetime import datetime, timezone
from reports.execution_outcome import calculate_canonical_trade_r
from storage.signal_logger import load_signals
from alerts.telegram_alerts import send_telegram_alert

ACTIVE_STATUSES = {"OPEN", "OPEN_TP1", "OPEN_TP2"}
TERMINAL_STATUSES = {"TP3_HIT", "SL_HIT", "EXPIRED"}
RESOLVED_STATUSES = {"TP3_HIT", "SL_HIT"}


class DailyReport:

    def send(self):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_signals = load_signals()
        today_signals = [s for s in all_signals if s.get("timestamp", "")[:10] == today]

        resolved_outcomes = []
        unresolved_today = 0
        for signal in today_signals:
            if signal.get("status") not in RESOLVED_STATUSES:
                continue
            outcome = calculate_canonical_trade_r(signal)
            if outcome.resolved:
                resolved_outcomes.append((signal, outcome.realized_r))
            else:
                unresolved_today += 1

        active_today = [s for s in today_signals if s.get("status") in ACTIVE_STATUSES]
        expired_today = [s for s in today_signals if s.get("status") == "EXPIRED"]

        wins_today = [(s, r) for s, r in resolved_outcomes if r > 0]
        losses_today = [(s, r) for s, r in resolved_outcomes if r <= 0]
        known_r = [r for _, r in resolved_outcomes]
        gross_win = sum(r for r in known_r if r > 0)
        gross_loss = abs(sum(r for r in known_r if r < 0))
        net_r = sum(known_r)
        resolved_total = len(resolved_outcomes)
        wr = round(len(wins_today) / resolved_total * 100, 1) if resolved_total else 0
        pf = round(gross_win / gross_loss, 2) if gross_loss else 0

        grade_lines = ""
        for grade in ("S", "A", "B", "C"):
            g_sigs = [s for s in today_signals if s.get("grade") == grade]
            g_resolved = [(s, r) for s, r in resolved_outcomes if s.get("grade") == grade]
            g_wins = [(s, r) for s, r in g_resolved if r > 0]
            if g_sigs:
                g_wr = round(len(g_wins) / len(g_resolved) * 100, 0) if g_resolved else "-"
                grade_lines += f"  Grade {grade}: {len(g_sigs)} signals | WR: {g_wr}%\n"

        sig_lines = ""
        for s in today_signals:
            status = s.get("status", "")
            icon = "✅" if status == "TP3_HIT" else "❌" if status == "SL_HIT" else "⏰" if status == "EXPIRED" else "🔵"
            if status in RESOLVED_STATUSES and not calculate_canonical_trade_r(s).resolved:
                icon = "⚠️"
                status = f"{status} (UNRESOLVED)"
            sig_lines += f"{icon} {s['symbol']} {s['direction']} Grade:{s.get('grade','?')} → {status}\n"

        if not today_signals:
            msg = (
                f"📊 <b>Elite V6 — Daily Report</b>\n"
                f"📅 {today}\n\n"
                f"No signals fired today.\n"
                f"System is running — waiting for qualifying setups."
            )
        else:
            msg = (
                f"📊 <b>Elite V6 — Daily Report</b>\n"
                f"📅 {today} (today only)\n\n"
                f"📈 Signals Today: <b>{len(today_signals)}</b>\n"
                f"🔵 Active: <b>{len(active_today)}</b>\n"
                f"🏁 Resolved: <b>{resolved_total}</b>\n"
                f"⚠️ Unresolved: <b>{unresolved_today}</b>\n"
                f"⏰ Expired: <b>{len(expired_today)}</b>\n\n"
                f"🏆 Wins: <b>{len(wins_today)}</b>\n"
                f"❌ Losses: <b>{len(losses_today)}</b>\n"
                f"📊 WR Today: <b>{wr}%</b>\n\n"
                f"💰 PF: <b>{pf}</b>\n"
                f"📐 Net: <b>{net_r:+.2f}R</b>\n\n"
                f"<b>By Grade:</b>\n{grade_lines}\n"
                f"<b>Signals:</b>\n{sig_lines}"
            )

        send_telegram_alert(msg)
        print(f"📊 Daily report sent ({len(today_signals)} signals today)")
