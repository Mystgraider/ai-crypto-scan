import os
import time
import requests
import ccxt
import pandas as pd
import ta

from dotenv import load_dotenv
from datetime import datetime, timedelta

# =====================================
# LOAD ENV
# =====================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =====================================
# EXCHANGE
# =====================================

exchange = ccxt.okx({
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})

# =====================================
# SETTINGS
# =====================================

TIMEFRAME = "15m"

MIN_RR = 2.0

SCAN_INTERVAL = 300

SIGNAL_COOLDOWN_HOURS = 12

# =====================================
# FAST ROTATING COIN GROUPS
# =====================================

SYMBOL_GROUPS = [

    # GROUP 1 - MAJORS
    [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "XRP/USDT:USDT",
        "BNB/USDT:USDT"
    ],

    # GROUP 2 - MEME
    [
        "DOGE/USDT:USDT",
        "PEPE/USDT:USDT",
        "SHIB/USDT:USDT",
        "WIF/USDT:USDT",
        "BONK/USDT:USDT"
    ],

    # GROUP 3 - AI
    [
        "FET/USDT:USDT",
        "RNDR/USDT:USDT",
        "TAO/USDT:USDT",
        "WLD/USDT:USDT",
        "ARKM/USDT:USDT"
    ],

    # GROUP 4 - TRENDING
    [
        "ONDO/USDT:USDT",
        "SEI/USDT:USDT",
        "SUI/USDT:USDT",
        "INJ/USDT:USDT",
        "TIA/USDT:USDT"
    ],

    # GROUP 5 - MIDCAP
    [
        "AVAX/USDT:USDT",
        "ARB/USDT:USDT",
        "OP/USDT:USDT",
        "LINK/USDT:USDT",
        "APT/USDT:USDT"
    ]
]

# =====================================
# MEMORY
# =====================================

last_signal_times = {}

current_group = 0

# =====================================
# LOAD DATA
# =====================================

def load_ohlcv(
    symbol,
    timeframe="15m",
    limit=50
):

    ohlcv = exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=limit
    )

    df = pd.DataFrame(
        ohlcv,
        columns=[
            "timestamp",
            "open",
            "high",
            "low",
            "close",
            "volume"
        ]
    )

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="ms"
    )

    return df

# =====================================
# INDICATORS
# =====================================

def apply_indicators(df):

    df["ema_20"] = ta.trend.ema_indicator(
        df["close"],
        window=20
    )

    df["ema_50"] = ta.trend.ema_indicator(
        df["close"],
        window=50
    )

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    df["atr"] = ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"]
    )

    df["roc"] = ta.momentum.roc(
        df["close"],
        window=5
    )

    return df

# =====================================
# MARKET REGIME
# =====================================

def detect_market_regime(df):

    atr = df["atr"].iloc[-1]

    price = df["close"].iloc[-1]

    atr_percent = (atr / price) * 100

    ema20 = df["ema_20"].iloc[-1]

    ema50 = df["ema_50"].iloc[-1]

    if atr_percent < 0.5:
        return "dead_market"

    if abs(ema20 - ema50) < price * 0.001:
        return "ranging"

    if atr_percent > 3:
        return "volatile"

    return "trending"

# =====================================
# TREND
# =====================================

def analyze_trend(df):

    ema20 = df["ema_20"].iloc[-1]

    ema50 = df["ema_50"].iloc[-1]

    if ema20 > ema50:
        direction = "bullish"
    else:
        direction = "bearish"

    return {
        "direction": direction
    }

# =====================================
# MOMENTUM
# =====================================

def analyze_momentum(df):

    roc = df["roc"].iloc[-1]

    rsi = df["rsi"].iloc[-1]

    strong = abs(roc) > 0.5

    return {
        "roc": round(roc, 2),
        "rsi": round(rsi, 2),
        "strong": strong
    }

# =====================================
# VOLATILITY
# =====================================

def analyze_volatility(df):

    atr = df["atr"].iloc[-1]

    price = df["close"].iloc[-1]

    volatility = (atr / price) * 100

    return {
        "volatility_percent": round(volatility, 2),
        "active": volatility >= 0.5
    }

# =====================================
# VOLUME
# =====================================

def analyze_volume(df):

    current_volume = df["volume"].iloc[-1]

    average_volume = (
        df["volume"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    relative_volume = (
        current_volume / average_volume
    )

    return {
        "relative_volume": round(relative_volume, 2),
        "strong_volume": relative_volume >= 1.0
    }

# =====================================
# FILTER
# =====================================

def should_skip_trade(
    momentum,
    volatility,
    volume,
    regime
):

    if not momentum["strong"]:
        return True, "Weak momentum"

    if not volatility["active"]:
        return True, "Low volatility"

    if not volume["strong_volume"]:
        return True, "Weak volume"

    if regime == "dead_market":
        return True, "Dead market"

    return False, "Valid"

# =====================================
# RISK MANAGER
# =====================================

def calculate_trade_levels(
    price,
    atr,
    direction
):

    sl_distance = atr * 1.5

    if direction == "bullish":

        stop_loss = (
            price - sl_distance
        )

        take_profit = (
            price + (
                sl_distance * MIN_RR
            )
        )

    else:

        stop_loss = (
            price + sl_distance
        )

        take_profit = (
            price - (
                sl_distance * MIN_RR
            )
        )

    return {
        "entry": round(price, 4),
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
        "rr": MIN_RR
    }

# =====================================
# TELEGRAM ALERT
# =====================================

def send_telegram_alert(message):

    if not TELEGRAM_TOKEN:
        return

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    requests.post(url, json=payload)

# =====================================
# MARKET SCAN
# =====================================

def scan_market():

    global current_group
    global last_signal_times

    symbols = SYMBOL_GROUPS[current_group]

    print(f"\nScanning Group {current_group + 1}")

    for symbol in symbols:

        try:

            df = load_ohlcv(
                symbol,
                TIMEFRAME
            )

            if len(df) < 50:
                continue

            df = apply_indicators(df)

            regime = detect_market_regime(df)

            trend = analyze_trend(df)

            momentum = analyze_momentum(df)

            volatility = analyze_volatility(df)

            volume = analyze_volume(df)

            skip, reason = should_skip_trade(
                momentum,
                volatility,
                volume,
                regime
            )

            if skip:
                continue

            now = datetime.utcnow()

            last_time = last_signal_times.get(symbol)

            if last_time:

                elapsed = now - last_time

                if elapsed < timedelta(
                    hours=SIGNAL_COOLDOWN_HOURS
                ):
                    continue

            price = df["close"].iloc[-1]

            atr = df["atr"].iloc[-1]

            levels = calculate_trade_levels(
                price,
                atr,
                trend["direction"]
            )

            signal_type = (
                "LONG"
                if trend["direction"] == "bullish"
                else "SHORT"
            )

            message = f"""
━━━━━━━━━━━━━━━━━━
🏆 CLEAN MARKET SIGNAL
━━━━━━━━━━━━━━━━━━

🪙 Symbol: {symbol}

📢 Signal: {signal_type}

━━━━━━━━━━━━━━━━━━
📊 Market Analysis
━━━━━━━━━━━━━━━━━━

📈 Regime: {regime}

Momentum ROC: {momentum['roc']}%

RSI: {momentum['rsi']}

Volatility: {volatility['volatility_percent']}%

Relative Volume: {volume['relative_volume']}

━━━━━━━━━━━━━━━━━━
🎯 Trade Execution
━━━━━━━━━━━━━━━━━━

💰 Entry: {levels['entry']}

🛑 Stop Loss: {levels['stop_loss']}

🎯 Take Profit: {levels['take_profit']}

⚖ Risk Reward: 1:{levels['rr']}

━━━━━━━━━━━━━━━━━━
⚠ IMPORTANT
━━━━━━━━━━━━━━━━━━

Probability-based setup only.

No guaranteed outcome.
"""

            print(message)

            send_telegram_alert(message)

            last_signal_times[symbol] = now

        except Exception as e:

            print(f"ERROR {symbol}: {e}")

    current_group += 1

    if current_group >= len(SYMBOL_GROUPS):
        current_group = 0

# =====================================
# LOOP
# =====================================

if __name__ == "__main__":

    while True:

        print(
            f"\n[{datetime.utcnow()}] "
            f"Starting market scan..."
        )

        scan_market()

        print(
            f"\nSleeping {SCAN_INTERVAL} seconds..."
        )

        time.sleep(SCAN_INTERVAL)
