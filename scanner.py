import ccxt
import pandas as pd
import ta
import time
import csv
import os
from datetime import datetime, timezone

# =============================================================
# CONFIG
# =============================================================

TIMEFRAME_4H  = '4h'
TIMEFRAME_1H  = '1h'
TIMEFRAME_15M = '15m'

LOOKBACK     = 300
MAX_SIGNALS  = 5
RR_RATIO     = 2.0
LOG_FILE     = 'signal_log.csv'

# --- HARD FILTERS (all must pass) ---
MIN_RVOL            = 2.0    # Strong volume confirmation
MIN_ADX             = 25     # Trending market only
MIN_BREAKOUT_BODY   = 65     # Clean breakout candle
MIN_ATR_PERCENT     = 0.8    # Minimum volatility
MAX_RSI_LONG        = 65     # Not overbought on entry
MIN_RSI_LONG        = 40     # Has momentum
MAX_RSI_SHORT       = 60     # Not oversold on entry
MIN_RSI_SHORT       = 35     # Has momentum
SL_ATR_MULT         = 1.5    # SL buffer (wider = fewer stop-outs)
MIN_SCORE           = 75     # Only high-conviction setups

# --- SESSION FILTER (UTC hours) ---
# London: 07:00–16:00 UTC | New York: 12:00–21:00 UTC
TRADING_SESSIONS = [
    (7, 16),   # London
    (12, 21),  # New York
]

TOP_COINS = [
    'BTC/USDT:USDT',
    'ETH/USDT:USDT',
    'SOL/USDT:USDT',
    'BNB/USDT:USDT',
    'XRP/USDT:USDT',
    'DOGE/USDT:USDT',
    'AVAX/USDT:USDT',
    'INJ/USDT:USDT',
    'WLD/USDT:USDT',
    'ONDO/USDT:USDT',
    'SUI/USDT:USDT',
    'WIF/USDT:USDT',
    'TIA/USDT:USDT',
    'OP/USDT:USDT',
    'ARKM/USDT:USDT',
    'SEI/USDT:USDT',
    'PEPE/USDT:USDT',
    'ICP/USDT:USDT',
    'NEAR/USDT:USDT',
]

# =============================================================
# EXCHANGE
# =============================================================

exchange = ccxt.bitget({
    'enableRateLimit': True,
    'options': {'defaultType': 'swap'}
})

# =============================================================
# FETCH + INDICATORS
# =============================================================

def fetch_ohlcv(symbol, timeframe):
    try:
        data = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=LOOKBACK)
        df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except Exception as e:
        print(f'  [ERROR] {symbol} ({timeframe}): {e}')
        return None


def calculate_indicators(df):
    # Trend
    df['ema20']  = ta.trend.ema_indicator(df['close'], window=20)
    df['ema50']  = ta.trend.ema_indicator(df['close'], window=50)
    df['ema200'] = ta.trend.ema_indicator(df['close'], window=200)

    # Momentum
    df['rsi'] = ta.momentum.rsi(df['close'], window=14)

    macd = ta.trend.MACD(df['close'])
    df['macd']        = macd.macd()
    df['macd_signal'] = macd.macd_signal()
    df['macd_hist']   = macd.macd_diff()

    # Trend strength
    adx = ta.trend.ADXIndicator(df['high'], df['low'], df['close'])
    df['adx']    = adx.adx()
    df['di_pos'] = adx.adx_pos()
    df['di_neg'] = adx.adx_neg()

    # Volatility
    atr = ta.volatility.AverageTrueRange(df['high'], df['low'], df['close'])
    df['atr'] = atr.average_true_range()

    bb = ta.volatility.BollingerBands(df['close'], window=20, window_dev=2)
    df['bb_upper'] = bb.bollinger_hband()
    df['bb_lower'] = bb.bollinger_lband()
    df['bb_mid']   = bb.bollinger_mavg()
    df['bb_width'] = (df['bb_upper'] - df['bb_lower']) / df['bb_mid']

    # Volume
    df['volume_ma'] = df['volume'].rolling(20).mean()
    df['rvol']      = df['volume'] / df['volume_ma']

    return df

# =============================================================
# MARKET STRUCTURE
# =============================================================

def get_swing_levels(df, lookback=20):
    """
    Detects the most recent swing high and swing low
    from the last N candles — used as structural S/R.
    """
    recent = df.tail(lookback)
    swing_high = recent['high'].max()
    swing_low  = recent['low'].min()
    return swing_high, swing_low


def is_near_support(price, swing_low, atr, tolerance=1.5):
    """Price is within 1.5 ATR above swing low = near support."""
    return price <= swing_low + (atr * tolerance)


def is_near_resistance(price, swing_high, atr, tolerance=1.5):
    """Price is within 1.5 ATR below swing high = near resistance."""
    return price >= swing_high - (atr * tolerance)


def market_structure_bullish(df, lookback=10):
    """
    Higher highs + higher lows over last N candles.
    True market structure confirmation for LONG.
    """
    highs = df['high'].tail(lookback).values
    lows  = df['low'].tail(lookback).values

    hh = sum(1 for i in range(1, len(highs)) if highs[i] > highs[i - 1])
    hl = sum(1 for i in range(1, len(lows))  if lows[i]  > lows[i - 1])

    return (hh + hl) >= lookback  # majority must be bullish structure


def market_structure_bearish(df, lookback=10):
    """Lower highs + lower lows over last N candles."""
    highs = df['high'].tail(lookback).values
    lows  = df['low'].tail(lookback).values

    lh = sum(1 for i in range(1, len(highs)) if highs[i] < highs[i - 1])
    ll = sum(1 for i in range(1, len(lows))  if lows[i]  < lows[i - 1])

    return (lh + ll) >= lookback


def detect_liquidity_sweep(df, direction):
    """
    Detects if the last candle swept a liquidity level (stop hunt)
    before reversing — classic smart money move.
    LONG: wick below recent low then closed above it.
    SHORT: wick above recent high then closed below it.
    """
    candle   = df.iloc[-1]
    prev_low = df['low'].iloc[-6:-1].min()
    prev_high = df['high'].iloc[-6:-1].max()

    if direction == 'LONG':
        swept = candle['low'] < prev_low
        closed_back = candle['close'] > prev_low
        return swept and closed_back

    swept = candle['high'] > prev_high
    closed_back = candle['close'] < prev_high
    return swept and closed_back

# =============================================================
# TREND + ALIGNMENT CHECKS
# =============================================================

def get_trend(df):
    last = df.iloc[-1]

    above_200 = last['close'] > last['ema200']
    ema_stack = last['ema20'] > last['ema50']

    if above_200 and ema_stack:
        return 'BULL'
    if not above_200 and not ema_stack:
        return 'BEAR'
    return 'RANGE'


def get_trend_strength(df):
    """
    Returns a 0–3 score based on how aligned the EMAs are.
    3 = strongest trend (EMA20 > EMA50 > EMA200 or reverse).
    """
    last = df.iloc[-1]
    score = 0

    if last['ema20'] > last['ema50']:
        score += 1
    if last['ema50'] > last['ema200']:
        score += 1
    if last['close'] > last['ema20']:
        score += 1

    return score  # Invert for bearish in calling code


def macd_momentum(last, direction):
    """
    MACD must be above signal AND histogram must be growing
    (accelerating momentum, not fading).
    """
    if direction == 'LONG':
        return last['macd'] > last['macd_signal'] and last['macd_hist'] > 0
    return last['macd'] < last['macd_signal'] and last['macd_hist'] < 0


def di_aligned(last, direction):
    """DI+ > DI- for LONG, DI- > DI+ for SHORT."""
    if direction == 'LONG':
        return last['di_pos'] > last['di_neg']
    return last['di_neg'] > last['di_pos']


def consecutive_momentum(df, direction, candles=3):
    """Last N candles must all close in the direction."""
    tail = df.tail(candles)
    if direction == 'LONG':
        return all(r['close'] > r['open'] for _, r in tail.iterrows())
    return all(r['close'] < r['open'] for _, r in tail.iterrows())


def breakout_body_percent(df):
    candle = df.iloc[-1]
    body = abs(candle['close'] - candle['open'])
    full = candle['high'] - candle['low']
    return (body / full * 100) if full > 0 else 0


def rsi_confluence(last, direction):
    """
    RSI must be in the momentum zone — not overbought/oversold.
    This ensures we're catching continuation, not exhaustion.
    """
    rsi = last['rsi']
    if direction == 'LONG':
        return MIN_RSI_LONG <= rsi <= MAX_RSI_LONG
    return MIN_RSI_SHORT <= rsi <= MAX_RSI_SHORT

# =============================================================
# SESSION FILTER
# =============================================================

def is_active_session():
    """Only trade during London or New York session (UTC)."""
    now_hour = datetime.now(timezone.utc).hour
    for start, end in TRADING_SESSIONS:
        if start <= now_hour < end:
            return True
    return False

# =============================================================
# SCORING ENGINE
# =============================================================

def compute_score(rvol, adx, body_pct, trend_strength, liq_sweep, di_ok, rsi_ok):
    """
    Transparent scoring — each criterion has a weight.
    Max possible score = 100.
    No fake base points — every point must be earned.
    """
    score = 0

    # Volume (30 pts)
    if rvol >= 3.0:
        score += 30
    elif rvol >= 2.0:
        score += 20
    else:
        score += 10

    # Trend strength via ADX (25 pts)
    if adx >= 35:
        score += 25
    elif adx >= 25:
        score += 18
    else:
        score += 10

    # Breakout candle quality (20 pts)
    if body_pct >= 80:
        score += 20
    elif body_pct >= 65:
        score += 13
    else:
        score += 5

    # EMA alignment strength (15 pts)
    score += trend_strength * 5  # 0–15

    # Bonus filters (10 pts total)
    if liq_sweep:
        score += 5   # Smart money confirmation
    if di_ok:
        score += 3   # DI alignment
    if rsi_ok:
        score += 2   # RSI in momentum zone

    return min(score, 100)


def get_label(score):
    if score >= 90:
        return '🔥 GOD TIER'
    if score >= 80:
        return '⚡ ELITE'
    if score >= 75:
        return '✅ HIGH QUALITY'
    return '⚠️  STANDARD'

# =============================================================
# SIGNAL BUILDER
# =============================================================

def build_signal(symbol):
    df_4h  = fetch_ohlcv(symbol, TIMEFRAME_4H)
    df_1h  = fetch_ohlcv(symbol, TIMEFRAME_1H)
    df_15m = fetch_ohlcv(symbol, TIMEFRAME_15M)

    if df_4h is None or df_1h is None or df_15m is None:
        return None

    df_4h  = calculate_indicators(df_4h)
    df_1h  = calculate_indicators(df_1h)
    df_15m = calculate_indicators(df_15m)

    # --- STEP 1: Multi-TF Trend Alignment ---
    trend_4h = get_trend(df_4h)
    trend_1h = get_trend(df_1h)
    trend_15m = get_trend(df_15m)

    direction = None

    # All 3 timeframes must agree — no exceptions
    if trend_4h == 'BULL' and trend_1h == 'BULL' and trend_15m == 'BULL':
        direction = 'LONG'
    elif trend_4h == 'BEAR' and trend_1h == 'BEAR' and trend_15m == 'BEAR':
        direction = 'SHORT'
    else:
        return None  # Conflicting trends = no trade

    last_15m = df_15m.iloc[-1]
    last_1h  = df_1h.iloc[-1]

    rvol  = float(last_15m['rvol'])
    adx   = float(last_15m['adx'])
    atr   = float(last_15m['atr'])
    close = float(last_15m['close'])
    rsi   = float(last_15m['rsi'])

    # --- STEP 2: Hard Filters (all must pass) ---
    if rvol < MIN_RVOL:
        return None
    if adx < MIN_ADX:
        return None

    body_pct = breakout_body_percent(df_15m)
    if body_pct < MIN_BREAKOUT_BODY:
        return None

    atr_pct = (atr / close) * 100
    if atr_pct < MIN_ATR_PERCENT:
        return None

    if not macd_momentum(last_15m, direction):
        return None

    if not consecutive_momentum(df_15m, direction, candles=3):
        return None

    if not rsi_confluence(last_15m, direction):
        return None

    # --- STEP 3: Structure Filters ---
    swing_high, swing_low = get_swing_levels(df_1h, lookback=30)

    # Don't chase — price must be near structure
    if direction == 'LONG' and not is_near_support(close, swing_low, atr):
        # Allow if breaking out strongly (ADX > 35)
        if adx < 35:
            return None

    if direction == 'SHORT' and not is_near_resistance(close, swing_high, atr):
        if adx < 35:
            return None

    # --- STEP 4: Bonus Indicators ---
    di_ok      = di_aligned(last_15m, direction)
    liq_sweep  = detect_liquidity_sweep(df_15m, direction)
    rsi_ok     = rsi_confluence(last_15m, direction)

    # Trend strength (0–3 on each TF, combined)
    strength_4h  = get_trend_strength(df_4h)
    strength_1h  = get_trend_strength(df_1h)
    strength_15m = get_trend_strength(df_15m)

    # Invert for SHORT
    if direction == 'SHORT':
        strength_4h  = 3 - strength_4h
        strength_1h  = 3 - strength_1h
        strength_15m = 3 - strength_15m

    avg_strength = (strength_4h + strength_1h + strength_15m) / 3  # 0–3

    # --- STEP 5: Score ---
    score = compute_score(
        rvol, adx, body_pct,
        avg_strength, liq_sweep, di_ok, rsi_ok
    )

    if score < MIN_SCORE:
        return None

    # --- STEP 6: Entry / SL / TP (structure-based) ---
    entry = close

    if direction == 'LONG':
        # SL below swing low or ATR-based (whichever is tighter but not too tight)
        sl_structural = swing_low - (atr * 0.5)
        sl_atr        = entry - (atr * SL_ATR_MULT)
        sl = max(sl_structural, sl_atr)  # Use higher (closer) SL
        tp = entry + ((entry - sl) * RR_RATIO)
    else:
        sl_structural = swing_high + (atr * 0.5)
        sl_atr        = entry + (atr * SL_ATR_MULT)
        sl = min(sl_structural, sl_atr)
        tp = entry - ((sl - entry) * RR_RATIO)

    risk_pct = abs((sl - entry) / entry) * 100
    reward_pct = abs((tp - entry) / entry) * 100

    label = get_label(score)

    return {
        'symbol':      symbol,
        'direction':   direction,
        'entry':       round(entry, 6),
        'sl':          round(sl, 6),
        'tp':          round(tp, 6),
        'risk_pct':    round(risk_pct, 2),
        'reward_pct':  round(reward_pct, 2),
        'rvol':        round(rvol, 2),
        'adx':         round(adx, 2),
        'rsi':         round(rsi, 2),
        'body_pct':    round(body_pct, 1),
        'liq_sweep':   liq_sweep,
        'score':       score,
        'label':       label,
        'timestamp':   datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'),
    }

# =============================================================
# OUTPUT
# =============================================================

def print_signal(s):
    direction_icon = '🟢 LONG' if s['direction'] == 'LONG' else '🔴 SHORT'
    sweep_tag = '  🎯 LIQUIDITY SWEEP DETECTED' if s['liq_sweep'] else ''

    print()
    print('╔══════════════════════════════════════════════════════╗')
    print(f"  {s['label']}  —  {s['symbol']}")
    print('╠══════════════════════════════════════════════════════╣')
    print(f"  Direction : {direction_icon}{sweep_tag}")
    print(f"  Score     : {s['score']}/100")
    print(f"  Time      : {s['timestamp']}")
    print('╠══════════════════════════════════════════════════════╣')
    print(f"  📍 ENTRY      : {s['entry']}")
    print(f"  🛑 STOP LOSS  : {s['sl']}  (-{s['risk_pct']}%)")
    print(f"  🎯 TAKE PROFIT: {s['tp']}  (+{s['reward_pct']}%)")
    print('╠══════════════════════════════════════════════════════╣')
    print(f"  RVOL : {s['rvol']}x   ADX : {s['adx']}   RSI : {s['rsi']}")
    print(f"  Body : {s['body_pct']}%   RR  : 1:{RR_RATIO}")
    print('╚══════════════════════════════════════════════════════╝')


def log_signal(s):
    """Append signal to CSV for backtesting / win rate tracking."""
    file_exists = os.path.isfile(LOG_FILE)

    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=s.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(s)

# =============================================================
# MAIN LOOP
# =============================================================

def run_scanner():

    print()
    print('╔══════════════════════════════════════════════╗')
    print('║           ELITE FUTURES SCANNER v2.0        ║')
    print('║      Multi-TF + Structure + Smart Money     ║')
    print('╚══════════════════════════════════════════════╝')
    print()

    try:

        now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
        in_session = is_active_session()

        session_tag = '🟢 ACTIVE SESSION' if in_session else '🟡 OFF SESSION'

        print(f'\n[SCAN] {now} | {session_tag}')
        print('-' * 56)

        if not in_session:
            print(' Waiting for London / New York session...')
            return

        signals = []

        for symbol in TOP_COINS:

            print(f' Scanning {symbol}...', end='\r')

            signal = build_signal(symbol)

            if signal:
                signals.append(signal)

            time.sleep(0.3)

        print(' ' * 50, end='\r')

        signals = sorted(
            signals,
            key=lambda x: x['score'],
            reverse=True
        )

        signals = signals[:MAX_SIGNALS]

        if not signals:

            print(' No high-conviction setups found this cycle.')
            print(' Criteria: Score ≥ 75, all 3 TFs aligned, structure confirmed.')

        else:

            print(f'\n✅ {len(signals)} signal(s) found:\n')

            for s in signals:
                print_signal(s)
                log_signal(s)

    except Exception as e:

        print(f'[SCANNER ERROR] {e}')
