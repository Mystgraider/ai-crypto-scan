def detect_market_regime(df):

    atr = df["atr"].iloc[-1]

    price = df["close"].iloc[-1]

    atr_percent = (atr / price) * 100

    ema20 = df["ema_20"].iloc[-1]

    ema50 = df["ema_50"].iloc[-1]

    if atr_percent < 1:
        return "dead_market"

    if abs(ema20 - ema50) < price * 0.002:
        return "ranging"

    if atr_percent > 3:
        return "volatile"

    return "trending"
