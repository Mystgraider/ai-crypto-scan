import pandas as pd


class Indicators:
    """
    Pure pandas indicator calculations.
    No external ta library — avoids version compatibility issues
    with pandas 3.0 and ta-0.11.0.
    """

    MIN_CANDLES = 60

    @staticmethod
    def apply(df: pd.DataFrame) -> pd.DataFrame:

        if len(df) < Indicators.MIN_CANDLES:
            raise ValueError(
                f"Insufficient candles: {len(df)} < {Indicators.MIN_CANDLES}"
            )

        df = df.copy()

        c = df["close"]
        h = df["high"]
        l = df["low"]
        v = df["volume"]

        # ── EMA ────────────────────────────────────────────────────────
        df["ema_20"] = c.ewm(span=20, adjust=False).mean()
        df["ema_50"] = c.ewm(span=50, adjust=False).mean()

        # ── RSI ────────────────────────────────────────────────────────
        delta = c.diff()
        gain  = delta.clip(lower=0)
        loss  = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-10)
        df["rsi"] = 100 - (100 / (1 + rs))

        # ── ATR ────────────────────────────────────────────────────────
        tr = pd.concat([
            h - l,
            (h - c.shift()).abs(),
            (l - c.shift()).abs()
        ], axis=1).max(axis=1)
        df["atr"]     = tr.ewm(com=13, adjust=False).mean()
        df["atr_pct"] = (df["atr"] / c) * 100

        # ── ADX ────────────────────────────────────────────────────────
        plus_dm  = h.diff().clip(lower=0)
        minus_dm = (-l.diff()).clip(lower=0)
        # Where plus_dm < minus_dm, zero out plus_dm and vice versa
        plus_dm  = plus_dm.where(plus_dm > minus_dm, 0)
        minus_dm = minus_dm.where(minus_dm > plus_dm, 0)

        atr14    = tr.ewm(com=13, adjust=False).mean()
        plus_di  = 100 * plus_dm.ewm(com=13,  adjust=False).mean() / atr14.replace(0, 1e-10)
        minus_di = 100 * minus_dm.ewm(com=13, adjust=False).mean() / atr14.replace(0, 1e-10)
        dx       = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, 1e-10)
        df["adx"] = dx.ewm(com=13, adjust=False).mean()

        # ── ROC ────────────────────────────────────────────────────────
        df["roc"] = c.pct_change(periods=10) * 100

        # ── Volume ─────────────────────────────────────────────────────
        df["vol_ma"]     = v.rolling(20).mean()
        df["rel_volume"] = v / df["vol_ma"].replace(0, 1e-10)

        return df
