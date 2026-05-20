import os
from dotenv import load_dotenv

load_dotenv()

BINANCE_EXCHANGE = "binance"

SYMBOL = "BTC/USDT"

TIMEFRAME = "15m"

RISK_PER_TRADE = 0.01

MIN_RR = 2.0

MAX_CONSECUTIVE_LOSSES = 3

MAX_DAILY_DRAWDOWN = 0.05

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")

TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
