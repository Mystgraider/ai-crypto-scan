"""
Daily Loss Circuit Breaker — V5.8
====================================
Stops firing signals if daily losses exceed threshold.

Protects capital on bad market days where even good setups fail
(e.g. unexpected news, flash crash, liquidity crisis).

Rules:
  Track canonical negative outcomes TODAY (UTC) from signals.csv.
  Unresolved outcomes are excluded from the loss count.
  If losses >= MAX_DAILY_LOSSES → pause signals for rest of day.
  Sends Telegram alert when triggered.

Default: pause after 3 canonical losing trades in one day.
"""

import json
import os
from datetime import datetime, timezone

from reports.execution_outcome import calculate_canonical_trade_r
from storage.signal_logger import load_signals
from alerts.telegram_alerts import send_telegram_alert

BREAKER_FILE = "storage/circuit_breaker.json"
MAX_DAILY_LOSSES = 3


def _load_state() -> dict:
    if os.path.exists(BREAKER_FILE):
        try:
            with open(BREAKER_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {"tripped_date": None, "losses_today": 0}


def _save_state(state: dict):
    os.makedirs("storage", exist_ok=True)
    with open(BREAKER_FILE, "w") as f:
        json.dump(state, f)


def _count_canonical_losses(signals: list[dict], today: str) -> int:
    """Count today's resolved trades whose canonical realized R is negative."""
    losses = 0
    for signal in signals:
        if signal.get("timestamp", "")[:10] != today:
            continue

        outcome = calculate_canonical_trade_r(signal)
        if outcome.resolved and outcome.realized_r is not None and outcome.realized_r < 0.0:
            losses += 1

    return losses


def check() -> dict:
    """
    Check if circuit breaker is tripped.
    Returns dict with is_tripped, losses_today, max_losses.
    """

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    state = _load_state()

    # Count today's canonical negative outcomes. This intentionally does not
    # equate SL_HIT with a loss: a trade may have realized positive R before
    # its remaining position reaches a stop/breakeven level.
    signals = load_signals()
    losses_today = _count_canonical_losses(signals, today)

    is_tripped = losses_today >= MAX_DAILY_LOSSES

    # Send alert first time it trips today
    if is_tripped and state.get("tripped_date") != today:
        state["tripped_date"] = today
        state["losses_today"] = losses_today
        _save_state(state)

        send_telegram_alert(
            f"🔴 <b>CIRCUIT BREAKER TRIPPED</b>\n\n"
            f"Daily losses: <b>{losses_today}</b> losing trades today\n"
            f"Signals PAUSED for rest of day (UTC).\n\n"
            f"Resumes automatically tomorrow at 00:00 UTC.\n"
            f"Review market conditions before manual override."
        )
        print(f"  🔴 Circuit breaker tripped: {losses_today} losses today")

    return {
        "is_tripped":    is_tripped,
        "losses_today":  losses_today,
        "max_losses":    MAX_DAILY_LOSSES,
        "today":         today,
    }
