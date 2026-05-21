import os
import json
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

SIGNAL_COOLDOWN_HOURS = 12

COOLDOWN_FILE = "last_signal_times.json"

# ROC threshold — lowered from 0.5 to 0.2
ROC_THRESHOLD = 0.2

# =====================================
# ALL COINS
# FET → AGIX/USDT:USDT (OKX alternative)
# RNDR → RENDER/USDT:USDT (OKX alternative)
# =====================================

ALL_SYMBOLS = [

    # MAJORS
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "BNB/USDT:USDT",

    # MEME
    "DOGE/USDT:USDT",
    "PEPE/USDT:USDT",
    "SHIB/USDT:USDT",
    "WIF/USDT:USDT",
    "BONK/USDT:USDT",

    # AI
    "AGIX/USDT:USDT",       # FET not on OKX swap
    "RENDER/USDT:USDT",     # RNDR renamed to RENDER
    "TAO/USDT:USDT",
    "WLD/USDT:USDT",
    "ARKM/USDT:USDT",

    # TRENDING
    "ONDO/USDT:USDT",
    "SEI/USDT:USDT",
    "SUI/USDT:USDT",
    "INJ/USDT:USDT",
    "TIA/USDT:USDT",

    # MIDCAP
    "AVAX/USDT:USDT",
    "ARB/USDT:USDT",
    "OP/USDT:USDT",
    "LINK/USDT:USDT",
    "APT/USDT:USDT",

]

# =====================================
# COOLDOWN TRACKER
# =====================================

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
    last_time = signal_times.get(symbol)
    if not last_time:
        return False
    return (now - last_time) < timedelta(hours=SIGNAL_COOLDOWN_HOURS)

# =====================================
# LOAD DATA
# =====================================

def load_ohlcv(symbol, timeframe="15m", limit=60):

    ohlcv = exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=limit
    )

    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )

    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")

    return df

# =====================================
# INDICATORS (pure pandas)
# =====================================

def apply_indicators(df):

    # EMA
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # ATR
    hl = df["high"] - df["low"]
    hc = (df["high"] - df["close"].shift()).abs()
    lc = (df["low"] - df["close"].shift()).abs()
    tr = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=13, adjust=False).mean()

    # ROC
    df["roc"] = df["close"].pct_change(periods=5) * 100

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

    if atr_percent < 0.3:
        return "dead_market"
    if abs(ema20 - ema50) < price * 0.001:
        return "ranging"
    if atr_percent > 3:
        return "volatile"

    return "trending"

# =====================================
# ANALYSIS
# =====================================

def analyze_trend(df):
    ema20 = df["ema_20"].iloc[-1]
    ema50 = df["ema_50"].iloc[-1]
    direction = "bullish" if ema20 > ema50 else "bearish"
    return {"direction": direction}


def analyze_momentum(df):
    roc = df["roc"].iloc[-1]
    rsi = df["rsi"].iloc[-1]
    return {
        "roc": round(roc, 2),
        "rsi": round(rsi, 2),
        "strong": abs(roc) > ROC_THRESHOLD   # 0.2 instead of 0.5
    }


def analyze_volatility(df):
    atr = df["atr"].iloc[-1]
    price = df["close"].iloc[-1]
    volatility = (atr / price) * 100
    return {
        "volatility_percent": round(volatility, 2),
        "active": volatility >= 0.3           # lowered from 0.5 to 0.3
    }


def analyze_volume(df):
    current_volume = df["volume"].iloc[-1]
    average_volume = df["volume"].rolling(20).mean().iloc[-1]
    relative_volume = current_volume / average_volume
    return {
        "relative_volume": round(relative_volume, 2),
        "strong_volume": relative_volume >= 0.8   # lowered from 1.0 to 0.8
    }

# =====================================
# FILTER
# =====================================

def should_skip_trade(momentum, volatility, volume, regime):

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

def calculate_trade_levels(price, atr, direction):

    sl_distance = atr * 1.5

    if direction == "bullish":
        stop_loss = price - sl_distance
        take_profit = price + (sl_distance * MIN_RR)
    else:
        stop_loss = price + sl_distance
        take_profit = price - (sl_distance * MIN_RR)

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

    if not BOT_TOKEN:
        print("No BOT_TOKEN found, skipping Telegram.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# =====================================
# MAIN SCAN
# =====================================

def scan_all():

    signal_times = load_signal_times()
    signals_found = 0
    now = datetime.utcnow()

    print(f"\n[{now}] Scanning {len(ALL_SYMBOLS)} coins...\n")

    for symbol in ALL_SYMBOLS:

        try:

            if is_on_cooldown(symbol, signal_times, now):
                last = signal_times[symbol]
                remaining = last + timedelta(hours=SIGNAL_COOLDOWN_HOURS) - now
                hrs = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                print(f"  COOLDOWN {symbol}: {hrs}h {mins}m left")
                continue

            df = load_ohlcv(symbol, TIMEFRAME)

            if len(df) < 55:
                print(f"  SKIP {symbol}: not enough data")
                continue

            df = apply_indicators(df)

            regime = detect_market_regime(df)
            trend = analyze_trend(df)
            momentum = analyze_momentum(df)
            volatility = analyze_volatility(df)
            volume = analyze_volume(df)

            skip, reason = should_skip_trade(
                momentum, volatility, volume, regime
            )

            if skip:
                print(f"  SKIP {symbol}: {reason}")
                continue

            price = df["close"].iloc[-1]
            atr = df["atr"].iloc[-1]

            levels = calculate_trade_levels(price, atr, trend["direction"])

            signal_type = "LONG" if trend["direction"] == "bullish" else "SHORT"

            message = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏆 CLEAN MARKET SIGNAL\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🪙 Symbol: {symbol}\n"
                f"📢 Signal: {signal_type}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 Market Analysis\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"📈 Regime: {regime}\n"
                f"Momentum ROC: {momentum['roc']}%\n"
                f"RSI: {momentum['rsi']}\n"
                f"Volatility: {volatility['volatility_percent']}%\n"
                f"Relative Volume: {volume['relative_volume']}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 Trade Execution\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Entry: {levels['entry']}\n"
                f"🛑 Stop Loss: {levels['stop_loss']}\n"
                f"🎯 Take Profit: {levels['take_profit']}\n"
                f"⚖ Risk Reward: 1:{levels['rr']}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠ IMPORTANT\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"Probability-based setup only.\n"
                f"No guaranteed outcome."
            )

            print(f"  ✅ SIGNAL: {symbol} → {signal_type}")
            send_telegram_alert(message)

            signal_times[symbol] = now
            signals_found += 1

        except Exception as e:
            print(f"  ERROR {symbol}: {e}")

    save_signal_times(signal_times)

    print(f"\n[DONE] {signals_found} signal(s) sent.\n")


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    scan_all()
