# =====================================
# ELITE FUTURES SCANNER v2.1 BALANCED
# =====================================

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

exchange = ccxt.bitget({
    "enableRateLimit": True,
    "options": {
        "defaultType": "swap"
    }
})

# =====================================
# SETTINGS
# =====================================

MIN_SCORE = 3
MIN_RR = 2.0
MIN_SL_PCT = 0.005

SIGNAL_COOLDOWN_HOURS = 12
COOLDOWN_FILE = "last_signal_times.json"

# =====================================
# COINS
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
    "FET/USDT:USDT",
    "RENDER/USDT:USDT",
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
# COOLDOWN
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

    last = signal_times.get(symbol)

    if not last:
        return False

    return (
        now - last
    ) < timedelta(hours=SIGNAL_COOLDOWN_HOURS)

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

    df["timestamp"] = pd.to_datetime(
        df["timestamp"],
        unit="ms"
    )

    return df

# =====================================
# INDICATORS
# =====================================

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

# =====================================
# BTC MARKET ENGINE
# =====================================

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

# =====================================
# TREND DETECTOR
# =====================================

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

# =====================================
# RELATIVE STRENGTH
# =====================================

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

        if rs > 0.01:
            return 1, f"RS Strong ({round(rs*100,2)}%)"

        return 0, f"RS Weak ({round(rs*100,2)}%)"

    except:
        return 0, "RS Error"

# =====================================
# BREAKOUT QUALITY
# =====================================

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

    if body_ratio < 0.5:
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

# =====================================
# MOMENTUM PERSISTENCE
# =====================================

def momentum_persistence(df, direction):

    closes = df["close"].tail(4).tolist()

    if direction == "bullish":

        if closes[3] > closes[2] > closes[1]:
            return 1, "Momentum strong"

    if direction == "bearish":

        if closes[3] < closes[2] < closes[1]:
            return 1, "Momentum strong"

    return 0, "Momentum weak"

# =====================================
# OVEREXTENSION FILTER
# =====================================

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

# =====================================
# OPEN INTEREST
# OPTIONAL BONUS
# =====================================

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

# =====================================
# RISK MANAGER
# =====================================

def calculate_trade_levels(
    price,
    atr_1h,
    direction
):

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

    return {
        "entry": round(price, 4),
        "stop_loss": round(stop_loss, 4),
        "take_profit": round(take_profit, 4),
        "rr": MIN_RR
    }

# =====================================
# TELEGRAM
# =====================================

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

        print(
            "⚠ Defensive Mode "
            "High Volatility"
        )

        return

    signals_found = 0

    for symbol in ALL_SYMBOLS:

        try:

            # =====================================
            # COOLDOWN
            # =====================================

            if is_on_cooldown(
                symbol,
                signal_times,
                now
            ):

                print(
                    f"Cooldown: {symbol}"
                )

                continue

            # =====================================
            # 4H TREND
            # =====================================

            df_4h = load_ohlcv(
                symbol,
                "4h",
                limit=40
            )

            df_4h = apply_indicators(df_4h)

            direction = detect_trend(df_4h)

            if direction is None:

                print(
                    f"Skip {symbol}: "
                    f"No clear trend"
                )

                continue

            # =====================================
            # 1H DATA
            # =====================================

            df_1h = load_ohlcv(
                symbol,
                "1h",
                limit=40
            )

            df_1h = apply_indicators(df_1h)

            # =====================================
            # 15M DATA
            # =====================================

            df_15m = load_ohlcv(
                symbol,
                "15m",
                limit=40
            )

            df_15m = apply_indicators(df_15m)

            price = df_15m["close"].iloc[-2]

            atr_1h = df_1h["atr"].iloc[-2]

            # =====================================
            # VOLUME
            # =====================================

            rel_vol = (
                df_15m["rel_vol"].iloc[-2]
            )

            if rel_vol < 0.7:

                print(
                    f"Skip {symbol}: "
                    f"Weak volume"
                )

                continue

            # =====================================
            # RELATIVE STRENGTH
            # =====================================

            s_rs, l_rs = (
                relative_strength_score(symbol)
            )

            if s_rs == 0:

                print(
                    f"Skip {symbol}: "
                    f"{l_rs}"
                )

                continue

            # =====================================
            # BREAKOUT QUALITY
            # =====================================

            s_break, l_break = (
                breakout_quality(
                    df_15m,
                    direction
                )
            )

            if s_break == 0:

                print(
                    f"Skip {symbol}: "
                    f"{l_break}"
                )

                continue

            # =====================================
            # MOMENTUM
            # =====================================

            s_momo, l_momo = (
                momentum_persistence(
                    df_15m,
                    direction
                )
            )

            if s_momo == 0:

                print(
                    f"Skip {symbol}: "
                    f"{l_momo}"
                )

                continue

            # =====================================
            # OVEREXTENSION
            # =====================================

            safe_ext, ext_label = (
                overextension_filter(df_15m)
            )

            if not safe_ext:

                print(
                    f"Skip {symbol}: "
                    f"{ext_label}"
                )

                continue

            # =====================================
            # OPEN INTEREST BONUS
            # =====================================

            s_oi, l_oi = (
                open_interest_score(symbol)
            )

            # =====================================
            # SCORE
            # =====================================

            total_score = (
                s_rs +
                s_break +
                s_momo
            )

            bonus_score = s_oi

            final_score = (
                total_score +
                bonus_score
            )

            if total_score < MIN_SCORE:

                print(
                    f"Skip {symbol}: "
                    f"Low score"
                )

                continue

            # =====================================
            # TRADE LEVELS
            # =====================================

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

            # =====================================
            # TELEGRAM MESSAGE
            # =====================================

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

                f"✅ {l_rs}\n"
                f"✅ {l_break}\n"
                f"✅ {l_momo}\n"
                f"✅ {ext_label}\n"
                f"ℹ {l_oi}\n"

                f"✅ Relative Volume: "
                f"{round(rel_vol,2)}x\n\n"

                f"⭐ Final Score: "
                f"{final_score}/4\n\n"

                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 EXECUTION\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"

                f"💰 Entry: "
                f"{levels['entry']}\n"

                f"🛑 Stop Loss: "
                f"{levels['stop_loss']}\n"

                f"🎯 Take Profit: "
                f"{levels['take_profit']}\n"

                f"⚖ RR: "
                f"1:{levels['rr']}\n"
            )

            print(
                f"✅ SIGNAL: "
                f"{symbol} "
                f"{signal}"
            )

            print(message)

            send_telegram_alert(message)

            signal_times[symbol] = now

            signals_found += 1

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
