# =====================================
# IMPORTS
# =====================================

import os
import json
import time
import requests
import ccxt
import pandas as pd

from dotenv import load_dotenv
from datetime import datetime, timedelta

# =====================================
# LOAD ENV
# =====================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# =====================================
# EXCHANGE
# =====================================

exchange = ccxt.bitget({
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})

# =====================================
# SETTINGS
# =====================================

TOP_COINS_LIMIT = 300

MIN_LIQUIDITY_USDT = 5_000_000

MIN_SL_PCT = 0.005

MIN_RR = 2.0

# =====================================
# COOLDOWN SYSTEM
# =====================================

SIGNAL_COOLDOWN_HOURS = 12

COOLDOWN_FILE = "last_signal_times.json"

def load_signal_times():

    if os.path.exists(COOLDOWN_FILE):

        with open(COOLDOWN_FILE, "r") as f:

            raw = json.load(f)

        return {
            k: datetime.fromisoformat(v)
            for k, v in raw.items()
        }

    return {}

def save_signal_times(signal_times):

    raw = {
        k: v.isoformat()
        for k, v in signal_times.items()
    }

    with open(COOLDOWN_FILE, "w") as f:

        json.dump(raw, f, indent=2)

def is_on_cooldown(symbol, signal_times, now):

    last = signal_times.get(symbol)

    if not last:
        return False

    return (
        now - last
    ) < timedelta(hours=SIGNAL_COOLDOWN_HOURS)

# =====================================
# TELEGRAM
# =====================================

def send_telegram_alert(message):

    if not BOT_TOKEN:
        return

    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:

        requests.post(
            url,
            json=payload,
            timeout=10
        )

    except Exception as e:

        print(e)

# =====================================
# LOAD OHLCV
# =====================================

def load_ohlcv(symbol, timeframe, limit=40):

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

    return df

# =====================================
# INDICATORS
# =====================================

def apply_indicators(df):

    df["ema20"] = (
        df["close"]
        .ewm(span=20)
        .mean()
    )

    df["ema50"] = (
        df["close"]
        .ewm(span=50)
        .mean()
    )

    tr = (
        df["high"] - df["low"]
    )

    df["atr"] = (
        tr.rolling(14).mean()
    )

    df["vol_ma"] = (
        df["volume"]
        .rolling(20)
        .mean()
    )

    df["rel_vol"] = (
        df["volume"] /
        df["vol_ma"]
    )

    return df

# =====================================
# TREND DETECTION
# =====================================

def detect_trend(df):

    ema20 = df["ema20"].iloc[-2]

    ema50 = df["ema50"].iloc[-2]

    price = df["close"].iloc[-2]

    if ema20 > ema50 and price > ema20:
        return "bullish"

    if ema20 < ema50 and price < ema20:
        return "bearish"

    return None

# =====================================
# BTC ENGINE
# =====================================

def get_btc_market_state():

    try:

        df = load_ohlcv(
            "BTC/USDT:USDT",
            "1h",
            40
        )

        df = apply_indicators(df)

        trend = detect_trend(df)

        atr = df["atr"].iloc[-2]

        price = df["close"].iloc[-2]

        volatility = atr / price

        if volatility > 0.03:

            vol = "HIGH"

        elif volatility > 0.015:

            vol = "NORMAL"

        else:

            vol = "LOW"

        return {
            "trend": (
                "BULL"
                if trend == "bullish"
                else "BEAR"
            ),
            "volatility": vol,
            "safe": vol != "HIGH"
        }

    except:

        return {
            "trend": "UNKNOWN",
            "volatility": "UNKNOWN",
            "safe": False
        }

# =====================================
# TOP COINS
# =====================================

def get_top_symbols(limit=300):

    markets = exchange.load_markets()

    pairs = []

    for symbol, market in markets.items():

        try:

            if not market.get("swap"):
                continue

            if "/USDT" not in symbol:
                continue

            ticker = exchange.fetch_ticker(symbol)

            volume = ticker.get(
                "quoteVolume",
                0
            )

            if volume < MIN_LIQUIDITY_USDT:
                continue

            pairs.append({
                "symbol": symbol,
                "volume": volume
            })

        except:
            continue

    pairs.sort(
        key=lambda x: x["volume"],
        reverse=True
    )

    return [
        x["symbol"]
        for x in pairs[:limit]
    ]

# =====================================
# MAIN SCAN
# =====================================

def scan_all():

    signal_times = load_signal_times()

    now = datetime.utcnow()

    print(f"\n[{now}] ELITE SCAN STARTED\n")

    btc_state = get_btc_market_state()

    print(
        f"BTC Trend: {btc_state['trend']}"
    )

    print(
        f"BTC Volatility: "
        f"{btc_state['volatility']}"
    )

    if not btc_state["safe"]:

        print("High volatility")

        return

    ALL_SYMBOLS = get_top_symbols(
        TOP_COINS_LIMIT
    )

    signals_found = 0

    for symbol in ALL_SYMBOLS:

        try:

            if is_on_cooldown(
                symbol,
                signal_times,
                now
            ):
                continue

            df_4h = load_ohlcv(
                symbol,
                "4h",
                40
            )

            df_4h = apply_indicators(
                df_4h
            )

            direction = detect_trend(
                df_4h
            )

            if direction is None:
                continue

            if (
                btc_state["trend"] == "BULL"
                and direction != "bullish"
            ):
                continue

            if (
                btc_state["trend"] == "BEAR"
                and direction != "bearish"
            ):
                continue

            df_1h = load_ohlcv(
                symbol,
                "1h",
                40
            )

            df_1h = apply_indicators(
                df_1h
            )

            df_15m = load_ohlcv(
                symbol,
                "15m",
                40
            )

            df_15m = apply_indicators(
                df_15m
            )

            price = (
                df_15m["close"]
                .iloc[-2]
            )

            atr_1h = (
                df_1h["atr"]
                .iloc[-2]
            )

            rel_vol = (
                df_15m["rel_vol"]
                .iloc[-2]
            )

            if rel_vol < 0.7:
                continue

            signal = (
                "LONG 🟢"
                if direction == "bullish"
                else "SHORT 🔴"
            )

            sl_distance = max(
                atr_1h * 1.5,
                price * MIN_SL_PCT
            )

            if direction == "bullish":

                stop_loss = (
                    price - sl_distance
                )

                take_profit = (
                    price +
                    (sl_distance * MIN_RR)
                )

            else:

                stop_loss = (
                    price + sl_distance
                )

                take_profit = (
                    price -
                    (sl_distance * MIN_RR)
                )

            if price < 0.0001:

                decimals = 10

            elif price < 0.01:

                decimals = 8

            elif price < 1:

                decimals = 6

            else:

                decimals = 4

            message = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏆 ELITE SIGNAL\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🪙 {symbol}\n"
                f"📢 {signal}\n"
                f"🏦 Bitget Futures\n\n"
                f"BTC Trend: "
                f"{btc_state['trend']}\n"
                f"Volatility: "
                f"{btc_state['volatility']}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 ANALYSIS\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ Trend aligned\n"
                f"✅ Strong momentum\n"
                f"✅ Relative Volume: "
                f"{round(rel_vol,2)}x\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 EXECUTION\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Entry: "
                f"{round(price, decimals)}\n"
                f"🛑 Stop Loss: "
                f"{round(stop_loss, decimals)}\n"
                f"🎯 Take Profit: "
                f"{round(take_profit, decimals)}\n"
                f"⚖ RR: 1:{MIN_RR}\n"
            )

            print(
                f"✅ SIGNAL: "
                f"{symbol} {signal}"
            )

            print(message)

            send_telegram_alert(message)

            signal_times[symbol] = now

            signals_found += 1

            time.sleep(0.15)

        except Exception as e:

            print(
                f"ERROR {symbol}: {e}"
            )

    save_signal_times(signal_times)

    print(
        f"\nDONE: "
        f"{signals_found} signals sent.\n"
    )

# =====================================
# ENTRY
# =====================================

if __name__ == "__main__":

    scan_all()
