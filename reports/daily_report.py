"""
Daily Report — V6.1
Shows TODAY's signals only (not historical)
Since strategy changes between versions, mixing old data
with new strategy gives misleading win rate.
"""

from datetime import datetime, timezone
from reports.analytics_engine import AnalyticsEngine
from storage.signal_logger    import load_signals
from alerts.telegram_alerts   import send_telegram_alert


class DailyReport:

    def send(self):

        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        all_signals = load_signals()

        # TODAY's signals only
        today_signals = [s for s in all_signals if s.get("timestamp","")[:10] == today]
        closed_today  = [s for s in today_signals if s["status"] in ("TP1_HIT","TP2_HIT","TP3_HIT","SL_HIT")]
        open_today    = [s for s in today_signals if s["status"] == "OPEN"]
        wins_today    = [s for s in closed_today  if s["status"] != "SL_HIT"]
        losses_today  = [s for s in closed_today  if s["status"] == "SL_HIT"]

        tp_r = {"TP1_HIT": 2.5, "TP2_HIT": 4.0, "TP3_HIT": 6.0}
        gross_win  = sum(tp_r.get(s["status"], 0) for s in wins_today)
        gross_loss = float(len(losses_today))
        net_r      = gross_win - gross_loss
        wr         = round(len(wins_today) / len(closed_today) * 100, 1) if closed_today else 0
        pf         = round(gross_win / gross_loss, 2) if gross_loss else 0

        # Grade breakdown today
        grade_lines = ""
        for g in ("S", "A", "B", "C"):
            g_sigs   = [s for s in today_signals if s.get("grade") == g]
            g_closed = [s for s in g_sigs if s["status"] in ("TP1_HIT","TP2_HIT","TP3_HIT","SL_HIT")]
            g_wins   = [s for s in g_closed if s["status"] != "SL_HIT"]
            if g_sigs:
                g_wr = round(len(g_wins)/len(g_closed)*100, 0) if g_closed else "-"
                grade_lines += f"  Grade {g}: {len(g_sigs)} signals | WR: {g_wr}%\n"

        # Signal list today
        sig_lines = ""
        for s in today_signals:
            icon = "✅" if "TP" in s["status"] else "❌" if "SL" in s["status"] else "🔵"
            sig_lines += f"{icon} {s['symbol']} {s['direction']} Grade:{s.get('grade','?')} → {s['status']}\n"

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
                f"🔵 Open:   <b>{len(open_today)}</b>\n"
                f"✅ Closed: <b>{len(closed_today)}</b>\n\n"
                f"🏆 Wins:   <b>{len(wins_today)}</b>\n"
                f"❌ Losses: <b>{len(losses_today)}</b>\n"
                f"📊 WR Today: <b>{wr}%</b>\n\n"
                f"💰 PF: <b>{pf}</b>\n"
                f"📐 Net: <b>{net_r:+.1f}R</b>\n\n"
                f"<b>By Grade:</b>\n{grade_lines}\n"
                f"<b>Signals:</b>\n{sig_lines}"
            )

        send_telegram_alert(msg)
        print(f"📊 Daily report sent ({len(today_signals)} signals today)")
