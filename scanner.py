import os import json import time import requests import ccxt import pandas as pd

from dotenv import load_dotenv from datetime import datetime, timedelta

=====================================

LOAD ENV

=====================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN") CHAT_ID = os.getenv("CHAT_ID")

=====================================

EXCHANGE

=====================================

exchange = ccxt.bitget({ "enableRateLimit": True, "options": { "defaultType": "swap" } })

=====================================

SETTINGS

=====================================

MIN_SCORE = 3 MIN_RR = 2.0 MIN_SL_PCT = 0.005

SIGNAL_COOLDOWN_HOURS = 12 COOLDOWN_FILE = "last_signal_times.json"

TOP_COINS_LIMIT = 300 MIN_LIQUIDITY_USDT = 5_000_000

=====================================

COOLDOWN

=====================================

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

=====================================

DYNAMIC TOP COINS

=====================================

def get_top_symbols(limit=300):

try:

    print("Loading futures markets...")

    markets = exchange.load_markets()

    valid_symbols = []

    blacklist = [
        "USDC",
        "FDUSD",
        "TUSD",
        "BUSD"
    ]

    for symbol, market in markets.items():

        try:

            if not market.get("swap"):
                continue

            if "/USDT" not in symbol:
                continue

            if any(x in symbol for x in blacklist):
                continue

            if not market.get("active", True):
                continue

            ticker = exchange.fetch_ticker(symbol)

            volume = ticker.get(
                "quoteVolume",
                0
            )

            if volume is None:
                volume = 0

            valid_symbols.append({
                "symbol": symbol,
                "volume": volume
            })

        except:
            continue

    valid_symbols.sort(
        key=lambda x: x["volume"],
        reverse=True
    )

    top_symbols = [
        x["symbol"]
        for x in valid_symbols[:limit]
    ]

    print(
        f"Loaded {len(top_symbols)} coins"
    )

    return top_symbols

except Exception as e:

    print(
        f"Market loading error: {e}"
    )

    return []

=====================================

LOAD OHLCV

=====================================

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

df["timestamp"] = pd.to_datetime(
    df["timestamp"],
    unit="ms"
)

return df

=====================================

INDICATORS

=====================================

def apply_indicators(df):

df["ema_20"] = df["close"].ewm(
    span=20,
    adjust=False
).mean()

df["ema_50"] = df["close"].ewm(
    span=50,
    adjust=False
).mean()

delta = df["close"].diff()

gain = delta.clip(lower=0)
loss = -delta.clip(upper=0)

avg_gain = gain.ewm(
    com=13,
    adjust=False
).mean()

avg_loss = loss.ewm(
    com=13,
    adjust=False
).mean()

rs = avg_gain / avg_loss

df["rsi"] = 100 - (100 / (1 + rs))

hl = df["high"] - df["low"]

hc = (
    df["high"] -
    df["close"].shift()
).abs()

lc = (
    df["low"] -
    df["close"].shift()
).abs()

tr = pd.concat(
    [hl, hc, lc],
    axis=1
).max(axis=1)

df["atr"] = tr.ewm(
    com=13,
    adjust=False
).mean()

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

=====================================

BTC MARKET ENGINE

=====================================

def get_btc_market_state():

try:

    df = load_ohlcv(
        "BTC/USDT:USDT",
        "1h",
        limit=40
    )

    df = apply_indicators(df)

    ema20 = df["ema_20"].iloc[-2]
    ema50 = df["ema_50"].iloc[-2]
    price = df["close"].iloc[-2]
    atr = df["atr"].iloc[-2]

    volatility_pct = atr / price

    if ema20 > ema50:
        trend = "BULL"

    elif ema20 < ema50:
        trend = "BEAR"

    else:
        trend = "RANGE"

    if volatility_pct > 0.03:
        volatility = "HIGH"

    elif volatility_pct > 0.015:
        volatility = "NORMAL"

    else:
        volatility = "LOW"

    return {
        "trend": trend,
        "volatility": volatility,
        "safe": volatility != "HIGH"
    }

except:

    return {
        "trend": "UNKNOWN",
        "volatility": "UNKNOWN",
        "safe": False
    }

=====================================

TREND DETECTOR

=====================================

def detect_trend(df):

ema20 = df["ema_20"].iloc[-2]
ema50 = df["ema_50"].iloc[-2]
price = df["close"].iloc[-2]

gap_pct = abs(
    ema20 - ema50
) / price

if gap_pct < 0.002:
    return None

if ema20 > ema50 and price > ema20:
    return "bullish"

if ema20 < ema50 and price < ema20:
    return "bearish"

return None

=====================================

RELATIVE STRENGTH

=====================================

def relative_strength_score(symbol):

try:

    btc_df = load_ohlcv(
        "BTC/USDT:USDT",
        "1h",
        limit=20
    )

    alt_df = load_ohlcv(
        symbol,
        "1h",
        limit=20
    )

    btc_change = (
        btc_df["close"].iloc[-2]
        -
        btc_df["close"].iloc[-10]
    ) / btc_df["close"].iloc[-10]

    alt_change = (
        alt_df["close"].iloc[-2]
        -
        alt_df["close"].iloc[-10]
    ) / alt_df["close"].iloc[-10]

    rs = alt_change - btc_change

    if rs > 0.02:
        return 1, f"RS Strong ({round(rs*100,2)}%)"

    return 0, f"RS Weak ({round(rs*100,2)}%)"

except:
    return 0, "RS Error"

=====================================

BREAKOUT QUALITY

=====================================

def breakout_quality(df, direction):

candle = df.iloc[-2]

body = abs(
    candle["close"] -
    candle["open"]
)

range_size = (
    candle["high"] -
    candle["low"]
)

if range_size == 0:
    return 0, "Breakout invalid"

body_ratio = body / range_size

if body_ratio < 0.6:
    return 0, "Weak breakout"

if direction == "bullish":

    upper_wick = (
        candle["high"] -
        candle["close"]
    )

    if upper_wick > body:
        return 0, "Heavy rejection"

if direction == "bearish":

    lower_wick = (
        candle["close"] -
        candle["low"]
    )

    if lower_wick > body:
        return 0, "Heavy rejection"

return 1, "Clean breakout"

=====================================

MOMENTUM PERSISTENCE

=====================================

def momentum_persistence(df, direction):

closes = df["close"].tail(4).tolist()

if direction == "bullish":

    if closes[3] > closes[2] > closes[1]:
        return 1, "Momentum strong"

if direction == "bearish":

    if closes[3] < closes[2] < closes[1]:
        return 1, "Momentum strong"

return 0, "Momentum weak"

=====================================

OVEREXTENSION FILTER

=====================================

def overextension_filter(df):

price = df["close"].iloc[-2]
ema20 = df["ema_20"].iloc[-2]

distance = abs(
    price - ema20
) / ema20

if distance > 0.05:
    return False, (
        f"Overextended "
        f"({round(distance*100,2)}%)"
    )

return True, "Healthy extension"

=====================================

RETEST CONFIRMATION

=====================================

def retest_confirmation(df, direction):

try:

    breakout_candle = df.iloc[-3]
    retest_candle = df.iloc[-2]

    breakout_high = breakout_candle["high"]
    breakout_low = breakout_candle["low"]

    if direction == "bullish":

        if retest_candle["low"] <= breakout_high:

            if retest_candle["close"] > breakout_high:
                return 1, "Retest confirmed"

    if direction == "bearish":

        if retest_candle["high"] >= breakout_low:

            if retest_candle["close"] < breakout_low:
                return 1, "Retest confirmed"

    return 0, "Retest failed"

except:

    return 0, "Retest error"

=====================================

OPEN INTEREST

=====================================

def open_interest_score(symbol):

try:

    oi = exchange.fetch_open_interest(symbol)

    current_oi = oi.get(
        "openInterestAmount",
        None
    )

    if current_oi is None:
        return 0, "OI unavailable"

    return 1, "OI Active"

except:
    return 0, "OI error"

=====================================

RISK MANAGER

=====================================

def calculate_trade_levels(price, atr_1h, direction):

min_sl = price * MIN_SL_PCT

sl_distance = max(
    atr_1h * 1.5,
    min_sl
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

return {
    "entry": round(price, decimals),
    "stop_loss": round(stop_loss, decimals),
    "take_profit": round(take_profit, decimals),
    "rr": MIN_RR
}

=====================================

TELEGRAM

=====================================

def send_telegram_alert(message):

if not BOT_TOKEN:
    print("No BOT_TOKEN")
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

    print("Telegram Error:", e)

=====================================

MAIN SCAN

=====================================

def scan_all():

signal_times = load_signal_times()

now = datetime.utcnow()

print(f"

[{now}] ELITE SCAN STARTED ")

btc_state = get_btc_market_state()

print(
    f"BTC Trend: {btc_state['trend']}"
)

print(
    f"BTC Volatility: "
    f"{btc_state['volatility']}"
)

if not btc_state["safe"]:

    print(
        "⚠ Defensive Mode High Volatility"
    )

    return

ALL_SYMBOLS = get_top_symbols(TOP_COINS_LIMIT)

signals_found = 0

for symbol in ALL_SYMBOLS:

    try:

        if is_on_cooldown(
            symbol,
            signal_times,
            now
        ):
            continue

        try:

            ticker = exchange.fetch_ticker(symbol)

            quote_volume = ticker.get(
                "quoteVolume",
                0
            )

            if quote_volume < MIN_LIQUIDITY_USDT:

                print(
                    f"Skip {symbol}: low liquidity"
                )

                continue

        except:
            continue

        df_4h = load_ohlcv(
            symbol,
            "4h",
            limit=40
        )

        df_4h = apply_indicators(df_4h)

        direction = detect_trend(df_4h)

        if direction is None:
            continue

        if btc_state["trend"] == "BULL" and direction != "bullish":
            continue

        if btc_state["trend"] == "BEAR" and direction != "bearish":
            continue

        df_1h = load_ohlcv(
            symbol,
            "1h",
            limit=40
        )

        df_1h = apply_indicators(df_1h)

        df_15m = load_ohlcv(
            symbol,
            "15m",
            limit=40
        )

        df_15m = apply_indicators(df_15m)

        price = df_15m["close"].iloc[-2]

        atr_1h = df_1h["atr"].iloc[-2]

        rel_vol = (
            df_15m["rel_vol"].iloc[-2]
        )

        if rel_vol < 0.7:
            continue

        s_rs, l_rs = (
            relative_strength_score(symbol)
        )

        if s_rs == 0:
            continue

        s_break, l_break = (
            breakout_quality(
                df_15m,
                direction
            )
        )

        if s_break == 0:
            continue

        s_momo, l_momo = (
            momentum_persistence(
                df_15m,
                direction
            )
        )

        if s_momo == 0:
            continue

        s_retest, l_retest = (
            retest_confirmation(
                df_15m,
                direction
            )
        )

        if s_retest == 0:
            continue

        safe_ext, ext_label = (
            overextension_filter(df_15m)
        )

        if not safe_ext:
            continue

        s_oi, l_oi = (
            open_interest_score(symbol)
        )

        total_score = (
            s_rs +
            s_break +
            s_momo
        )

        final_score = (
            total_score +
            s_oi
        )

        if total_score < MIN_SCORE:
            continue

        levels = calculate_trade_levels(
            price,
            atr_1h,
            direction
        )

        signal = (
            "LONG 🟢"
            if direction == "bullish"
            else "SHORT 🔴"
        )

        message = (
            f"━━━━━━━━━━━━━━━━━━

" f"🏆 ELITE SIGNAL " f"━━━━━━━━━━━━━━━━━━

" f"🪙 {symbol} " f"📢 {signal} " f"🏦 Bitget Futures

" f"BTC Trend: {btc_state['trend']} " f"Volatility: {btc_state['volatility']}

" f"━━━━━━━━━━━━━━━━━━ " f"📊 ANALYSIS " f"━━━━━━━━━━━━━━━━━━

" f"✅ {l_rs} " f"✅ {l_break} " f"✅ {l_momo} " f"✅ {l_retest} " f"✅ {ext_label} " f"ℹ {l_oi} " f"✅ Relative Volume: {round(rel_vol,2)}x

" f"⭐ Final Score: {final_score}/4

" f"━━━━━━━━━━━━━━━━━━ " f"🎯 EXECUTION " f"━━━━━━━━━━━━━━━━━━

" f"💰 Entry: {levels['entry']} " f"🛑 Stop Loss: {levels['stop_loss']} " f"🎯 Take Profit: {levels['take_profit']} " f"⚖ RR: 1:{levels['rr']} " )

print(
            f"✅ SIGNAL: {symbol} {signal}"
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
    f"

DONE: {signals_found} signals sent. " )

=====================================

ENTRY

=====================================

if name == "main": scan_all()
