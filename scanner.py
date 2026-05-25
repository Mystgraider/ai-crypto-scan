import ccxt
import pandas as pd
import ta
import time
from datetime import datetime

CONFIG

TIMEFRAME_4H = '4h' TIMEFRAME_1H = '1h' TIMEFRAME_15M = '15m'

LOOKBACK = 200 MAX_SIGNALS = 5 MIN_RVOL = 1.5 MIN_ADX = 20 MIN_BREAKOUT_BODY = 65 MIN_ATR_PERCENT = 1.0 RR_RATIO = 2.0 COOLDOWN_MINUTES = 45

TOP_COINS = [ 'BTC/USDT:USDT', 'ETH/USDT:USDT', 'SOL/USDT:USDT', 'BNB/USDT:USDT', 'XRP/USDT:USDT', 'DOGE/USDT:USDT', 'AVAX/USDT:USDT', 'INJ/USDT:USDT', 'WLD/USDT:USDT', 'ONDO/USDT:USDT', 'SUI/USDT:USDT', 'WIF/USDT:USDT', 'TIA/USDT:USDT', 'OP/USDT:USDT', 'ARKM/USDT:USDT', 'SEI/USDT:USDT', 'PEPE/USDT:USDT', 'ICP/USDT:USDT', 'NEAR/USDT:USDT', ]

EXCHANGE

exchange = ccxt.bitget({ 'enableRateLimit': True, 'options': { 'defaultType': 'swap' } })

STORAGE

cooldowns = {}

HELPERS

def fetch_ohlcv(symbol, timeframe): try: data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=LOOKBACK) df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume']) return df except Exception as e: print(f"ERROR fetching {symbol}: {e}") return None

def calculate_indicators(df): df['ema20'] = ta.trend.ema_indicator(df['close'], window=20) df['ema50'] = ta.trend.ema_indicator(df['close'], window=50)

df['rsi'] = ta.momentum.rsi(df['close'], window=14)

macd = ta.trend.MACD(df['close'])
df['macd'] = macd.macd()
df['macd_signal'] = macd.macd_signal()

adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'])
df['adx'] = adx.adx()

atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'])
df['atr'] = atr.average_true_range()

df['volume_ma'] = df['volume'].rolling(20).mean()
df['rvol'] = df['volume'] / df['volume_ma']

return df

def get_trend(df): last = df.iloc[-1]

if last['ema20'] > last['ema50']:
    return 'BULL'
elif last['ema20'] < last['ema50']:
    return 'BEAR'
else:
    return 'RANGE'

def btc_market_context(): btc = fetch_ohlcv('BTC/USDT:USDT', TIMEFRAME_1H) btc = calculate_indicators(btc)

last = btc.iloc[-1]

trend = get_trend(btc)

atr_percent = (last['atr'] / last['close']) * 100

volatility = 'HIGH' if atr_percent >= MIN_ATR_PERCENT else 'LOW'

return trend, volatility

def breakout_body_percent(df): candle = df.iloc[-1]

body = abs(candle['close'] - candle['open'])
full = candle['high'] - candle['low']

if full == 0:
    return 0

return (body / full) * 100

def momentum_check(df, direction): candles = df.tail(3)

if direction == 'LONG':
    return all(c['close'] > c['open'] for _, c in candles.iterrows())
else:
    return all(c['close'] < c['open'] for _, c in candles.iterrows())

def macd_aligned(last, direction): if direction == 'LONG': return last['macd'] > last['macd_signal'] else: return last['macd'] < last['macd_signal']

def relative_strength_vs_btc(symbol_df, btc_df): symbol_change = ((symbol_df['close'].iloc[-1] - symbol_df['close'].iloc[-10]) / symbol_df['close'].iloc[-10]) * 100 btc_change = ((btc_df['close'].iloc[-1] - btc_df['close'].iloc[-10]) / btc_df['close'].iloc[-10]) * 100

return symbol_change - btc_change

def cooldown_active(symbol): if symbol not in cooldowns: return False

elapsed = time.time() - cooldowns[symbol]

return elapsed < (COOLDOWN_MINUTES * 60)

def score_signal(direction, btc_trend, rvol, adx, macd_ok, breakout_ok, rs_strength): score = 0

# BTC alignment
if direction == 'LONG' and btc_trend == 'BULL':
    score += 25

if direction == 'SHORT' and btc_trend == 'BEAR':
    score += 25

# RVOL
if rvol >= 2.0:
    score += 25
elif rvol >= 1.5:
    score += 15

# ADX
if adx >= 30:
    score += 20
elif adx >= 20:
    score += 10

# MACD
if macd_ok:
    score += 15

# Breakout candle
if breakout_ok:
    score += 15

# Relative strength
if direction == 'LONG' and rs_strength > 1:
    score += 10

if direction == 'SHORT' and rs_strength < -1:
    score += 10

return score

def build_signal(symbol): if cooldown_active(symbol): return None

df_4h = fetch_ohlcv(symbol, TIMEFRAME_4H)
df_1h = fetch_ohlcv(symbol, TIMEFRAME_1H)
df_15m = fetch_ohlcv(symbol, TIMEFRAME_15M)
btc_df = fetch_ohlcv('BTC/USDT:USDT', TIMEFRAME_1H)

if any(x is None for x in [df_4h, df_1h, df_15m, btc_df]):
    return None

df_4h = calculate_indicators(df_4h)
df_1h = calculate_indicators(df_1h)
df_15m = calculate_indicators(df_15m)
btc_df = calculate_indicators(btc_df)

last_4h = df_4h.iloc[-1]
last_1h = df_1h.iloc[-1]
last_15m = df_15m.iloc[-1]

trend_4h = get_trend(df_4h)
trend_1h = get_trend(df_1h)

btc_trend, btc_volatility = btc_market_context()

# Reject low volatility market
if btc_volatility == 'LOW':
    return None

# Determine direction
direction = None

if trend_4h == 'BULL' and trend_1h == 'BULL':
    direction = 'LONG'

if trend_4h == 'BEAR' and trend_1h == 'BEAR':
    direction = 'SHORT'

if direction is None:
    return None

# RVOL filter
rvol = last_15m['rvol']

if rvol < MIN_RVOL:
    return None

# ADX filter
adx = last_15m['adx']

if adx < MIN_ADX:
    return None

# MACD confirmation
macd_ok = macd_aligned(last_15m, direction)

if not macd_ok:
    return None

# Breakout body
body_percent = breakout_body_percent(df_15m)

breakout_ok = body_percent >= MIN_BREAKOUT_BODY

if not breakout_ok:
    return None

# Momentum
if not momentum_check(df_15m, direction):
    return None

# Relative strength vs BTC
rs_strength = relative_strength_vs_btc(df_15m, btc_df)

if direction == 'LONG' and rs_strength < 1:
    return None

if direction == 'SHORT' and rs_strength > -1:
    return None

# ATR
atr_percent = (last_15m['atr'] / last_15m['close']) * 100

if atr_percent < MIN_ATR_PERCENT:
    return None

# Entry / SL / TP
entry = last_15m['close']

if direction == 'LONG':
    sl = entry - (last_15m['atr'] * 1.2)
    tp = entry + ((entry - sl) * RR_RATIO)
else:
    sl = entry + (last_15m['atr'] * 1.2)
    tp = entry - ((sl - entry) * RR_RATIO)

# Score
score = score_signal(
    direction,
    btc_trend,
    rvol,
    adx,
    macd_ok,
    breakout_ok,
    rs_strength
)

if score < 70:
    return None

label = 'HIGH QUALITY'

if score >= 85:
    label = 'ELITE'

return {
    'symbol': symbol,
    'direction': direction,
    'score': score,
    'label': label,
    'entry': round(entry, 6),
    'sl': round(sl, 6),
    'tp': round(tp, 6),
    'rvol': round(rvol, 2),
    'adx': round(adx, 2),
    'rsi': round(last_15m['rsi'], 2),
    'btc_trend': btc_trend,
    'volatility': btc_volatility,
    'rs_strength': round(rs_strength, 2),
    'body_percent': round(body_percent, 2)
}

def print_signal(signal): print('\n' + '━' * 50) print(f"🏆 {signal['label']} SIGNAL") print('━' * 50) print(f"🪙 {signal['symbol']}") print(f"📢 {signal['direction']}") print(f"⭐ Score: {signal['score']}") print('━' * 50) print(f"BTC Trend: {signal['btc_trend']}") print(f"Volatility: {signal['volatility']}") print(f"RVOL: {signal['rvol']}x") print(f"ADX: {signal['adx']}") print(f"RSI: {signal['rsi']}") print(f"RS vs BTC: {signal['rs_strength']}%") print(f"Breakout Body: {signal['body_percent']}%") print('━' * 50) print(f"💰 Entry: {signal['entry']}") print(f"🛑 Stop Loss: {signal['sl']}") print(f"🎯 Take Profit: {signal['tp']}") print('━' * 50)

def run_scanner(): print('\n🚀 Elite Futures Scanner Started...')

while True:
    try:
        signals = []

        for symbol in TOP_COINS:
            print(f"Scanning {symbol}...")

            signal = build_signal(symbol)

            if signal:
                signals.append(signal)

        # Sort strongest first
        signals = sorted(signals, key=lambda x: x['score'], reverse=True)

        # Limit signals
        signals = signals[:MAX_SIGNALS]

        if len(signals) == 0:
            print('\n❌ No high quality setups found.')
        else:
            for signal in signals:
                print_signal(signal)

        print('\n⏰ Waiting 5 minutes...')
        time.sleep(300)

    except Exception as e:
        print(f"Scanner Error: {e}")
        time.sleep(30)

if name == 'main': run_scanner()
