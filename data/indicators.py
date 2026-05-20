import ta


def apply_indicators(df):

    df["ema_20"] = ta.trend.ema_indicator(
        df["close"],
        window=20
    )

    df["ema_50"] = ta.trend.ema_indicator(
        df["close"],
        window=50
    )

    df["adx"] = ta.trend.adx(
        df["high"],
        df["low"],
        df["close"]
    )

    df["rsi"] = ta.momentum.rsi(
        df["close"],
        window=14
    )

    df["atr"] = ta.volatility.average_true_range(
        df["high"],
        df["low"],
        df["close"]
    )

    df["roc"] = ta.momentum.roc(
        df["close"],
        window=5
    )

    return df
