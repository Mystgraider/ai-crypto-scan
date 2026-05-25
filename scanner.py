import ccxt
import pandas as pd 
import ta 
import time

=========================

CONFIG

=========================

TIMEFRAME_4H = '4h' TIMEFRAME_1H = '1h' TIMEFRAME_15M = '15m'

LOOKBACK = 200 MAX_SIGNALS = 5 MIN_RVOL = 1.5 MIN_ADX = 20 MIN_BREAKOUT_BODY = 65 MIN_ATR_PERCENT = 1.0 RR_RATIO = 2.0

TOP_COINS = [ 'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT', 'INJ/USDT:USDT', 'WLD/USDT:USDT', 'ONDO/USDT:USDT', 'SUI/USDT:USDT', 'WIF/USDT:USDT', 'TIA/USDT:USDT', 'OP/USDT:USDT', 'ARKM/USDT:USDT', 'SEI/USDT:USDT', 'PEPE/USDT:USDT', 'ICP/USDT:USDT', 'NEAR/USDT:USDT' ]

=========================

EXCHANGE

=========================

exchange = ccxt.bitget({ 'enableRateLimit': True, 'options': { 'defaultType': 'swap' } })

=========================

HELPERS

=========================

def fetch_ohlcv(symbol, timeframe): try: data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=LOOKBACK)

df = pd.DataFrame(
        data,
        columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']
    )

    return df

except Exception as e:
    print(f'ERROR fetching {symbol}: {e}')
    return None

def calculate_indicators(df): df['ema20'] = ta.trend.ema_indicator(df['close'], window=20) df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)

df['rsi'] = ta.momentum.rsi(df['close'], window=14)

macd = ta.trend.MACD(df['close'])
df['macd'] = macd.macd()
df['macd_signal'] = macd.macd_signal()

adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'])
df['adx'] = adx.adx()

atr = ta.volatility.AverageTrueRange(
    df['high'],
    df['low'],
    df['close']
)

df['atr'] = atr.average_true_range()

df['volume_ma'] = df['volume'].rolling(20).mean()
df['rvol'] = df['volume'] / df['volume_ma']

return df

def get_trend(df): last = df.iloc[-1]

if last['ema20'] > last['ema50']:
    return 'BULL'

if last['ema20'] < last['ema50']:
    return 'BEAR'

return 'RANGE'

def breakout_body_percent(df): candle = df.iloc[-1]

body = abs(candle['close'] - candle['open'])
full = candle['high'] - candle['low']

if full == 0:
    return 0

return (body / full) * 100

def macd_aligned(last, direction): if direction == 'LONG': return last['macd'] > last['macd_signal']

return last['macd'] < last['macd_signal']

def momentum_check(df, direction): candles = df.tail(3)

if direction == 'LONG':
    return all(row['close'] > row['open'] for _, row in candles.iterrows())

return all(row['close'] < row['open'] for _, row in candles.iterrows())

def build_signal(symbol): df_4h = fetch_ohlcv(symbol, TIMEFRAME_4H) df_1h = fetch_ohlcv(symbol, TIMEFRAME_1H) df_15m = fetch_ohlcv(symbol, TIMEFRAME_15M)

if df_4h is None or df_1h is None or df_15m is None:
    return None

df_4h = calculate_indicators(df_4h)
df_1h = calculate_indicators(df_1h)
df_15m = calculate_indicators(df_15m)

trend_4h = get_trend(df_4h)
trend_1h = get_trend(df_1h)

direction = None

if trend_4h == 'BULL' and trend_1h == 'BULL':
    direction = 'LONG'

if trend_4h == 'BEAR' and trend_1h == 'BEAR':
    direction = 'SHORT'

if direction is None:
    return None

last = df_15m.iloc[-1]

rvol = float(last['rvol'])
adx = float(last['adx'])
atr = float(last['atr'])
close = float(last['close'])

# HARD FILTERS
if rvol < MIN_RVOL:
    return None

if adx < MIN_ADX:
    return None

if not macd_aligned(last, direction):
    return None

if not momentum_check(df_15m, direction):
    return None

body_percent = breakout_body_percent(df_15m)

if body_percent < MIN_BREAKOUT_BODY:
    return None

atr_percent = (atr / close) * 100

if atr_percent < MIN_ATR_PERCENT:
    return None

entry = close

if direction == 'LONG':
    sl = entry - (atr * 1.2)
    tp = entry + ((entry - sl) * RR_RATIO)
else:
    sl = entry + (atr * 1.2)
    tp = entry - ((sl - entry) * RR_RATIO)

score = 0

if rvol >= 2:
    score += 35
else:
    score += 20

if adx >= 30:
    score += 25
else:
    score += 15

if body_percent >= 80:
    score += 20
else:
    score += 10

score += 20

label = 'HIGH QUALITY'

if score >= 85:
    label = 'ELITE'

return {
    'symbol': symbol,
    'direction': direction,
    'entry': round(entry, 6),
    'sl': round(sl, 6),
    'tp': round(tp, 6),
    'rvol': round(rvol, 2),
    'adx': round(adx, 2),
    'score': score,
    'label': label
}

def print_signal(signal): print('\n' + '=' * 50) print(f"{signal['label']} SIGNAL") print('=' * 50) print(f"PAIR: {signal['symbol']}") print(f"DIRECTION: {signal['direction']}") print(f"SCORE: {signal['score']}") print(f"RVOL: {signal['rvol']}x") print(f"ADX: {signal['adx']}") print('-' * 50) print(f"ENTRY: {signal['entry']}") print(f"STOP LOSS: {signal['sl']}") print(f"TAKE PROFIT: {signal['tp']}") print('=' * 50)

def run_scanner(): print('Elite Futures Scanner Started')

while True:
    try:
        signals = []

        for symbol in TOP_COINS:
            print(f'Scanning {symbol}...')

            signal = build_signal(symbol)

            if signal:
                signals.append(signal)

        signals = sorted(
            signals,
            key=lambda x: x['score'],
            reverse=True
        )

        signals = signals[:MAX_SIGNALS]

        if len(signals) == 0:
            print('No setups found.')
        else:
            for signal in signals:
                print_signal(signal)

        print('Waiting 5 minutes...')
        time.sleep(300)

    except Exception as e:
        print(f'SCANNER ERROR: {e}')
        time.sleep(30)

if name == 'main': run_scanner()
