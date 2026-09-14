from config import CONFIG


class TrendEngine:
    """
    Trend direction + score engine — V6.0
    ========================================
    Upgrades from V5.x:
    - MACD cross confirmation (prevents entries against momentum)
    - Stochastic RSI extreme filter (blocks overbought LONG / oversold SHORT)
    - BB %B filter (blocks buying at upper band, shorting at lower band)
    - Finer ADX scoring tiers
    - Stronger EMA gap scoring (less fake signals in weak trends)

    When require_trend_gate=True, the historical directional result is
    returned and the scanner may use it as a hard gate.

    When require_trend_gate=False, TrendEngine is supporting evidence only.
    In that mode its directional hint MUST NOT suppress the opposite direction.
    The scanner's existing orchestration interprets direction=NONE as
    "evaluate both LONG and SHORT". We therefore return a neutral score of
    50 while preserving the actual trend direction and directional score in
    direction_hint/directional_score for the later direction-aware pipeline.
    """

    ADX_MIN    = 20
    ADX_STRONG = 25
    ADX_POWER  = 35

    @staticmethod
    def _result(direction, trend, score, filters):
        """Return a direction-aware result without leaking a soft hint into gating."""
        if not CONFIG.get("require_trend_gate", True) and direction in ("LONG", "SHORT"):
            return {
                "direction": "NONE",
                "trend": trend,
                "score": 50.0,
                "filters": filters,
                "direction_hint": direction,
                "directional_score": round(score, 2),
            }
        return {
            "direction": direction,
            "trend": trend,
            "score": round(score, 2),
            "filters": filters,
        }

    def analyze(self, price, ema20, ema50, adx=None, roc=None,
                macd=None, macd_sig=None, macd_hist=None,
                stoch_k=None, stoch_d=None,
                bb_pct_b=None):

        # Hard gate: no ADX = no confirmed trend
        if adx is not None and adx < self.ADX_MIN:
            return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "adx_weak"}

        # ── LONG ──────────────────────────────────────────────────────
        if ema20 > ema50 and price > ema20:

            # MACD filter: MACD must be above signal (bullish momentum)
            if macd is not None and macd_sig is not None:
                if macd < macd_sig:
                    return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "macd_bearish"}

            # Stoch RSI filter: block if extremely overbought (>85)
            if stoch_k is not None and stoch_k > 85:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "stoch_overbought"}

            # BB filter: block buying at/above upper band (>0.95)
            if bb_pct_b is not None and bb_pct_b > 0.95:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "bb_upper_band"}

            gap   = ((ema20 - ema50) / ema50) * 100
            score = min(100.0, 50 + gap * 12)

            if adx:
                if adx >= self.ADX_POWER:
                    score = min(100.0, score + 14)
                elif adx >= self.ADX_STRONG:
                    score = min(100.0, score + 8)

            if roc and roc > 0:
                score = min(100.0, score + 4)

            if macd_hist is not None and macd_hist > 0:
                score = min(100.0, score + 3)

            if stoch_k is not None and 40 <= stoch_k <= 70:
                score = min(100.0, score + 4)

            return self._result("LONG", "BULLISH", score, "passed")

        # ── SHORT ─────────────────────────────────────────────────────
        if ema20 < ema50 and price < ema20:

            # MACD filter: MACD must be below signal (bearish momentum)
            if macd is not None and macd_sig is not None:
                if macd > macd_sig:
                    return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "macd_bullish"}

            # Stoch RSI filter: block if extremely oversold (<15)
            if stoch_k is not None and stoch_k < 15:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "stoch_oversold"}

            # BB filter: block shorting at/below lower band (<0.05)
            if bb_pct_b is not None and bb_pct_b < 0.05:
                return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "bb_lower_band"}

            gap   = ((ema50 - ema20) / ema50) * 100
            score = min(100.0, 50 + gap * 12)

            if adx:
                if adx >= self.ADX_POWER:
                    score = min(100.0, score + 14)
                elif adx >= self.ADX_STRONG:
                    score = min(100.0, score + 8)

            if roc and roc < 0:
                score = min(100.0, score + 4)

            if macd_hist is not None and macd_hist < 0:
                score = min(100.0, score + 3)

            if stoch_k is not None and 30 <= stoch_k <= 60:
                score = min(100.0, score + 4)

            return self._result("SHORT", "BEARISH", score, "passed")

        return {"direction": "NONE", "trend": "RANGE", "score": 0.0, "filters": "ema_misaligned"}
