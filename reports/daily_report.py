from reports.analytics_engine import AnalyticsEngine
from alerts.telegram_alerts   import send_telegram_alert


class DailyReport:

    def send(self):

        stats = AnalyticsEngine().compute()

        if stats["total_signals"] == 0:
            send_telegram_alert(
                "📊 <b>Elite V5 — Daily Report</b>\n\n"
                "No signals logged yet.\n"
                "System is running — waiting for qualifying setups."
            )
            return

        pf  = stats["profit_factor"] or "N/A"
        exp = stats["expectancy_r"]  or "N/A"

        # Grade breakdown
        gs = stats["grade_stats"]
        grade_lines = ""
        for g in ("S", "A", "B", "C"):
            d = gs[g]
            if d["total"] > 0:
                grade_lines += f"  Grade {g}: {d['total']} signals | WR: {d['wr']}%\n"

        msg = (
            f"📊 <b>Elite V5 — Daily Report</b>\n\n"
            f"📈 Total Signals: <b>{stats['total_signals']}</b>\n"
            f"🟢 Open:   <b>{stats['open']}</b>\n"
            f"✅ Closed: <b>{stats['closed']}</b>\n\n"
            f"🏆 Wins:    <b>{stats['wins']}</b>\n"
            f"❌ Losses:  <b>{stats['losses']}</b>\n"
            f"📊 Win Rate: <b>{stats['win_rate']}%</b>\n\n"
            f"💰 Profit Factor: <b>{pf}</b>\n"
            f"📐 Expectancy: <b>{exp}R</b>\n"
            f"💵 Gross P: <b>+{stats['gross_profit_r']}R</b> | "
            f"Gross L: <b>-{stats['gross_loss_r']}R</b>\n\n"
            f"<b>By Grade:</b>\n{grade_lines}"
        )

        send_telegram_alert(msg)
        print("📊 Daily report sent.")
