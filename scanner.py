import requests
import statistics
import os
from datetime import datetime

# =====================================
# CONFIG
# =====================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOLS = [

    "BTC",
    "ETH",
    "BNB",
    "SOL",
    "XRP",
    "ADA",
    "DOGE",
    "AVAX",
    "DOT",
    "LINK",
    "MATIC",
    "LTC",
    "ATOM",
    "UNI",
    "FIL",
    "APT",
    "ARB",
    "OP",
    "INJ",
    "NEAR",
    "FTM",
    "ALGO",
    "ICP",
    "SHIB",
    "PEPE",
    "WIF",
    "BONK",
    "TAO",
    "FET",
    "IMX",
    "GALA",
    "MKR",
    "AAVE",
    "SUI",
    "SEI",
    "TIA",
    "JUP",
    "PYTH",
    "TON",
    "ONDO"

]

# =====================================
# TELEGRAM
# =====================================

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    payload = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=payload)

# =====================================
# GET MARKET DATA
# =====================================

def get_price_data(symbol):

    headers = {
        "User-Agent": "Mozilla/5.0"
    }

    url = (
        "https://min-api.cryptocompare.com/data/v2/histominute"
        f"?fsym={symbol}"
        "&tsym=USDT"
        "&limit=100"
    )

    response = requests.get(
        url,
        headers=headers,
        timeout=15
    )

    data = response.json()

    # SAFE CHECK
    if "Data" not in data:
        raise Exception("No Data")

    if "Data" not in data["Data"]:
        raise Exception("Invalid Candle Data")

    candles = data["Data"]["Data"]

    if len(candles) < 50:
        raise Exception("Not Enough Candles")

    closes = [
        float(x["close"])
        for x in candles
    ]

    volumes = [
        float(x["volumeto"])
        for x in candles
    ]

    return closes, volumes

# =====================================
# MARKET REGIME
# =====================================

def market_regime(closes):

    sma20 = statistics.mean(closes[-20:])
    sma50 = statistics.mean(closes[-50:])

    if sma20 > sma50:
        return "TRENDING 🚀"

    elif sma20 < sma50:
        return "BEARISH 🩸"

    return "RANGING ⚖️"

# =====================================
# VOLATILITY
# =====================================

def volatility_score(closes):

    recent = closes[-20:]

    high = max(recent)
    low = min(recent)

    volatility = ((high - low) / low) * 100

    return round(volatility, 2)

# =====================================
# MOMENTUM
# =====================================

def momentum_score(closes):

    latest = closes[-1]
    old = closes[-10]

    momentum = (
        (latest - old) / old
    ) * 100

    return round(momentum, 2)

# =====================================
# TREND ALIGNMENT
# =====================================

def trend_alignment(closes):

    sma20 = statistics.mean(closes[-20:])
    sma50 = statistics.mean(closes[-50:])

    diff = abs(sma20 - sma50)

    score = min(diff * 2, 100)

    return round(score, 2)

# =====================================
# LIQUIDITY ALIGNMENT
# =====================================

def liquidity_alignment(volumes):

    avg_volume = statistics.mean(volumes[-20:])
    current_volume = volumes[-1]

    if avg_volume == 0:
        return 0

    ratio = current_volume / avg_volume

    score = min(ratio * 50, 100)

    return round(score, 2)

# =====================================
# MOMENTUM ALIGNMENT
# =====================================

def momentum_alignment(momentum):

    score = min(
        abs(momentum) * 30,
        100
    )

    return round(score, 2)

# =====================================
# RISK STABILITY
# =====================================

def risk_stability(volatility):

    score = max(
        100 - (volatility * 10),
        1
    )

    return round(score, 2)

# =====================================
# CONSENSUS ENGINE
# =====================================

def consensus_engine(
    trend,
    liquidity,
    momentum,
    risk
):

    score = (
        trend * 0.30 +
        liquidity * 0.20 +
        momentum * 0.20 +
        risk * 0.30
    )

    return round(score, 2)

# =====================================
# SIGNAL CONFLICT
# =====================================

def signal_conflict(
    trend,
    momentum,
    risk
):

    if risk < 40:
        return "HIGH"

    elif trend < 50 or momentum < 50:
        return "MODERATE"

    return "LOW"

# =====================================
# NO TRADE FILTER
# =====================================

def no_trade_filter(
    volatility,
    consensus,
    conflict
):

    if volatility > 6:
        return True

    if consensus < 50:
        return True

    if conflict == "HIGH":
        return True

    return False

# =====================================
# SIGNAL ENGINE
# =====================================

def signal_engine(
    regime,
    momentum,
    consensus
):

    if (
        "TRENDING" in regime
        and momentum > 0
        and consensus >= 55
    ):
        return "BUY 🚀"

    elif (
        "BEARISH" in regime
        and momentum < 0
        and consensus >= 55
    ):
        return "SELL 🩸"

    return "NO TRADE ⚠️"

# =====================================
# EXECUTION ZONES
# =====================================

def execution_zones(
    current_price,
    volatility,
    signal
):

    move = current_price * (
        volatility / 100
    )

    if "BUY" in signal:

        entry_low = round(
            current_price * 0.998,
            2
        )

        entry_high = round(
            current_price * 1.001,
            2
        )

        stop_loss = round(
            current_price - (move * 0.8),
            2
        )

        tp1 = round(
            current_price + (move * 1.5),
            2
        )

        tp2 = round(
            current_price + (move * 3),
            2
        )

    elif "SELL" in signal:

        entry_low = round(
            current_price * 0.999,
            2
        )

        entry_high = round(
            current_price * 1.002,
            2
        )

        stop_loss = round(
            current_price + (move * 0.8),
            2
        )

        tp1 = round(
            current_price - (move * 1.5),
            2
        )

        tp2 = round(
            current_price - (move * 3),
            2
        )

    else:
        return None

    rr = round(
        abs(tp2 - current_price)
        /
        abs(current_price - stop_loss),
        2
    )

    return {
        "entry_low": entry_low,
        "entry_high": entry_high,
        "sl": stop_loss,
        "tp1": tp1,
        "tp2": tp2,
        "rr": rr
    }

# =====================================
# MAIN ANALYSIS
# =====================================

def analyze():

    best_setup = None

    for symbol in SYMBOLS:

        try:

            closes, volumes = get_price_data(symbol)

            price = closes[-1]

            regime = market_regime(closes)

            volatility = volatility_score(closes)

            momentum = momentum_score(closes)

            trend_score = trend_alignment(closes)

            liquidity_score = liquidity_alignment(volumes)

            momentum_score_value = momentum_alignment(
                momentum
            )

            risk_score = risk_stability(
                volatility
            )

            consensus = consensus_engine(
                trend_score,
                liquidity_score,
                momentum_score_value,
                risk_score
            )

            conflict = signal_conflict(
                trend_score,
                momentum_score_value,
                risk_score
            )

            signal = signal_engine(
                regime,
                momentum,
                consensus
            )

            blocked = no_trade_filter(
                volatility,
                consensus,
                conflict
            )

            if blocked:
                continue

            if (
                best_setup is None
                or
                consensus > best_setup["consensus"]
            ):

                best_setup = {
                    "symbol": symbol,
                    "price": price,
                    "signal": signal,
                    "consensus": consensus,
                    "momentum": momentum,
                    "volatility": volatility,
                    "regime": regime
                }

        except Exception as e:

            print(f"ERROR {symbol}: {e}")

    # =====================================
    # NO SETUP
    # =====================================

    if not best_setup:

        report = """
━━━━━━━━━━━━━━━━━━
⚠️ MARKET STATUS
━━━━━━━━━━━━━━━━━━

No high-quality setup found.

Trade Permission:
DENIED ❌

Reason:
Weak market conditions
━━━━━━━━━━━━━━━━━━
"""

        print(report)

        send_telegram(report)

        return

    # =====================================
    # EXECUTION
    # =====================================

    zones = execution_zones(
        best_setup["price"],
        best_setup["volatility"],
        best_setup["signal"]
    )

    # SAFE CHECK
    if zones is None:

        report = f"""
━━━━━━━━━━━━━━━━━━
⚠️ MARKET STATUS
━━━━━━━━━━━━━━━━━━

No executable setup found.

Best Symbol:
{best_setup['symbol']}USDT

Signal:
{best_setup['signal']}

Consensus:
{best_setup['consensus']}%

━━━━━━━━━━━━━━━━━━
"""

        print(report)

        send_telegram(report)

        return

    # =====================================
    # FINAL REPORT
    # =====================================

    report = f"""
━━━━━━━━━━━━━━━━━━
🏆 TOP MARKET OPPORTUNITY
━━━━━━━━━━━━━━━━━━

🪙 Symbol:
{best_setup['symbol']}USDT

💰 Current Price:
{best_setup['price']}

📢 Signal:
{best_setup['signal']}

━━━━━━━━━━━━━━━━━━
🎯 Trade Execution
━━━━━━━━━━━━━━━━━━

Entry Zone:
{zones['entry_low']} - {zones['entry_high']}

Stop Loss:
{zones['sl']}

Take Profit 1:
{zones['tp1']}

Take Profit 2:
{zones['tp2']}

Risk : Reward
1 : {zones['rr']}

━━━━━━━━━━━━━━━━━━
📊 Market Analysis
━━━━━━━━━━━━━━━━━━

Regime:
{best_setup['regime']}

Consensus Score:
{best_setup['consensus']}%

Momentum:
{best_setup['momentum']}%

Volatility:
{best_setup['volatility']}%

━━━━━━━━━━━━━━━━━━
🕒 Time
━━━━━━━━━━━━━━━━━━

{datetime.utcnow()} UTC
━━━━━━━━━━━━━━━━━━
"""

    print(report)

    send_telegram(report)

# =====================================
# START
# =====================================

if __name__ == "__main__":
    analyze()
