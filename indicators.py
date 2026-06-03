import pandas as pd


class Indicators:

    @staticmethod
    def apply(df):

        # EMA 20

        df["ema20"] = (
            df["close"]
            .ewm(
                span=20,
                adjust=False
            )
            .mean()
        )

        # EMA 50

        df["ema50"] = (
            df["close"]
            .ewm(
                span=50,
                adjust=False
            )
            .mean()
        )

        # RSI

        delta = df["close"].diff()

        gain = delta.clip(
            lower=0
        )

        loss = -delta.clip(
            upper=0
        )

        avg_gain = gain.ewm(
            com=13,
            adjust=False
        ).mean()

        avg_loss = loss.ewm(
            com=13,
            adjust=False
        ).mean()

        rs = avg_gain / avg_loss

        df["rsi"] = (
            100 -
            (
                100 /
                (1 + rs)
            )
        )

        # ATR

        hl = (
            df["high"] -
            df["low"]
        )

        hc = (
            df["high"] -
            df["close"].shift()
        ).abs()

        lc = (
            df["low"] -
            df["close"].shift()
        ).abs()

        tr = pd.concat(
            [hl, hc, lc],
            axis=1
        ).max(axis=1)

        df["atr"] = tr.ewm(
            com=13,
            adjust=False
        ).mean()

        # Volume MA

        df["vol_ma"] = (
            df["volume"]
            .rolling(20)
            .mean()
        )

        # Relative Volume

        df["rel_volume"] = (
            df["volume"] /
            df["vol_ma"]
        )

        return df
