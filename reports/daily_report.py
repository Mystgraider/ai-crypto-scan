from reports.analytics_engine import AnalyticsEngine
from alerts.telegram_alerts import send_telegram_alert


class DailyReport:

    def send(self):

        stats = AnalyticsEngine().compute()

        pf_str = str(stats["profit_factor"]) if stats["profit_factor"] else "N/A"
        ex_str = str(stats["expectancy_r"])  if stats["expectancy_r"]  else "N/A"

        msg = (
            f"📊 <b>ELITE V5 — Daily Report</b>\n\n"
            f"📈 Total Signals: <b>{stats['total_signals']}</b>\n"
            f"🟢 Open:   <b>{stats['open']}</b>\n"
            f"✅ Closed: <b>{stats['closed']}</b>\n\n"
            f"🏆 Wins:   <b>{stats['wins']}</b>\n"
            f"❌ Losses: <b>{stats['losses']}</b>\n"
            f"📊 Win Rate: <b>{stats['win_rate']}%</b>\n\n"
            f"💰 Profit Factor: <b>{pf_str}</b>\n"
            f"📐 Expectancy: <b>{ex_str}R</b>"
        )

        send_telegram_alert(msg)
        print("📊 Daily report sent.")
