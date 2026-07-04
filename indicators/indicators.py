import pandas as pd


class Indicators:
    """
    Pure pandas indicator calculations.
    No external ta library — avoids version compatibility issues
    with pandas 3.0 and ta-0.11.0.

    V6.0 additions:
    - MACD (12/26/9) — momentum direction + histogram
    - Bollinger Bands (20, 2σ) — volatility squeeze detection
    - Stochastic RSI (14,3,3) — overbought/oversold with smoothing
    - BB %B — position within bands (0=lower, 1=upper)
    - BB Width — squeeze detection
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
        delta    = c.diff()
        gain     = delta.clip(lower=0)
        loss     = (-delta).clip(lower=0)
        avg_gain = gain.ewm(com=13, adjust=False).mean()
        avg_loss = loss.ewm(com=13, adjust=False).mean()
        rs       = avg_gain / avg_loss.replace(0, 1e-10)
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

        # ── MACD (12/26/9) ─────────────────────────────────────────────
        ema12          = c.ewm(span=12, adjust=False).mean()
        ema26          = c.ewm(span=26, adjust=False).mean()
        df["macd"]     = ema12 - ema26
        df["macd_sig"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_sig"]

        # ── Bollinger Bands (20, 2σ) ───────────────────────────────────
        bb_mid          = c.rolling(20).mean()
        bb_std          = c.rolling(20).std()
        df["bb_upper"]  = bb_mid + 2 * bb_std
        df["bb_lower"]  = bb_mid - 2 * bb_std
        df["bb_mid"]    = bb_mid
        bb_range        = (df["bb_upper"] - df["bb_lower"]).replace(0, 1e-10)
        df["bb_pct_b"]  = (c - df["bb_lower"]) / bb_range   # 0=lower, 1=upper
        df["bb_width"]  = bb_range / bb_mid.replace(0, 1e-10) * 100  # % width

        # ── Squeeze detection (leading indicator) ───────────────────────
        # Where does current bb_width rank vs its own last 20 bars?
        # Low percentile = volatility has contracted = coiled spring,
        # move likely BEFORE it happens, not a confirmation of one
        # already in progress.
        df["bb_width_pctile"] = df["bb_width"].rolling(20).apply(
            lambda w: (w.iloc[-1] <= w).mean(), raw=False
        )

        # ── Stochastic RSI (14, 3, 3) ──────────────────────────────────
        rsi_series      = df["rsi"]
        rsi_min         = rsi_series.rolling(14).min()
        rsi_max         = rsi_series.rolling(14).max()
        stoch_rsi_raw   = (rsi_series - rsi_min) / (rsi_max - rsi_min).replace(0, 1e-10)
        df["stoch_k"]   = stoch_rsi_raw.rolling(3).mean() * 100   # %K smoothed
        df["stoch_d"]   = df["stoch_k"].rolling(3).mean()          # %D signal

        return df
