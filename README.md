# Elite Futures Scanner V5

Automated 24/7 crypto futures signal platform with signal generation,
tracking, analytics, AI ranking, and daily reporting.

---

## Folder Structure

```
scanner_v5/
├── scanner_v5.py              # Main orchestrator
├── daily_report_runner.py     # Daily report entry point
├── config.py                  # Single source of truth for all settings
├── version.py                 # Version constants
├── requirements.txt
│
├── loaders/
│   ├── market_loader.py       # Exchange factory (OKX / Bitget)
│   ├── top_symbols_loader.py  # Top 300 futures by volume
│   └── market_data_loader.py  # OHLCV fetcher
│
├── indicators/
│   └── indicators.py          # EMA20/50, RSI, ATR, ADX, ROC, RelVol
│
├── engines/
│   ├── trend_engine.py        # Direction + trend score (0-100)
│   ├── quality_engine.py      # Volume + RSI quality score (0-100)
│   ├── risk_engine.py         # Entry, SL, TP1/2/3 + RR validation
│   └── validator.py           # Final signal gate
│
├── alerts/
│   └── telegram_alerts.py     # HTML-formatted Telegram sender
│
├── storage/
│   ├── signal_logger.py       # CSV signal log (signals.csv)
│   └── cooldown_manager.py    # Per-symbol cooldown (12h default)
│
├── tracker/
│   └── signal_tracker.py      # Checks open signals vs live price
│
├── reports/
│   ├── analytics_engine.py    # Win rate, PF, expectancy
│   └── daily_report.py        # Sends daily summary to Telegram
│
├── ai/
│   ├── signal_ranker.py       # Ranks candidates by composite score
│   └── confidence_engine.py   # Signal confidence estimate
│
└── .github/workflows/
    └── scanner.yml            # Every 5min scan + daily report
```

---

## Setup

1. Fork / clone the repo
2. Add GitHub Secrets:
   - `BOT_TOKEN` — your Telegram bot token
   - `CHAT_ID` — your Telegram chat/channel ID
3. Enable GitHub Actions
4. Scanner runs automatically every 5 minutes

---

## Signal Format (Telegram)

```
🚨 ELITE V5 SIGNAL

🟢 LONG — BTCUSDT
🏅 Grade: A  |  Score: 84.5

🎯 Entry: 67420.0
🛑 SL:    66800.0
✅ TP1:  68260.0
✅ TP2:  68680.0
✅ TP3:  69520.0

📐 RR: 2.1R
🤖 Confidence: 76%
```

---

## Development Phases

| Phase | Status | Scope |
|-------|--------|-------|
| 1 | ✅ Done | Core scanner, indicators, trend, Telegram, TP/SL, logging |
| 2 | ✅ Done | Cooldown manager, signal tracker |
| 3 | ✅ Done | Analytics, profit factor, daily report |
| 4 | 🔜 Next | BTC filter, multi-timeframe, relative strength upgrade |
| 5 | ✅ Done | AI signal ranker, confidence engine |
| 6 | 🔜 Next | Dashboard, full web analytics |
