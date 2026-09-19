class TrendEngine:
    """
    Trend direction + score engine — V6.0

    analyze() preserves the legacy confirmed-trend behavior used when
    require_trend_gate=True. directional_scores() exposes independent
    LONG/SHORT evidence so disabling the trend gate does not copy one
    direction's score onto the opposite candidate.
    """

    ADX_MIN = 20
    ADX_STRONG = 25
    ADX_POWER = 35

    def directional_scores(
        self, price, ema20, ema50, adx=None, roc=None,
        macd=None, macd_sig=None, macd_hist=None,
        stoch_k=None, stoch_d=None, bb_pct_b=None,
    ):
        """Return independent directional evidence scores (never a hard gate)."""

        def score_long():
            if ema50 == 0:
                return 0.0
            gap = ((ema20 - ema50) / ema50) * 100
            score = min(100.0, max(0.0, 50 + gap * 12))
            if adx is not None:
                if adx >= self.ADX_POWER:
                    score = min(100.0, score + 14)
                elif adx >= self.ADX_STRONG:
                    score = min(100.0, score + 8)
            if roc is not None and roc > 0:
                score = min(100.0, score + 4)
            if macd_hist is not None and macd_hist > 0:
                score = min(100.0, score + 3)
            if stoch_k is not None and 40 <= stoch_k <= 70:
                score = min(100.0, score + 4)
            return round(score, 2)

        def score_short():
            if ema50 == 0:
                return 0.0
            gap = ((ema50 - ema20) / ema50) * 100
            score = min(100.0, max(0.0, 50 + gap * 12))
            if adx is not None:
                if adx >= self.ADX_POWER:
                    score = min(100.0, score + 14)
                elif adx >= self.ADX_STRONG:
                    score = min(100.0, score + 8)
            if roc is not None and roc < 0:
                score = min(100.0, score + 4)
            if macd_hist is not None and macd_hist < 0:
                score = min(100.0, score + 3)
            if stoch_k is not None and 30 <= stoch_k <= 60:
                score = min(100.0, score + 4)
            return round(score, 2)

        return {"LONG": score_long(), "SHORT": score_short()}

    def analyze(self, price, ema20, ema50, adx=None, roc=None,
                macd=None, macd_sig=None, macd_hist=None,
                stoch_k=None, stoch_d=None, bb_pct_b=None):

        if adx is not None and adx < self.ADX_MIN:
            return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "adx_weak"}

        if ema20 > ema50 and price > ema20:
            if macd is not None and macd_sig is not None and macd < macd_sig:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "macd_bearish"}
            if stoch_k is not None and stoch_k > 85:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "stoch_overbought"}
            if bb_pct_b is not None and bb_pct_b > 0.95:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "bb_upper_band"}

            score = self.directional_scores(
                price, ema20, ema50, adx, roc, macd, macd_sig,
                macd_hist, stoch_k, stoch_d, bb_pct_b
            )["LONG"]
            return {"direction": "LONG", "trend": "BULLISH", "score": score, "filters": "passed"}

        if ema20 < ema50 and price < ema20:
            if macd is not None and macd_sig is not None and macd > macd_sig:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "macd_bullish"}
            if stoch_k is not None and stoch_k < 15:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "stoch_oversold"}
            if bb_pct_b is not None and bb_pct_b < 0.05:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "bb_lower_band"}

            score = self.directional_scores(
                price, ema20, ema50, adx, roc, macd, macd_sig,
                macd_hist, stoch_k, stoch_d, bb_pct_b
            )["SHORT"]
            return {"direction": "SHORT", "trend": "BEARISH", "score": score, "filters": "passed"}

        return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "ema_misaligned"}
