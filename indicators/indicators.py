import ta
import pandas as pd


class Indicators:

    MIN_CANDLES = 60  # need at least 60 candles for EMA50 + ADX to be valid

    @staticmethod
    def apply(df):

        if len(df) < Indicators.MIN_CANDLES:
            raise ValueError(
                f"Insufficient candles: {len(df)} < {Indicators.MIN_CANDLES}"
            )

        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # Trend
        df["ema_20"] = ta.trend.ema_indicator(close=c, window=20)
        df["ema_50"] = ta.trend.ema_indicator(close=c, window=50)
        df["adx"]    = ta.trend.adx(high=h, low=l, close=c, window=14)

        # Momentum
        df["rsi"] = ta.momentum.rsi(close=c, window=14)
        df["roc"] = ta.momentum.roc(close=c, window=10)

        # Volatility
        df["atr"]     = ta.volatility.average_true_range(high=h, low=l, close=c, window=14)
        df["atr_pct"] = (df["atr"] / c) * 100

        # Volume
        df["vol_ma"]     = v.rolling(20).mean()
        df["rel_volume"] = v / df["vol_ma"]

        return df
