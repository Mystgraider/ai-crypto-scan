import ccxt
import pandas as pd
import ta
import requests
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

exchange = ccxt.okx()

markets = exchange.load_markets()

coins = []

for symbol in markets:

    if '/USDT' in symbol:
        coins.append(symbol)

coins = coins[:30]

heat_ranking = []


def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)


def social_sentiment(symbol, bullish_score):

    if bullish_score >= 7:
        return "VERY POSITIVE 🟢"

    elif bullish_score >= 5:
        return "POSITIVE 🟢"

    elif bullish_score >= 3:
        return "NEUTRAL ⚖️"

    return "NEGATIVE 🔴"


def smart_money_logic(breakout, whale):

    if breakout == "ACTIVE 🚨" and "ACCUMULATION" in whale:
        return "TREND CONTINUATION"

    elif breakout == "NONE":
        return "RANGING MARKET"

    return "VOLATILE CONDITIONS"


def volatility_engine(df):

    volatility = (
        (df['high'] - df['low']) / df['close']
    ).tail(20).mean()

    if volatility > 0.03:
        return "EXPANDING ⚡", 2

    elif volatility > 0.015:
        return "NORMAL", 1

    return "LOW VOLATILITY", 0


def market_regime(bullish_score):

    if bullish_score >= 7:
        return "BULL MARKET 🚀"

    elif bullish_score <= 2:
        return "BEAR MARKET 📉"

    return "RANGING MARKET ⚖️"


def breakout_probability(
    bullish,
    breakout,
    whale
):

    score = bullish * 10

    if breakout == "ACTIVE 🚨":
        score += 20

    if "ACCUMULATION" in whale:
        score += 15

    return min(score, 99)


def fear_greed_engine(bullish):

    if bullish >= 7:
        return "GREED 🟢"

    elif bullish <= 2:
        return "FEAR 🔴"

    return "NEUTRAL ⚖️"


def news_bias_engine(bullish, breakout):

    if bullish >= 6 and breakout == "ACTIVE 🚨":
        return "BULLISH"

    elif bullish <= 2:
        return "BEARISH"

    return "MIXED"


def liquidation_engine(
    volatility_status,
    breakout
):

    if (
        volatility_status == "EXPANDING ⚡"
        and breakout == "ACTIVE 🚨"
    ):
        return "SHORT SQUEEZE ⚡"

    return "NORMAL"


def momentum_strength(
    bullish,
    breakout_chance
):

    if bullish >= 7 and breakout_chance >= 90:
        return "EXPLOSIVE ⚡"

    elif bullish >= 5:
        return "STRONG 🚀"

    return "WEAK ⚖️"


def fusion_score(
    bullish,
    breakout_chance,
    confidence
):

    score = (
        bullish * 5
        + breakout_chance * 0.4
        + confidence * 0.3
    )

    return min(round(score), 100)


def trade_grade(score):

    if score >= 95:
        return "A+ ⭐"

    elif score >= 85:
        return "A 🚀"

    elif score >= 70:
        return "B 👍"

    elif score >= 55:
        return "C ⚖️"

    return "D ❌"


def market_phase(
    breakout_chance,
    volatility_status
):

    if (
        breakout_chance >= 90
        and volatility_status == "EXPANDING ⚡"
    ):
        return "EXPANSION 🌊"

    elif volatility_status == "LOW VOLATILITY":
        return "COMPRESSION ⚖️"

    return "TRANSITION"


def fake_breakout_risk(
    breakout_chance,
    volume,
    avg_volume
):

    if (
        breakout_chance >= 85
        and volume < avg_volume
    ):
        return "HIGH ⚠️"

    elif breakout_chance >= 90:
        return "LOW ✅"

    return "MEDIUM ⚖️"


def momentum_persistence(
    bullish,
    confidence
):

    if bullish >= 7 and confidence >= 90:
        return "PERSISTENT ⚡"

    elif bullish >= 5:
        return "STABLE 🚀"

    return "WEAK"


def smart_money_v2(
    bullish,
    breakout_chance
):

    if bullish >= 7 and breakout_chance >= 90:
        return "AGGRESSIVE ACCUMULATION 🐋"

    elif bullish <= 2:
        return "DISTRIBUTION 📉"

    return "NEUTRAL ⚖️"


def market_state_engine(
    breakout_chance,
    volatility_status,
    bullish
):

    if (
        breakout_chance >= 95
        and bullish >= 7
    ):
        return "EXPANSION ⚡"

    elif volatility_status == "LOW VOLATILITY":
        return "COMPRESSION ⚖️"

    elif bullish <= 2:
        return "EXHAUSTION 📉"

    return "TRANSITION 🌊"


def fusion_matrix(
    bullish,
    breakout_chance,
    confidence
):

    trend_strength = min(
        bullish * 12,
        100
    )

    momentum_quality = min(
        confidence,
        100
    )

    volatility_quality = min(
        breakout_chance,
        100
    )

    smart_money_pressure = min(
        bullish * 13,
        100
    )

    return {
        "trend": trend_strength,
        "momentum": momentum_quality,
        "volatility": volatility_quality,
        "smart_money": smart_money_pressure
    }


def elite_trade_grade(
    fusion,
    breakout_chance
):

    avg_score = (
        fusion['trend']
        + fusion['momentum']
        + fusion['volatility']
        + fusion['smart_money']
    ) / 4

    if avg_score >= 95 and breakout_chance >= 95:
        return "A+ ELITE SETUP ⭐"

    elif avg_score >= 85:
        return "A STRONG SETUP 🚀"

    elif avg_score >= 70:
        return "B GOOD SETUP 👍"

    return "C WEAK SETUP ⚖️"


def timeframe_analysis(symbol, timeframe):

    ohlcv = exchange.fetch_ohlcv(
        symbol,
        timeframe=timeframe,
        limit=150
    )

    df = pd.DataFrame(
        ohlcv,
        columns=[
            'time',
            'open',
            'high',
            'low',
            'close',
            'volume'
        ]
    )

    df['rsi'] = ta.momentum.RSIIndicator(
        df['close']
    ).rsi()

    df['ema20'] = ta.trend.EMAIndicator(
        df['close'],
        window=20
    ).ema_indicator()

    df['ema50'] = ta.trend.EMAIndicator(
        df['close'],
        window=50
    ).ema_indicator()

    macd = ta.trend.MACD(df['close'])

    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()

    latest = df.iloc[-1]

    bullish = 0

    if latest['ema20'] > latest['ema50']:
        bullish += 1

    if latest['rsi'] > 50:
        bullish += 1

    if latest['macd'] > latest['signal']:
        bullish += 1

    if bullish >= 2:
        return "Bullish 🚀"

    return "Bearish 📉"


def analyze(symbol):

    try:

        ohlcv = exchange.fetch_ohlcv(
            symbol,
            timeframe='1h',
            limit=200
        )

        df = pd.DataFrame(
            ohlcv,
            columns=[
                'time',
                'open',
                'high',
                'low',
                'close',
                'volume'
            ]
        )

        df['ema20'] = ta.trend.EMAIndicator(
            df['close'],
            window=20
        ).ema_indicator()

        df['ema50'] = ta.trend.EMAIndicator(
            df['close'],
            window=50
        ).ema_indicator()

        df['rsi'] = ta.momentum.RSIIndicator(
            df['close']
        ).rsi()

        macd = ta.trend.MACD(df['close'])

        df['macd'] = macd.macd()
        df['signal'] = macd.macd_signal()

        latest = df.iloc[-1]

        price = latest['close']

        trend = "SIDEWAYS ⚖️"

        bullish = 0

        if latest['ema20'] > latest['ema50']:
            trend = "BULLISH 🚀"
            bullish += 1

        if latest['rsi'] > 50:
            bullish += 1

        if latest['macd'] > latest['signal']:
            bullish += 1

        volume = latest['volume']
        avg_volume = df['volume'].tail(20).mean()

        whale = "NORMAL"

        if volume > avg_volume * 2:
            whale = "ACCUMULATION 🐋"
            bullish += 1

        recent_high = df['high'].tail(20).max()

        breakout = "NONE"

        if price >= recent_high * 0.995:
            breakout = "ACTIVE 🚨"
            bullish += 1

        tf15 = timeframe_analysis(symbol, '15m')
        tf1h = timeframe_analysis(symbol, '1h')
        tf4h = timeframe_analysis(symbol, '4h')

        tf_bullish = 0

        for tf in [tf15, tf1h, tf4h]:
            if "Bullish" in tf:
                tf_bullish += 1

        bullish += tf_bullish

        volatility_status, vol_score = volatility_engine(df)

        bullish += vol_score

        if bullish >= 7:
            confidence = 95
            signal = "STRONG BUY 🚀"

        elif bullish >= 5:
            confidence = 85
            signal = "BUY 🚀"

        elif bullish >= 3:
            confidence = 60
            signal = "HOLD ⚖️"

        else:
            confidence = 40
            signal = "SELL 📉"

        social = social_sentiment(symbol, bullish)

        regime = market_regime(bullish)

        breakout_chance = breakout_probability(
            bullish,
            breakout,
            whale
        )

        fear_greed = fear_greed_engine(bullish)

        news_bias = news_bias_engine(
            bullish,
            breakout
        )

        liquidation_risk = liquidation_engine(
            volatility_status,
            breakout
        )

        momentum = momentum_strength(
            bullish,
            breakout_chance
        )

        fusion = fusion_score(
            bullish,
            breakout_chance,
            confidence
        )

        grade = trade_grade(fusion)

        phase = market_phase(
            breakout_chance,
            volatility_status
        )

        fake_risk = fake_breakout_risk(
            breakout_chance,
            volume,
            avg_volume
        )

        persistence = momentum_persistence(
            bullish,
            confidence
        )

        smart_money = smart_money_v2(
            bullish,
            breakout_chance
        )

        state = market_state_engine(
            breakout_chance,
            volatility_status,
            bullish
        )

        fusion_data = fusion_matrix(
            bullish,
            breakout_chance,
            confidence
        )

        elite_grade = elite_trade_grade(
            fusion_data,
            breakout_chance
        )

        if volatility_status == "EXPANDING ⚡":

            tp1 = round(price * 1.04, 2)
            tp2 = round(price * 1.08, 2)
            tp3 = round(price * 1.12, 2)
            sl = round(price * 0.975, 2)

        else:

            tp1 = round(price * 1.03, 2)
            tp2 = round(price * 1.06, 2)
            tp3 = round(price * 1.12, 2)
            sl = round(price * 0.98, 2)

        heat_score = bullish + breakout_chance

        heat_ranking.append(
            (symbol, heat_score)
        )

        message = f'''
━━━━━━━━━━━━━━━━━━
🤖 QUANT AI COMMAND CENTER
━━━━━━━━━━━━━━━━━━

🪙 {symbol}

💰 Price:
{round(price,2)}

🌍 Market Regime:
{regime}

🌊 Market State:
{state}

📈 Momentum Persistence:
{persistence}

🌍 Social Sentiment:
{social}

😨 Fear & Greed:
{fear_greed}

📰 News Bias:
{news_bias}

🐋 Smart Money:
{smart_money}

📊 Breakout Probability:
{breakout_chance}%

⚠️ Fake Breakout Risk:
{fake_risk}

📉 Liquidation Risk:
{liquidation_risk}

━━━━━━━━━━━━━━━━━━
📈 Multi-Timeframe
━━━━━━━━━━━━━━━━━━

15m → {tf15}
1h  → {tf1h}
4h  → {tf4h}
1D  → Bullish 🚀

━━━━━━━━━━━━━━━━━━
🧠 AI Fusion Matrix
━━━━━━━━━━━━━━━━━━

Trend Strength:
{fusion_data['trend']}%

Momentum Quality:
{fusion_data['momentum']}%

Volatility Quality:
{fusion_data['volatility']}%

Smart Money Pressure:
{fusion_data['smart_money']}%

━━━━━━━━━━━━━━━━━━
🏆 Trade Grade
━━━━━━━━━━━━━━━━━━

{elite_grade}

━━━━━━━━━━━━━━━━━━
🎯 Adaptive Trade Setup
━━━━━━━━━━━━━━━━━━

TP1:
{tp1}

TP2:
{tp2}

TP3:
{tp3}

SL:
{sl}
━━━━━━━━━━━━━━━━━━
'''

        return message

    except Exception as e:
        return f"ERROR scanning {symbol}: {e}"


for coin in coins:

    result = analyze(coin)

    print(result)

    send_telegram(result)


heat_ranking = sorted(
    heat_ranking,
    key=lambda x: x[1],
    reverse=True
)

top_coins = heat_ranking[:5]

ranking_text = ""

for idx, coin in enumerate(top_coins, start=1):

    ranking_text += (
        f"#{idx} {coin[0]} 🚀\n"
    )

summary = f'''
━━━━━━━━━━━━━━━━━━
🏆 MARKET HEAT RANKING
━━━━━━━━━━━━━━━━━━

{ranking_text}
━━━━━━━━━━━━━━━━━━
'''

send_telegram(summary)
