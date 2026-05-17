import ccxt
import pandas as pd
import ta
import requests
import os

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

exchange = ccxt.binance()

coins = [
    'BTC/USDT',
    'ETH/USDT',
    'SOL/USDT'
]

def send_telegram(message):

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    data = {
        "chat_id": CHAT_ID,
        "text": message
    }

    requests.post(url, data=data)

def analyze(symbol):

    ohlcv = exchange.fetch_ohlcv(
        symbol,
        timeframe='1h',
        limit=100
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

    # RSI
    df['rsi'] = ta.momentum.RSIIndicator(
        df['close']
    ).rsi()

    # MACD
    macd = ta.trend.MACD(df['close'])

    df['macd'] = macd.macd()
    df['signal'] = macd.macd_signal()

    latest = df.iloc[-1]

    price = latest['close']
    rsi = latest['rsi']

    macd_value = latest['macd']
    signal = latest['signal']

    decision = "HOLD ⚖️"
    confidence = 50

    bullish = 0

    if rsi < 35:
        bullish += 1

    if macd_value > signal:
        bullish += 1

    if bullish >= 2:
        decision = "BUY 🚀"
        confidence = 85

    elif rsi > 70 and macd_value < signal:
        decision = "SELL 📉"
        confidence = 80

    tp = round(price * 1.03, 2)
    sl = round(price * 0.98, 2)

    message = f'''
🤖 AI CRYPTO BOT

🪙 {symbol}

💰 Price:
{round(price,2)}

📊 RSI:
{round(rsi,2)}

📈 MACD:
{round(macd_value,2)}

⚡ Signal:
{decision}

🧠 Confidence:
{confidence}%

🎯 TP:
{tp}

🛑 SL:
{sl}
'''

    return message

for coin in coins:

    result = analyze(coin)

    print(result)

    send_telegram(result)
