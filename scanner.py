import os
import time
import requests
import ccxt
import pandas as pd
import ta

from dotenv import load_dotenv

# =========================
# LOAD ENV
# =========================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# =========================
# EXCHANGE
# =========================

exchange = ccxt.okx({
    "enableRateLimit": True
})

# =========================
# SETTINGS
# =========================

TIMEFRAME = "15m"

MIN_RR = 2.0

SCAN_INTERVAL = 60

SYMBOLS = [

    # MAJORS
    "BTC/USDT",
    "ETH/USDT",
    "BNB/USDT",
    "SOL/USDT",
    "XRP/USDT",

    # MID CAPS
    "ONDO/USDT",
    "LINK/USDT",
    "AVAX/USDT",
    "ARB/USDT",
    "OP/USDT",

    # MEME COINS
    "DOGE/USDT",
    "SHIB/USDT",
    "PEPE/USDT",
    "WIF/USDT",
    "BONK/USDT",
    "FLOKI/USDT",

    # VOLATILE
    "SUI/USDT",
    "SEI/USDT",
    "APT/USDT",
    "INJ/USDT",
    "TIA/USDT"
]

# =========================
# LOAD MARKET DATA
# =========================

def load_ohlcv(symbol, timeframe="15m", limit=300):

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

# =========================
# INDICATORS
# =========================

def apply_indicators(df):

    df["ema_20"] = ta.trend.ema_indicator(
        df["close"],
        window=20
    )

    df["ema_50"] = ta.trend.ema_indicator(
        df["close"],
        window=50
    )

    df["adx"] = ta.trend.adx(
        df["high"],
        df["low"],
        df["close"]
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

# =========================
# MARKET REGIME
# =========================

def detect_market_regime(df):

    atr = df["atr"].iloc[-1]

    price = df["close"].iloc[-1]

    atr_percent = (atr / price) * 100

    ema20 = df["ema_20"].iloc[-1]

    ema50 = df["ema_50"].iloc[-1]

    if atr_percent < 1:
        return "dead_market"

    if abs(ema20 - ema50) < price * 0.002:
        return "ranging"

    if atr_percent > 3:
        return "volatile"

    return "trending"

# =========================
# TREND ANALYSIS
# =========================

def analyze_trend(df):

    ema20 = df["ema_20"].iloc[-1]

    ema50 = df["ema_50"].iloc[-1]

    adx = df["adx"].iloc[-1]

    if ema20 > ema50:
        direction = "bullish"
    else:
        direction = "bearish"

    if adx > 30:
        strength = "strong"

    elif adx > 20:
        strength = "moderate"

    else:
        strength = "weak"

    return {
        "direction": direction,
        "strength": strength,
        "adx": round(adx, 2)
    }

# =========================
# MOMENTUM
# =========================

def analyze_momentum(df):

    roc = df["roc"].iloc[-1]

    rsi = df["rsi"].iloc[-1]

    strong = abs(roc) > 2

    return {
        "roc": round(roc, 2),
        "rsi": round(rsi, 2),
        "strong": strong
    }

# =========================
# VOLATILITY
# =========================

def analyze_volatility(df):

    atr = df["atr"].iloc[-1]

    price = df["close"].iloc[-1]

    volatility = (atr / price) * 100

    return {
        "volatility_percent": round(volatility, 2),
        "active": volatility >= 1.5
    }

# =========================
# VOLUME
# =========================

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
        "strong_volume": relative_volume >= 1.5
    }

# =========================
# LIQUIDITY SWEEP
# =========================

def detect_liquidity_sweep(df):

    last = df.iloc[-1]

    body = abs(
        last["close"] - last["open"]
    )

    wick = last["high"] - max(
        last["close"],
        last["open"]
    )

    sweep = wick > body * 2

    return {
        "liquidity_sweep": sweep
    }

# =========================
# NO TRADE FILTER
# =========================

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

    return False, "Valid setup"

# =========================
# RISK MANAGER
# =========================

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

# =========================
# TELEGRAM ALERT
# =========================

def send_telegram_alert(message):

    url = (
        f"https://api.telegram.org/bot"
        f"{TELEGRAM_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message
    }

    requests.post(url, json=payload)

# =========================
# MAIN SCANNER
# =========================

def scan_market():

    for symbol in SYMBOLS:

        try:

            print(f"Scanning {symbol}")

            df = load_ohlcv(
                symbol,
                TIMEFRAME
            )

            df = apply_indicators(df)

            regime = detect_market_regime(df)

            trend = analyze_trend(df)

            momentum = analyze_momentum(df)

            volatility = analyze_volatility(df)

            volume = analyze_volume(df)

            liquidity = detect_liquidity_sweep(df)

            skip, reason = should_skip_trade(
                momentum,
                volatility,
                volume,
                regime
            )

            if skip:

                print(
                    f"{symbol} SKIPPED: {reason}"
                )

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

            message = f'''
━━━━━━━━━━━━━━━━━━
🏆 CLEAN MARKET SIGNAL
━━━━━━━━━━━━━━━━━━

🪙 Symbol: {symbol}

📢 Signal: {signal_type}

━━━━━━━━━━━━━━━━━━
📊 Market Analysis
━━━━━━━━━━━━━━━━━━

📈 Regime: {regime}

📊 Trend Strength: {trend['strength']}

ADX: {trend['adx']}

Momentum ROC: {momentum['roc']}%

RSI: {momentum['rsi']}

Volatility: {volatility['volatility_percent']}%

Relative Volume: {volume['relative_volume']}

Liquidity Sweep: {liquidity['liquidity_sweep']}

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

Avoid overleveraging.
'''

            print(message)

            send_telegram_alert(message)

        except Exception as e:

            print(
                f"ERROR {symbol}: {e}"
            )

# =========================
# LOOP
# =========================

if __name__ == "__main__":

    while True:

        print("Starting market scan...")

        scan_market()

        print(
            f"Sleeping {SCAN_INTERVAL} seconds..."
        )

        time.sleep(SCAN_INTERVAL)
