import ccxt
import pandas as pd
import ta
import time

# =========================
# CONFIG
# =========================

TIMEFRAME_4H = '4h'
TIMEFRAME_1H = '1h'
TIMEFRAME_15M = '15m'

LOOKBACK = 200
MAX_SIGNALS = 5

MIN_RVOL = 1.2
MIN_ADX = 18
MIN_ATR_PERCENT = 0.5
MIN_BREAKOUT_BODY = 65

RR_RATIO = 2.0

# =========================
# COINS
# =========================

TOP_COINS = [

    # MAJORS
    'BTC/USDT:USDT',
    'ETH/USDT:USDT',
    'BNB/USDT:USDT',
    'SOL/USDT:USDT',
    'XRP/USDT:USDT',
    'DOGE/USDT:USDT',
    'AVAX/USDT:USDT',
    'LINK/USDT:USDT',
    'TRX/USDT:USDT',
    'DOT/USDT:USDT',
    'POL/USDT:USDT',
    'ATOM/USDT:USDT',
    'LTC/USDT:USDT',
    'ETC/USDT:USDT',

    # AI / TRENDING
    'FET/USDT:USDT',
    'TAO/USDT:USDT',
    'RENDER/USDT:USDT',
    'WLD/USDT:USDT',
    'ARKM/USDT:USDT',
    'INJ/USDT:USDT',
    'GRT/USDT:USDT',

    # DEFI
    'AAVE/USDT:USDT',
    'CRV/USDT:USDT',
    'LDO/USDT:USDT',
    'RUNE/USDT:USDT',
    'UNI/USDT:USDT',
    'SUSHI/USDT:USDT',

    # LAYER 1 / LAYER 2
    'ARB/USDT:USDT',
    'OP/USDT:USDT',
    'APT/USDT:USDT',
    'SEI/USDT:USDT',
    'SUI/USDT:USDT',
    'NEAR/USDT:USDT',
    'ICP/USDT:USDT',
    'FIL/USDT:USDT',
    'TIA/USDT:USDT',
    'IMX/USDT:USDT',

    # MEMES / HIGH VOL
    'PEPE/USDT:USDT',
    'WIF/USDT:USDT',
    'FLOKI/USDT:USDT',
    'SHIB/USDT:USDT',

    # TRENDING
    'ONDO/USDT:USDT',
    'ENA/USDT:USDT',
    'PYTH/USDT:USDT',
    'JUP/USDT:USDT',
    'KAS/USDT:USDT',
    'JASMY/USDT:USDT',
    'CFX/USDT:USDT',
    'ALGO/USDT:USDT',
]

# =========================
# EXCHANGE
# =========================

exchange = ccxt.bitget({
    'enableRateLimit': True,
    'options': {
        'defaultType': 'swap'
    }
})

# =========================
# FETCH DATA
# =========================

def fetch_ohlcv(symbol, timeframe):

    try:

        data = exchange.fetch_ohlcv(
            symbol,
            timeframe=timeframe,
            limit=LOOKBACK
        )

        df = pd.DataFrame(
            data,
            columns=[
                'timestamp',
                'open',
                'high',
                'low',
                'close',
                'volume'
            ]
        )

        return df

    except Exception as e:

        print(f'ERROR {symbol}: {e}')
        return None

# =========================
# INDICATORS
# =========================

def calculate_indicators(df):

    df['ema20'] = ta.trend.ema_indicator(
        df['close'],
        window=20
    )

    df['ema50'] = ta.trend.ema_indicator(
        df['close'],
        window=50
    )

    df['rsi'] = ta.momentum.rsi(
        df['close'],
        window=14
    )

    macd = ta.trend.MACD(df['close'])

    df['macd'] = macd.macd()
    df['macd_signal'] = macd.macd_signal()

    adx = ta.trend.ADXIndicator(
        df['high'],
        df['low'],
        df['close']
    )

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

# =========================
# TREND
# =========================

def get_trend(df):

    last = df.iloc[-1]

    if last['ema20'] > last['ema50']:
        return 'BULL'

    if last['ema20'] < last['ema50']:
        return 'BEAR'

    return 'RANGE'

# =========================
# BREAKOUT QUALITY
# =========================

def breakout_body_percent(df):

    candle = df.iloc[-1]

    body = abs(candle['close'] - candle['open'])

    full = candle['high'] - candle['low']

    if full == 0:
        return 0

    return (body / full) * 100

# =========================
# MOMENTUM
# =========================

def momentum_check(df, direction):

    candles = df.tail(3)

    if direction == 'LONG':

        return all(
            row['close'] > row['open']
            for _, row in candles.iterrows()
        )

    return all(
        row['close'] < row['open']
        for _, row in candles.iterrows()
    )

# =========================
# MACD ALIGNMENT
# =========================

def macd_aligned(last, direction):

    if direction == 'LONG':
        return last['macd'] > last['macd_signal']

    return last['macd'] < last['macd_signal']

# =========================
# BTC CONTEXT
# =========================

def btc_context():

    btc = fetch_ohlcv(
        'BTC/USDT:USDT',
        TIMEFRAME_1H
    )

    if btc is None:
        return 'RANGE'

    btc = calculate_indicators(btc)

    return get_trend(btc)

# =========================
# BUILD SIGNAL
# =========================

def build_signal(symbol):

    df_4h = fetch_ohlcv(symbol, TIMEFRAME_4H)
    df_1h = fetch_ohlcv(symbol, TIMEFRAME_1H)
    df_15m = fetch_ohlcv(symbol, TIMEFRAME_15M)

    if (
        df_4h is None
        or df_1h is None
        or df_15m is None
    ):
        return None

    df_4h = calculate_indicators(df_4h)
    df_1h = calculate_indicators(df_1h)
    df_15m = calculate_indicators(df_15m)

    trend_4h = get_trend(df_4h)
    trend_1h = get_trend(df_1h)

    btc_trend = btc_context()

    direction = None

    # LONG
    if (
        trend_4h == 'BULL'
        and trend_1h == 'BULL'
        and btc_trend == 'BULL'
    ):
        direction = 'LONG'

    # SHORT
    elif (
        trend_4h == 'BEAR'
        and trend_1h == 'BEAR'
        and btc_trend == 'BEAR'
    ):
        direction = 'SHORT'

    if direction is None:
        return None

    last = df_15m.iloc[-1]

    rvol = float(last['rvol'])
    adx = float(last['adx'])
    atr = float(last['atr'])
    close = float(last['close'])
    rsi = float(last['rsi'])

    # =========================
    # FILTERS
    # =========================

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

    # =========================
    # SCORE
    # =========================

    score = 0

    # RVOL
    if rvol >= 2:
        score += 30
    else:
        score += 20

    # ADX
    if adx >= 30:
        score += 25
    else:
        score += 15

    # BREAKOUT
    if body_percent >= 80:
        score += 20
    else:
        score += 10

    # MACD + MOMENTUM
    score += 25

    # RSI PENALTY
    if rsi > 80:
        score -= 10

    label = 'HIGH QUALITY'

    if score >= 80:
        label = 'ELITE'

    # =========================
    # ENTRY / SL / TP
    # =========================

    entry = close

    if direction == 'LONG':

        sl = entry - (atr * 1.2)

        tp = entry + ((entry - sl) * RR_RATIO)

    else:

        sl = entry + (atr * 1.2)

        tp = entry - ((sl - entry) * RR_RATIO)

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
        'rsi': round(rsi, 2)
    }

# =========================
# PRINT SIGNAL
# =========================

def print_signal(signal):

    print('\n' + '=' * 50)

    print(f"{signal['label']} SIGNAL")

    print('=' * 50)

    print(f"PAIR: {signal['symbol']}")
    print(f"DIRECTION: {signal['direction']}")
    print(f"SCORE: {signal['score']}")

    print('-' * 50)

    print(f"RVOL: {signal['rvol']}x")
    print(f"ADX: {signal['adx']}")
    print(f"RSI: {signal['rsi']}")

    print('-' * 50)

    print(f"ENTRY: {signal['entry']}")
    print(f"STOP LOSS: {signal['sl']}")
    print(f"TAKE PROFIT: {signal['tp']}")

    print('=' * 50)

# =========================
# MAIN SCANNER
# =========================

def run_scanner():

    print('Elite Futures Scanner Started')

    signals = []

    for symbol in TOP_COINS:

        time.sleep(0.3)

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

# =========================
# START
# =========================

if __name__ == '__main__':
    run_scanner()
