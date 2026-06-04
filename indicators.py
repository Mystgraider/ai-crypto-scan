import ta


class Indicators:

    @staticmethod
    def apply(df):

        # EMA 20
        df["ema_20"] = ta.trend.ema_indicator(
            close=df["close"],
            window=20
        )

        # EMA 50
        df["ema_50"] = ta.trend.ema_indicator(
            close=df["close"],
            window=50
        )

        # ADX
        df["adx"] = ta.trend.adx(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=14
        )

        # RSI
        df["rsi"] = ta.momentum.rsi(
            close=df["close"],
            window=14
        )

        # ATR
        df["atr"] = ta.volatility.average_true_range(
            high=df["high"],
            low=df["low"],
            close=df["close"],
            window=14
        )

        # Volume MA
        df["vol_ma"] = (
            df["volume"]
            .rolling(20)
            .mean()
        )

        # Relative Volume
        df["rel_volume"] = (
            df["volume"]
            / df["vol_ma"]
        )

        return df
