# =====================================
# ULTIMATE SMC/ICT ELITE SCANNER
# Combined: Our System + GitHub + Playbook
# =====================================

import os
import json
import requests
import ccxt
import pandas as pd
import xml.etree.ElementTree as ET

from dotenv import load_dotenv
from datetime import datetime, timedelta

# =====================================
# LOAD ENV
# =====================================

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID   = os.getenv("CHAT_ID")

# =====================================
# EXCHANGE — BITGET
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

MIN_RR                = 2.0
MIN_SL_PCT            = 0.005
SIGNAL_COOLDOWN_HOURS = 12
COOLDOWN_FILE         = "last_signal_times.json"

# SMC Score thresholds (out of 100)
GRADE_S = 90   # Best — always send
GRADE_A = 80   # Good — send
GRADE_B = 70   # Okay — skip (not reliable enough)

# =====================================
# NEWS SOURCES (free RSS)
# =====================================

RSS_FEEDS = [
    "https://cointelegraph.com/rss",
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
]

POSITIVE_WORDS = [
    "surge", "rally", "bullish", "soars", "jumps",
    "gains", "breakout", "all-time high", "adoption",
    "upgrade", "partnership", "growth", "record"
]

NEGATIVE_WORDS = [
    "crash", "dump", "bearish", "plunge", "hack",
    "ban", "lawsuit", "collapse", "exploit", "scam",
    "fraud", "warning", "fine", "sec charges"
]

EXACT_MATCH_COINS = {
    "op", "sei", "fet", "bnb", "wld", "arb",
    "inj", "tia", "ren", "sol", "grt", "crv",
    "uni", "fil", "icp", "kas"
}

# =====================================
# EXPANDED COIN LIST (48 coins)
# =====================================

ALL_SYMBOLS = [

    # MAJORS
    "BTC/USDT:USDT",
    "ETH/USDT:USDT",
    "BNB/USDT:USDT",
    "SOL/USDT:USDT",
    "XRP/USDT:USDT",
    "DOGE/USDT:USDT",
    "AVAX/USDT:USDT",
    "LINK/USDT:USDT",
    "TRX/USDT:USDT",
    "DOT/USDT:USDT",
    "ATOM/USDT:USDT",
    "LTC/USDT:USDT",

    # AI / TRENDING
    "FET/USDT:USDT",
    "TAO/USDT:USDT",
    "RENDER/USDT:USDT",
    "WLD/USDT:USDT",
    "ARKM/USDT:USDT",
    "INJ/USDT:USDT",
    "GRT/USDT:USDT",

    # DEFI
    "AAVE/USDT:USDT",
    "CRV/USDT:USDT",
    "LDO/USDT:USDT",
    "RUNE/USDT:USDT",
    "UNI/USDT:USDT",

    # LAYER 1 / LAYER 2
    "ARB/USDT:USDT",
    "OP/USDT:USDT",
    "APT/USDT:USDT",
    "SEI/USDT:USDT",
    "SUI/USDT:USDT",
    "NEAR/USDT:USDT",
    "ICP/USDT:USDT",
    "FIL/USDT:USDT",
    "TIA/USDT:USDT",
    "IMX/USDT:USDT",

    # MEMES / HIGH VOL
    "PEPE/USDT:USDT",
    "WIF/USDT:USDT",
    "FLOKI/USDT:USDT",
    "SHIB/USDT:USDT",
    "BONK/USDT:USDT",

    # TRENDING
    "ONDO/USDT:USDT",
    "ENA/USDT:USDT",
    "PYTH/USDT:USDT",
    "JUP/USDT:USDT",
    "KAS/USDT:USDT",
    "ALGO/USDT:USDT",
    "JASMY/USDT:USDT",
    "CFX/USDT:USDT",

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
    raw = {k: v.isoformat() for k, v in signal_times.items()}
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(raw, f, indent=2)


def is_on_cooldown(symbol, signal_times, now):
    last = signal_times.get(symbol)
    if not last:
        return False
    return (now - last) < timedelta(hours=SIGNAL_COOLDOWN_HOURS)

# =====================================
# TELEGRAM
# =====================================

def send_telegram_alert(message):
    if not BOT_TOKEN:
        print("No BOT_TOKEN")
        return
    url     = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Telegram error: {e}")

# =====================================
# LOAD OHLCV
# =====================================

def load_ohlcv(symbol, timeframe, limit=200):
    ohlcv = exchange.fetch_ohlcv(
        symbol, timeframe=timeframe, limit=limit
    )
    df = pd.DataFrame(
        ohlcv,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df

# =====================================
# INDICATORS (pure pandas — no ta lib)
# =====================================

def apply_indicators(df):

    # EMA
    df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
    df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()

    # RSI
    delta    = df["close"].diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs       = avg_gain / avg_loss
    df["rsi"] = 100 - (100 / (1 + rs))

    # MACD
    ema_12            = df["close"].ewm(span=12, adjust=False).mean()
    ema_26            = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"]        = ema_12 - ema_26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    # ATR (correct ewm formula)
    hl        = df["high"] - df["low"]
    hc        = (df["high"] - df["close"].shift()).abs()
    lc        = (df["low"] - df["close"].shift()).abs()
    tr        = pd.concat([hl, hc, lc], axis=1).max(axis=1)
    df["atr"] = tr.ewm(com=13, adjust=False).mean()

    # ADX (pure pandas)
    up_move   = df["high"].diff()
    down_move = -df["low"].diff()
    plus_dm   = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm  = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    atr_adx   = tr.ewm(com=13, adjust=False).mean()
    plus_di   = 100 * plus_dm.ewm(com=13, adjust=False).mean() / atr_adx
    minus_di  = 100 * minus_dm.ewm(com=13, adjust=False).mean() / atr_adx
    dx        = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df["adx"] = dx.ewm(com=13, adjust=False).mean()
    df["plus_di"]  = plus_di
    df["minus_di"] = minus_di

    # Volume
    df["vol_ma"]  = df["volume"].rolling(20).mean()
    df["rel_vol"] = df["volume"] / df["vol_ma"]

    # ROC
    df["roc"] = df["close"].pct_change(periods=5) * 100

    return df

# =====================================
# TREND DETECTOR
# Closed candle + min 0.2% EMA gap
# =====================================

def detect_trend(df):
    ema20 = df["ema_20"].iloc[-2]
    ema50 = df["ema_50"].iloc[-2]
    price = df["close"].iloc[-2]

    if price == 0:
        return None

    gap_pct = abs(ema20 - ema50) / price
    if gap_pct < 0.002:
        return None

    if ema20 > ema50 and price > ema20:
        return "bullish"
    if ema20 < ema50 and price < ema20:
        return "bearish"

    return None

# =====================================
# SWING POINTS DETECTOR
# Used by CHOCH and BOS
# =====================================

def get_swing_highs(df, n=5):
    """Returns list of swing high prices (last 20 candles)"""
    highs = []
    data  = df.iloc[-25:-1]  # closed candles only
    for i in range(n, len(data) - n):
        window = data["high"].iloc[i-n:i+n+1]
        if data["high"].iloc[i] == window.max():
            highs.append(data["high"].iloc[i])
    return highs


def get_swing_lows(df, n=5):
    """Returns list of swing low prices (last 20 candles)"""
    lows = []
    data = df.iloc[-25:-1]  # closed candles only
    for i in range(n, len(data) - n):
        window = data["low"].iloc[i-n:i+n+1]
        if data["low"].iloc[i] == window.min():
            lows.append(data["low"].iloc[i])
    return lows

# =====================================
# SMC FILTER 1 — LIQUIDITY SWEEP
# Playbook definition (fixed):
# Bull: price took previous low
#       then closed BACK ABOVE it
# Bear: price took previous high
#       then closed BACK BELOW it
# =====================================

def detect_liquidity_sweep(df, direction):
    try:
        # Use last 3 closed candles
        c1 = df.iloc[-4]  # older
        c2 = df.iloc[-3]  # middle
        c3 = df.iloc[-2]  # last closed

        if direction == "bullish":
            # Previous low from c1
            prev_low = c1["low"]
            # c2 swept below prev_low
            swept = c2["low"] < prev_low
            # c3 closed back above prev_low
            recovered = c3["close"] > prev_low
            if swept and recovered:
                return True, f"Liq Sweep: Took low {round(prev_low, 4)} ✅"
            return False, "Liq Sweep: No bull sweep ❌"

        else:  # bearish
            # Previous high from c1
            prev_high = c1["high"]
            # c2 swept above prev_high
            swept = c2["high"] > prev_high
            # c3 closed back below prev_high
            recovered = c3["close"] < prev_high
            if swept and recovered:
                return True, f"Liq Sweep: Took high {round(prev_high, 4)} ✅"
            return False, "Liq Sweep: No bear sweep ❌"

    except:
        return False, "Liq Sweep: Error ❌"

# =====================================
# SMC FILTER 2 — CHOCH
# Change of Character (early reversal)
# Bull: after downtrend, breaks above LH
# Bear: after uptrend, breaks below HL
# =====================================

def detect_choch(df, direction):
    try:
        price = df["close"].iloc[-2]

        if direction == "bullish":
            # Look for recent lower highs
            swing_highs = get_swing_highs(df)
            if len(swing_highs) >= 2:
                # Check if price broke above the last lower high
                last_lh = swing_highs[-1]
                prev_lh = swing_highs[-2]
                # Lower high pattern = last_lh < prev_lh
                if last_lh < prev_lh and price > last_lh:
                    return True, f"CHOCH: Broke LH {round(last_lh, 4)} ✅"
            return False, "CHOCH: No bullish CHoCH ❌"

        else:  # bearish
            # Look for recent higher lows
            swing_lows = get_swing_lows(df)
            if len(swing_lows) >= 2:
                # Check if price broke below the last higher low
                last_hl = swing_lows[-1]
                prev_hl = swing_lows[-2]
                # Higher low pattern = last_hl > prev_hl
                if last_hl > prev_hl and price < last_hl:
                    return True, f"CHOCH: Broke HL {round(last_hl, 4)} ✅"
            return False, "CHOCH: No bearish CHoCH ❌"

    except:
        return False, "CHOCH: Error ❌"

# =====================================
# SMC FILTER 3 — BOS
# Break of Structure (trend confirmation)
# Bull: breaks previous swing high
# Bear: breaks previous swing low
# =====================================

def detect_bos(df, direction):
    try:
        price = df["close"].iloc[-2]

        if direction == "bullish":
            swing_highs = get_swing_highs(df)
            if swing_highs:
                last_high = swing_highs[-1]
                if price > last_high:
                    return True, f"BOS: Broke high {round(last_high, 4)} ✅"
            return False, "BOS: No bullish BOS ❌"

        else:  # bearish
            swing_lows = get_swing_lows(df)
            if swing_lows:
                last_low = swing_lows[-1]
                if price < last_low:
                    return True, f"BOS: Broke low {round(last_low, 4)} ✅"
            return False, "BOS: No bearish BOS ❌"

    except:
        return False, "BOS: Error ❌"

# =====================================
# BTC MARKET STATE
# =====================================

def get_btc_market_state():
    try:
        df    = load_ohlcv("BTC/USDT:USDT", "1h", limit=100)
        df    = apply_indicators(df)
        price = df["close"].iloc[-2]
        atr   = df["atr"].iloc[-2]
        trend = detect_trend(df)
        adx   = df["adx"].iloc[-2]

        vol_pct = atr / price

        if vol_pct > 0.03:
            volatility = "HIGH"
        elif vol_pct > 0.015:
            volatility = "NORMAL"
        else:
            volatility = "LOW"

        if trend == "bullish":
            btc_trend = "BULL"
        elif trend == "bearish":
            btc_trend = "BEAR"
        else:
            btc_trend = "RANGE"

        return {
            "trend":      btc_trend,
            "volatility": volatility,
            "price":      round(price, 2),
            "adx":        round(adx, 1)
        }
    except:
        return {
            "trend":      "UNKNOWN",
            "volatility": "UNKNOWN",
            "price":      0,
            "adx":        0
        }

# =====================================
# NEWS HEADLINES (free RSS)
# =====================================

def fetch_rss_headlines():
    headlines = []
    for url in RSS_FEEDS:
        try:
            resp = requests.get(url, timeout=5)
            root = ET.fromstring(resp.content)
            for item in root.iter("item"):
                title = item.findtext("title") or ""
                headlines.append(title.lower())
        except:
            continue
    return headlines

# =====================================
# HARD FILTERS — all must pass or SKIP
# =====================================

def check_4h_trend(symbol):
    df = load_ohlcv(symbol, "4h", limit=100)
    df = apply_indicators(df)
    return df, detect_trend(df)


def check_1h_trend(symbol, direction_4h):
    df        = load_ohlcv(symbol, "1h", limit=100)
    df        = apply_indicators(df)
    direction = detect_trend(df)

    if direction is None:
        return df, False, "1H: Unclear"
    if direction != direction_4h:
        return df, False, "1H: Counter to 4H"

    label = "BULLISH" if direction == "bullish" else "BEARISH"
    return df, True, f"1H Trend: {label}"


def check_15m_ema(df_15m, direction):
    ema20   = df_15m["ema_20"].iloc[-2]
    ema50   = df_15m["ema_50"].iloc[-2]
    price   = df_15m["close"].iloc[-2]
    gap_pct = abs(ema20 - ema50) / price if price else 0

    if gap_pct < 0.001:
        return False, "15M EMA: Gap too small"
    if direction == "bullish" and ema20 > ema50:
        return True, "15M EMA: Aligned BULLISH"
    if direction == "bearish" and ema20 < ema50:
        return True, "15M EMA: Aligned BEARISH"
    return False, "15M EMA: Not aligned"


def check_volume(df_15m):
    rel_vol = round(df_15m["rel_vol"].iloc[-2], 2)
    if rel_vol >= 1.2:  # Stricter per playbook
        return True, f"RVOL: {rel_vol}x ✅"
    return False, f"RVOL: {rel_vol}x (need 1.2x) ❌"


def check_adx(df_15m):
    adx = round(df_15m["adx"].iloc[-2], 1)
    if adx >= 20:
        strength = "strong" if adx >= 30 else "moderate"
        return True, f"ADX: {adx} ({strength}) ✅"
    return False, f"ADX: {adx} (weak trend) ❌"


def check_atr_percent(df_15m):
    atr   = df_15m["atr"].iloc[-2]
    price = df_15m["close"].iloc[-2]
    atr_pct = (atr / price) * 100 if price else 0
    if atr_pct >= 0.5:
        return True, f"ATR%: {round(atr_pct, 2)}% ✅"
    return False, f"ATR%: {round(atr_pct, 2)}% (dead market) ❌"


def check_overextension(df_15m):
    price    = df_15m["close"].iloc[-2]
    ema20    = df_15m["ema_20"].iloc[-2]
    distance = abs(price - ema20) / ema20 if ema20 else 1
    if distance > 0.05:
        return False, f"Overextended ({round(distance*100, 2)}%)"
    return True, f"Extension: OK ({round(distance*100, 2)}%) ✅"


def check_breakout_quality(df_15m, direction):
    candle     = df_15m.iloc[-2]
    body       = abs(candle["close"] - candle["open"])
    range_size = candle["high"] - candle["low"]

    if range_size == 0:
        return False, "Breakout: Doji"

    body_pct = (body / range_size) * 100
    if body_pct < 65:
        return False, f"Breakout: Weak ({round(body_pct)}% body)"

    if direction == "bullish":
        upper_wick = candle["high"] - candle["close"]
        if upper_wick > body:
            return False, "Breakout: Heavy upper wick"
    else:
        lower_wick = candle["close"] - candle["low"]
        if lower_wick > body:
            return False, "Breakout: Heavy lower wick"

    return True, f"Breakout: Clean ({round(body_pct)}% body) ✅"


def check_momentum(df_15m, direction):
    closes = df_15m["close"].tail(5).tolist()
    c1, c2, c3 = closes[1], closes[2], closes[3]

    if direction == "bullish" and c3 > c2 > c1:
        return True, "Momentum: 3 bullish candles ✅"
    if direction == "bearish" and c3 < c2 < c1:
        return True, "Momentum: 3 bearish candles ✅"
    return False, "Momentum: Weak"


def check_relative_strength(symbol, btc_df, direction):
    try:
        alt_df     = load_ohlcv(symbol, "1h", limit=30)
        btc_change = (btc_df["close"].iloc[-2] - btc_df["close"].iloc[-15]) / btc_df["close"].iloc[-15]
        alt_change = (alt_df["close"].iloc[-2] - alt_df["close"].iloc[-15]) / alt_df["close"].iloc[-15]
        rs         = round((alt_change - btc_change) * 100, 2)

        if direction == "bullish" and alt_change > btc_change:
            return True, f"RS: Strong vs BTC (+{rs}%) ✅"
        if direction == "bearish" and alt_change < btc_change:
            return True, f"RS: Weak vs BTC ({rs}%) ✅"
        return False, f"RS: Not favorable ({rs}%) ❌"
    except:
        return False, "RS: Error ❌"

# =====================================
# SMC SCORE SYSTEM (out of 100)
# Based on BigDaddy Daks playbook
# =====================================

def calculate_smc_score(
    direction, btc_state,
    df_15m, df_1h,
    liq_sweep, choch, bos,
    all_headlines, symbol
):
    score = 0
    breakdown = {}

    # 1. TREND ALIGNMENT (20 pts)
    # 4H + 1H both aligned = full points
    trend_score = 20
    score += trend_score
    breakdown["Trend Alignment"] = (trend_score, 20)

    # 2. BTC ALIGNMENT (15 pts)
    btc_trend = btc_state["trend"]
    if direction == "bullish" and btc_trend == "BULL":
        s = 15
    elif direction == "bearish" and btc_trend == "BEAR":
        s = 15
    elif btc_trend == "RANGE":
        s = 8
    else:
        s = 0
    score += s
    breakdown["BTC Alignment"] = (s, 15)

    # 3. LIQUIDITY SWEEP (15 pts)
    s = 15 if liq_sweep else 0
    score += s
    breakdown["Liquidity Sweep"] = (s, 15)

    # 4. MACD (10 pts)
    macd     = df_15m["macd"].iloc[-2]
    macd_sig = df_15m["macd_signal"].iloc[-2]
    if direction == "bullish" and macd > macd_sig:
        s = 10
    elif direction == "bearish" and macd < macd_sig:
        s = 10
    else:
        s = 0
    score += s
    breakdown["MACD"] = (s, 10)

    # 5. RVOL (10 pts)
    rel_vol = df_15m["rel_vol"].iloc[-2]
    if rel_vol >= 2.0:
        s = 10
    elif rel_vol >= 1.2:
        s = 7
    else:
        s = 0
    score += s
    breakdown["RVOL"] = (s, 10)

    # 6. ADX (10 pts)
    adx = df_15m["adx"].iloc[-2]
    if adx >= 30:
        s = 10
    elif adx >= 20:
        s = 6
    else:
        s = 0
    score += s
    breakdown["ADX"] = (s, 10)

    # 7. CHOCH (10 pts)
    s = 10 if choch else 0
    score += s
    breakdown["CHOCH"] = (s, 10)

    # 8. BOS (10 pts)
    s = 10 if bos else 0
    score += s
    breakdown["BOS"] = (s, 10)

    # BONUS — RSI penalty
    rsi = df_15m["rsi"].iloc[-2]
    if direction == "bullish" and rsi > 80:
        score -= 10
        breakdown["RSI Penalty"] = (-10, 0)
    if direction == "bearish" and rsi < 20:
        score -= 10
        breakdown["RSI Penalty"] = (-10, 0)

    # BONUS — Funding Rate
    try:
        funding      = exchange.fetch_funding_rate(symbol)
        funding_rate = funding.get("fundingRate", 0)
        if direction == "bullish" and funding_rate > 0.001:
            score -= 5
            breakdown["Funding Penalty"] = (-5, 0)
        if direction == "bearish" and funding_rate < -0.001:
            score -= 5
            breakdown["Funding Penalty"] = (-5, 0)
    except:
        pass

    # BONUS — News
    try:
        coin = symbol.split("/")[0].lower()
        if coin in EXACT_MATCH_COINS:
            relevant = [
                h for h in all_headlines
                if f" {coin} " in f" {h} "
            ]
        else:
            relevant = [h for h in all_headlines if coin in h]

        positive = sum(1 for h in relevant for w in POSITIVE_WORDS if w in h)
        negative = sum(1 for h in relevant for w in NEGATIVE_WORDS if w in h)

        if direction == "bullish" and negative > positive:
            score -= 5
        if direction == "bearish" and positive > negative:
            score -= 5
    except:
        pass

    # Cap at 100
    score = min(score, 100)
    score = max(score, 0)

    # Grade
    if score >= GRADE_S:
        grade = "S 🏆"
    elif score >= GRADE_A:
        grade = "A ⭐"
    elif score >= GRADE_B:
        grade = "B"
    else:
        grade = "C"

    return score, grade, breakdown

# =====================================
# RISK MANAGER
# TP1=1R, TP2=2R, TP3=3R
# SL below/above liquidity sweep
# =====================================

def calculate_trade_levels(price, atr_1h, direction, df_15m):
    sl_distance = max(atr_1h * 1.5, price * MIN_SL_PCT)

    if direction == "bullish":
        stop_loss = price - sl_distance
        tp1       = price + (sl_distance * 1)
        tp2       = price + (sl_distance * 2)
        tp3       = price + (sl_distance * 3)
    else:
        stop_loss = price + sl_distance
        tp1       = price - (sl_distance * 1)
        tp2       = price - (sl_distance * 2)
        tp3       = price - (sl_distance * 3)

    sl_pct = round((sl_distance / price) * 100, 2)

    if price < 0.0001:
        decimals = 10
    elif price < 0.01:
        decimals = 8
    elif price < 1:
        decimals = 6
    else:
        decimals = 4

    return {
        "entry":    round(price, decimals),
        "sl":       round(stop_loss, decimals),
        "tp1":      round(tp1, decimals),
        "tp2":      round(tp2, decimals),
        "tp3":      round(tp3, decimals),
        "sl_pct":   sl_pct,
    }

# =====================================
# MAIN SCAN
# =====================================

def scan_all():

    signal_times  = load_signal_times()
    signals_found = 0
    now           = datetime.utcnow()

    print(f"\n[{now}] ULTIMATE SMC SCAN STARTED\n")

    # BTC State (fetch once)
    btc_state = get_btc_market_state()
    print(f"  BTC: {btc_state['trend']} | "
          f"Vol: {btc_state['volatility']} | "
          f"ADX: {btc_state['adx']} | "
          f"${btc_state['price']}\n")

    # News (fetch once)
    print("  Fetching news...")
    all_headlines = fetch_rss_headlines()
    print(f"  {len(all_headlines)} headlines loaded.\n")

    # BTC 1H for RS
    try:
        btc_df = load_ohlcv("BTC/USDT:USDT", "1h", limit=30)
    except:
        btc_df = None

    print(f"  Scanning {len(ALL_SYMBOLS)} coins...\n")

    collected_signals = []

    for symbol in ALL_SYMBOLS:

        try:

            if is_on_cooldown(symbol, signal_times, now):
                last      = signal_times[symbol]
                remaining = last + timedelta(hours=SIGNAL_COOLDOWN_HOURS) - now
                hrs  = int(remaining.total_seconds() // 3600)
                mins = int((remaining.total_seconds() % 3600) // 60)
                print(f"  COOLDOWN {symbol}: {hrs}h {mins}m left")
                continue

            # ══════════════════════════════
            # HARD FILTERS
            # ══════════════════════════════

            # 1. 4H Trend
            df_4h, direction = check_4h_trend(symbol)
            if direction is None:
                print(f"  SKIP {symbol}: 4H unclear")
                continue

            # 2. 1H Trend must match 4H
            df_1h, ok_1h, l_1h = check_1h_trend(symbol, direction)
            if not ok_1h:
                print(f"  SKIP {symbol}: {l_1h}")
                continue

            atr_1h = df_1h["atr"].iloc[-2]

            # 3. Load 15M
            df_15m = load_ohlcv(symbol, "15m", limit=200)
            df_15m = apply_indicators(df_15m)

            price = df_15m["close"].iloc[-2]
            if price == 0:
                continue

            # 4. 15M EMA aligned
            ok_ema, l_ema = check_15m_ema(df_15m, direction)
            if not ok_ema:
                print(f"  SKIP {symbol}: {l_ema}")
                continue

            # 5. RVOL >= 1.2 (stricter per playbook)
            ok_vol, l_vol = check_volume(df_15m)
            if not ok_vol:
                print(f"  SKIP {symbol}: {l_vol}")
                continue

            # 6. ADX >= 20 (trend strength)
            ok_adx, l_adx = check_adx(df_15m)
            if not ok_adx:
                print(f"  SKIP {symbol}: {l_adx}")
                continue

            # 7. ATR% >= 0.5 (not dead market)
            ok_atr, l_atr = check_atr_percent(df_15m)
            if not ok_atr:
                print(f"  SKIP {symbol}: {l_atr}")
                continue

            # 8. Not overextended
            ok_ext, l_ext = check_overextension(df_15m)
            if not ok_ext:
                print(f"  SKIP {symbol}: {l_ext}")
                continue

            # 9. Breakout quality
            ok_break, l_break = check_breakout_quality(df_15m, direction)
            if not ok_break:
                print(f"  SKIP {symbol}: {l_break}")
                continue

            # 10. Momentum persistence
            ok_momo, l_momo = check_momentum(df_15m, direction)
            if not ok_momo:
                print(f"  SKIP {symbol}: {l_momo}")
                continue

            # 11. Relative Strength vs BTC
            if btc_df is not None:
                ok_rs, l_rs = check_relative_strength(symbol, btc_df, direction)
                if not ok_rs:
                    print(f"  SKIP {symbol}: {l_rs}")
                    continue
            else:
                l_rs = "RS: Skipped"

            # ══════════════════════════════
            # SMC FILTERS
            # ══════════════════════════════

            ok_liq, l_liq   = detect_liquidity_sweep(df_15m, direction)
            ok_choch, l_choch = detect_choch(df_15m, direction)
            ok_bos, l_bos   = detect_bos(df_15m, direction)

            # ══════════════════════════════
            # SMC SCORING (0-100)
            # ══════════════════════════════

            score, grade, breakdown = calculate_smc_score(
                direction, btc_state,
                df_15m, df_1h,
                ok_liq, ok_choch, ok_bos,
                all_headlines, symbol
            )

            print(f"  {symbol}: {direction.upper()} "
                  f"Score {score}/100 Grade {grade}")

            # Only send Grade S or A
            if score < GRADE_A:
                print(f"  SKIP {symbol}: Grade below A ({score}/100)")
                continue

            # ══════════════════════════════
            # SIGNAL CONFIRMED
            # ══════════════════════════════

            levels      = calculate_trade_levels(price, atr_1h, direction, df_15m)
            signal_type = "LONG 🟢" if direction == "bullish" else "SHORT 🔴"
            rsi_val     = round(df_15m["rsi"].iloc[-2], 1)
            adx_val     = round(df_15m["adx"].iloc[-2], 1)
            rvol_val    = round(df_15m["rel_vol"].iloc[-2], 2)

            collected_signals.append({
                "symbol":      symbol,
                "signal_type": signal_type,
                "direction":   direction,
                "score":       score,
                "grade":       grade,
                "levels":      levels,
                "l_1h":        l_1h,
                "l_ema":       l_ema,
                "l_vol":       l_vol,
                "l_adx":       l_adx,
                "l_atr":       l_atr,
                "l_ext":       l_ext,
                "l_break":     l_break,
                "l_momo":      l_momo,
                "l_rs":        l_rs,
                "l_liq":       l_liq,
                "l_choch":     l_choch,
                "l_bos":       l_bos,
                "rsi":         rsi_val,
                "adx":         adx_val,
                "rvol":        rvol_val,
                "now":         now,
            })

        except Exception as e:
            print(f"  ERROR {symbol}: {e}")

    # Sort by score — best first
    collected_signals.sort(key=lambda x: x["score"], reverse=True)

    # Send top 5 signals max
    for sig in collected_signals[:5]:

        symbol = sig["symbol"]
        levels = sig["levels"]
        grade  = sig["grade"]
        score  = sig["score"]

        message = (
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🏆 ULTIMATE SMC SIGNAL\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"🪙 {symbol}\n"
            f"📢 Signal: {sig['signal_type']}\n"
            f"🏦 Bitget Futures\n"
            f"⭐ Score: {score}/100 | Grade: {grade}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🌍 Market Context\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"BTC: {btc_state['trend']} | "
            f"{btc_state['volatility']}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📊 Timeframe Check\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ 4H Trend: "
            f"{'BULLISH' if sig['direction'] == 'bullish' else 'BEARISH'}\n"
            f"✅ {sig['l_1h']}\n"
            f"✅ {sig['l_ema']}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"📈 Quality Filters\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"✅ {sig['l_vol']}\n"
            f"✅ {sig['l_adx']}\n"
            f"✅ {sig['l_atr']}\n"
            f"✅ {sig['l_ext']}\n"
            f"✅ {sig['l_break']}\n"
            f"✅ {sig['l_momo']}\n"
            f"✅ {sig['l_rs']}\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🔮 SMC / ICT Analysis\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"{'✅' if '✅' in sig['l_liq'] else '❌'} "
            f"{sig['l_liq']}\n"
            f"{'✅' if '✅' in sig['l_choch'] else '❌'} "
            f"{sig['l_choch']}\n"
            f"{'✅' if '✅' in sig['l_bos'] else '❌'} "
            f"{sig['l_bos']}\n\n"
            f"RSI: {sig['rsi']} | "
            f"ADX: {sig['adx']} | "
            f"RVOL: {sig['rvol']}x\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"🎯 Trade Execution\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"💰 Entry:   {levels['entry']}\n"
            f"🛑 SL:      {levels['sl']} "
            f"(-{levels['sl_pct']}%)\n"
            f"🎯 TP1:     {levels['tp1']} (1R)\n"
            f"🎯 TP2:     {levels['tp2']} (2R)\n"
            f"🎯 TP3:     {levels['tp3']} (3R)\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚠ IMPORTANT\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Probability-based setup only.\n"
            f"No guaranteed outcome.\n"
            f"Risk only what you can afford."
        )

        print(f"\n  ✅ SENDING: {symbol} → "
              f"{sig['signal_type']} ({score}/100 {grade})")

        send_telegram_alert(message)
        signal_times[symbol] = sig["now"]
        signals_found += 1

    save_signal_times(signal_times)
    print(f"\n[DONE] {signals_found} signal(s) sent.\n")


# =====================================
# ENTRY POINT
# =====================================

if __name__ == "__main__":
    scan_all()
