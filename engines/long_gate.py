"""Direction-specific LONG pullback/reclaim setup for RRCE research.

This module is intentionally asymmetric with the SHORT setup. SHORT uses a
1H RSI band plus 15m anti-bearish confirmation and a 4H RSI floor. LONG uses
a bullish structural trend, a non-overextended 1H pullback/reclaim, improving
momentum, and explicit 15m bullish confirmation.

All inputs are closed candles only. The live price is used only for the final
anti-chase distance check.
"""

from __future__ import annotations

from typing import Any

import pandas as pd


def _num(row: pd.Series, key: str) -> float | None:
    value = row.get(key)
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if pd.notna(value) else None


def evaluate_long_setup(
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame | None,
    df_15m: pd.DataFrame | None,
    live_price: float,
    *,
    rsi_floor: float = 45.0,
    rsi_ceiling: float = 65.0,
    rsi_4h_ceiling: float = 68.0,
    max_atr_distance: float = 1.25,
) -> dict[str, Any]:
    """Evaluate the LONG pullback/reclaim setup using only closed candles."""
    result: dict[str, Any] = {
        "valid": False,
        "setup": "LONG_PULLBACK_RECLAIM",
        "reason": None,
    }

    if df_1h is None or len(df_1h) < 4:
        result["reason"] = "long_1h_insufficient_data"
        return result

    if df_4h is None or len(df_4h) < 2:
        result["reason"] = "long_4h_insufficient_data"
        return result

    if df_15m is None or len(df_15m) < 4:
        result["reason"] = "long_15m_insufficient_data"
        return result

    closed_1h = df_1h.iloc[:-1] if len(df_1h) > 1 else df_1h.iloc[0:0]
    closed_4h = df_4h.iloc[:-1] if len(df_4h) > 1 else df_4h.iloc[0:0]
    closed_15m = df_15m.iloc[:-1] if len(df_15m) > 1 else df_15m.iloc[0:0]

    if len(closed_1h) < 3 or len(closed_4h) < 1 or len(closed_15m) < 3:
        result["reason"] = "long_closed_candle_insufficient_data"
        return result

    h1 = closed_1h.iloc[-1]
    h1_prev = closed_1h.iloc[-2]
    h1_before = closed_1h.iloc[-3]
    h4 = closed_4h.iloc[-1]
    m15 = closed_15m.iloc[-1]
    m15_prev = closed_15m.iloc[-2]

    required_1h = ("close", "ema_20", "ema_50", "atr", "rsi", "macd_hist")
    required_4h = ("close", "ema_20", "ema_50", "rsi")
    required_15m = ("close", "ema_20", "ema_50", "macd_hist")

    if any(_num(h1, key) is None for key in required_1h):
        result["reason"] = "long_1h_indicator_unavailable"
        return result
    if any(_num(h4, key) is None for key in required_4h):
        result["reason"] = "long_4h_indicator_unavailable"
        return result
    if any(_num(m15, key) is None for key in required_15m):
        result["reason"] = "long_15m_indicator_unavailable"
        return result
    if _num(m15_prev, "close") is None or _num(m15_prev, "ema_20") is None:
        result["reason"] = "long_15m_previous_indicator_unavailable"
        return result

    h1_close = _num(h1, "close")
    h1_ema20 = _num(h1, "ema_20")
    h1_ema50 = _num(h1, "ema_50")
    h1_atr = _num(h1, "atr")
    h1_rsi = _num(h1, "rsi")
    h1_macd = _num(h1, "macd_hist")
    h1_prev_close = _num(h1_prev, "close")
    h1_prev_ema20 = _num(h1_prev, "ema_20")
    h1_before_close = _num(h1_before, "close")
    h1_before_ema20 = _num(h1_before, "ema_20")

    h4_close = _num(h4, "close")
    h4_ema20 = _num(h4, "ema_20")
    h4_ema50 = _num(h4, "ema_50")
    h4_rsi = _num(h4, "rsi")

    m15_close = _num(m15, "close")
    m15_ema20 = _num(m15, "ema_20")
    m15_ema50 = _num(m15, "ema_50")
    m15_macd = _num(m15, "macd_hist")
    m15_prev_close = _num(m15_prev, "close")
    m15_prev_ema20 = _num(m15_prev, "ema_20")

    assert all(
        value is not None
        for value in (
            h1_close, h1_ema20, h1_ema50, h1_atr, h1_rsi, h1_macd,
            h1_prev_close, h1_prev_ema20, h1_before_close, h1_before_ema20,
            h4_close, h4_ema20, h4_ema50, h4_rsi,
            m15_close, m15_ema20, m15_ema50, m15_macd,
            m15_prev_close, m15_prev_ema20,
        )
    )

    checks = {
        "4h_bullish_structure": h4_ema20 >= h4_ema50 and h4_close >= h4_ema50,
        "4h_not_overbought": h4_rsi <= rsi_4h_ceiling,
        "1h_bullish_structure": h1_ema20 > h1_ema50 and h1_close >= h1_ema50,
        "1h_rsi_pullback_zone": rsi_floor <= h1_rsi <= rsi_ceiling,
        "1h_momentum_improving": h1_macd > 0.0,
        "1h_reclaim_ema20": (
            (h1_before_close <= h1_before_ema20 and h1_prev_close > h1_prev_ema20)
            or (h1_prev_close <= h1_prev_ema20 and h1_close > h1_ema20)
        ),
        "1h_not_chasing": (
            h1_close <= h1_ema20 + (max_atr_distance * h1_atr)
        ),
        "15m_bullish_structure": m15_ema20 >= m15_ema50 and m15_close >= m15_ema20,
        "15m_reclaim": (
            m15_prev_close <= m15_prev_ema20 and m15_close > m15_ema20
        ),
        "15m_momentum_positive": m15_macd > 0.0,
    }

    # The setup needs the higher-timeframe structure, the 1H reclaim,
    # and at least one 15m momentum/reclaim confirmation. This avoids turning
    # the LONG setup into a mirror image of the SHORT gate.
    core_checks = (
        checks["4h_bullish_structure"]
        and checks["4h_not_overbought"]
        and checks["1h_bullish_structure"]
        and checks["1h_rsi_pullback_zone"]
        and checks["1h_momentum_improving"]
        and checks["1h_reclaim_ema20"]
        and checks["1h_not_chasing"]
        and checks["15m_bullish_structure"]
        and (checks["15m_reclaim"] or checks["15m_momentum_positive"])
    )

    live_distance_ok = True
    if live_price <= 0:
        live_distance_ok = False
    elif h1_atr > 0:
        live_distance_ok = live_price <= h1_ema20 + (max_atr_distance * h1_atr)

    checks["live_not_chasing"] = live_distance_ok
    result.update({
        "valid": bool(core_checks and live_distance_ok),
        "reason": None if core_checks and live_distance_ok else "long_setup_conditions_not_met",
        "checks": checks,
        "metrics": {
            "rsi_1h": h1_rsi,
            "rsi_4h": h4_rsi,
            "atr_1h": h1_atr,
            "ema20_1h": h1_ema20,
            "ema50_1h": h1_ema50,
            "macd_hist_1h": h1_macd,
            "macd_hist_15m": m15_macd,
            "live_price": float(live_price),
        },
    })
    return result
