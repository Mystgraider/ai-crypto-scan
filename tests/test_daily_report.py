from datetime import datetime, timezone
from unittest.mock import patch

from reports.daily_report import DailyReport


def test_unresolved_terminal_trade_is_not_counted_as_daily_loss():
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    signals = [
        {
            "timestamp": f"{today}T01:00:00+00:00",
            "status": "TP3_HIT",
            "symbol": "UNRESOLVED/USDT",
            "direction": "LONG",
            "grade": "A",
            "realized_r": "",
        },
        {
            "timestamp": f"{today}T02:00:00+00:00",
            "status": "SL_HIT",
            "symbol": "LOSS/USDT",
            "direction": "LONG",
            "grade": "A",
            "entry": "100",
            "initial_sl": "98",
            "exit_price": "98",
            "realized_r": "-1.0",
        },
    ]

    with patch("reports.daily_report.load_signals", return_value=signals), patch(
        "reports.daily_report.send_telegram_alert"
    ) as send_alert:
        DailyReport().send()

    message = send_alert.call_args.args[0]
    assert "🏁 Resolved: <b>1</b>" in message
    assert "⚠️ Unresolved: <b>1</b>" in message
    assert "🏆 Wins: <b>0</b>" in message
    assert "❌ Losses: <b>1</b>" in message
    assert "📐 Net: <b>-1.00R</b>" in message
    assert "TP3_HIT (UNRESOLVED)" in message
