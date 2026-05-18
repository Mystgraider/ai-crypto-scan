import requests
import statistics
import os
from datetime import datetime

# =====================================
# CONFIG
# =====================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

SYMBOL = "BTCUSDT"
INTERVAL = "15"

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
# GET MARKET DATA (BYBIT)
# =====================================

def get_price_data():

    url = (
        "https://api.bybit.com/v5/market/kline"
        f"?category=linear&symbol={SYMBOL}&interval={INTERVAL}&limit=100"
    )

    response = requests.get(url)

    data = response.json()

    candles = data["result"]["list"]

    closes = [
        float(x[4])
        for x in candles
    ]

    volumes = [
        float(x[5])
        for x in candles
    ]

    closes.reverse()
    volumes.reverse()

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

    momentum = ((latest - old) / old) * 100

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

    ratio = current_volume / avg_volume

    score = min(ratio * 50, 100)

    return round(score, 2)

# =====================================
# MOMENTUM ALIGNMENT
# =====================================

def momentum_alignment(momentum):

    score = min(abs(momentum) * 30, 100)

    return round(score, 2)

# =====================================
# RISK STABILITY
# =====================================

def risk_stability(volatility):

    score = max(100 - (volatility * 10), 1)

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
# RISK ENGINE
# =====================================

def risk_engine(volatility):

    if volatility >= 5:
        return "HIGH ⚠️"

    elif volatility >= 3:
        return "MODERATE"

    return "LOW ✅"

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
# EXECUTION QUALITY
# =====================================

def execution_quality(consensus):

    if consensus >= 85:
        return "ELITE ✅"

    elif consensus >= 70:
        return "STRONG ⚡"

    elif consensus >= 55:
        return "MODERATE ⚠️"

    return "LOW ❌"

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

    if consensus < 60:
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
        and consensus >= 70
    ):
        return "BUY 🚀"

    elif (
        "BEARISH" in regime
        and momentum < 0
        and consensus >= 70
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
        abs(tp2 - current_price) /
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

    closes, volumes = get_price_data()

    price = closes[-1]

    regime = market_regime(closes)

    volatility = volatility_score(closes)

    momentum = momentum_score(closes)

    trend_score = trend_alignment(closes)

    liquidity_score = liquidity_alignment(volumes)

    momentum_score_value = momentum_alignment(momentum)

    risk_score = risk_stability(volatility)

    consensus = consensus_engine(
        trend_score,
        liquidity_score,
        momentum_score_value,
        risk_score
    )

    risk = risk_engine(volatility)

    conflict = signal_conflict(
        trend_score,
        momentum_score_value,
        risk_score
    )

    quality = execution_quality(consensus)

    blocked = no_trade_filter(
        volatility,
        consensus,
        conflict
    )

    signal = signal_engine(
        regime,
        momentum,
        consensus
    )

    if blocked:
        signal = "NO TRADE ⚠️"

    zones = execution_zones(
        price,
        volatility,
        signal
    )

    avg_volume = round(
        statistics.mean(volumes[-20:]),
        2
    )

    current_volume = round(
        volumes[-1],
        2
    )

    market_stability = round(
        (
            risk_score +
            trend_score
        ) / 2,
        2
    )

    trade_status = (
        "APPROVED ✅"
        if "NO TRADE" not in signal
        else "DENIED ❌"
    )

    volume_state = (
        "STRONG BUY PRESSURE 🐋"
        if current_volume > avg_volume
        else "WEAK PARTICIPATION ⚠️"
    )

    trade_section = ""

    if zones:

        trade_section = f"""
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

Trade Status:
{trade_status}
"""

    report = f"""
━━━━━━━━━━━━━━━━━━
🤖 V27 OMEGA STABLE CORE
━━━━━━━━━━━━━━━━━━

🪙 Symbol:
{SYMBOL}

💰 Current Price:
{price}

📢 Signal:
{signal}

{trade_section}

━━━━━━━━━━━━━━━━━━
🌍 Market State
━━━━━━━━━━━━━━━━━━

Regime:
{regime}

Market Stability:
{market_stability}%

Volatility:
{volatility}%

Momentum:
{momentum}%

━━━━━━━━━━━━━━━━━━
🧠 Consensus Matrix
━━━━━━━━━━━━━━━━━━

Trend Alignment:
{trend_score}%

Liquidity Alignment:
{liquidity_score}%

Momentum Alignment:
{momentum_score_value}%

Risk Stability:
{risk_score}%

Consensus Score:
{consensus}%

━━━━━━━━━━━━━━━━━━
🛡 Risk Engine
━━━━━━━━━━━━━━━━━━

Risk Level:
{risk}

Signal Conflict:
{conflict}

━━━━━━━━━━━━━━━━━━
⚔️ Execution Engine
━━━━━━━━━━━━━━━━━━

Execution Quality:
{quality}

Trade Permission:
{trade_status}

━━━━━━━━━━━━━━━━━━
📈 Volume Intelligence
━━━━━━━━━━━━━━━━━━

Current Volume:
{current_volume}

Average Volume:
{avg_volume}

Volume State:
{volume_state}

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
