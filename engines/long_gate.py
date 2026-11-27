"""Asymmetric LONG pullback/reclaim setup used by the RRCE research path."""
from __future__ import annotations
from typing import Any
import pandas as pd

def _f(row: pd.Series, key: str) -> float | None:
    try:
        value = float(row[key])
    except (KeyError, TypeError, ValueError):
        return None
    return value if pd.notna(value) else None

def evaluate_long_setup(
    df_1h: pd.DataFrame,
    df_4h: pd.DataFrame | None,
    df_15m: pd.DataFrame | None,
    live_price: float,
    *,
    rsi_floor: float = 50.0,
    rsi_ceiling: float = 60.0,
    rsi_4h_ceiling: float = 68.0,
    min_adx_1h: float = 30.0,
    min_adx_15m: float = 25.0,
    max_atr_distance: float = 1.25,
) -> dict[str, Any]:
    result: dict[str, Any] = {"valid": False, "setup": "LONG_PULLBACK_RECLAIM", "reason": None}
    if df_1h is None or len(df_1h) < 4:
        result["reason"] = "long_1h_insufficient_data"; return result
    if df_4h is None or len(df_4h) < 2:
        result["reason"] = "long_4h_insufficient_data"; return result
    if df_15m is None or len(df_15m) < 4:
        result["reason"] = "long_15m_insufficient_data"; return result

    h1c, h4c, m15c = df_1h.iloc[:-1], df_4h.iloc[:-1], df_15m.iloc[:-1]
    if len(h1c) < 3 or len(h4c) < 1 or len(m15c) < 3:
        result["reason"] = "long_closed_candle_insufficient_data"; return result

    h1, h1p, h1pp = h1c.iloc[-1], h1c.iloc[-2], h1c.iloc[-3]
    h4, m15, m15p = h4c.iloc[-1], m15c.iloc[-1], m15c.iloc[-2]
    keys = {
        "h1": ("close","ema_20","ema_50","atr","rsi","macd_hist","adx"),
        "h4": ("close","ema_20","ema_50","rsi"),
        "m15": ("close","ema_20","ema_50","macd_hist","adx"),
        "m15p": ("close","ema_20"),
    }
    rows = {"h1": h1, "h4": h4, "m15": m15, "m15p": m15p}
    for name, required in keys.items():
        if any(_f(rows[name], key) is None for key in required):
            result["reason"] = f"long_{name}_indicator_unavailable"; return result

    hc, he20, he50, hatr, hrsi, hmacd, hadx = [_f(h1,k) for k in keys["h1"]]
    hpclose, hpema20 = _f(h1p,"close"), _f(h1p,"ema_20")
    hppclose, hppema20 = _f(h1pp,"close"), _f(h1pp,"ema_20")
    h4close, h4ema20, h4ema50, h4rsi = [_f(h4,k) for k in keys["h4"]]
    mc, me20, me50, mmacd, madx = [_f(m15,k) for k in keys["m15"]]
    mpc, mpema20 = [_f(m15p,k) for k in keys["m15p"]]

    checks = {
        "4h_bullish_structure": h4ema20 >= h4ema50 and h4close >= h4ema50,
        "4h_not_overbought": h4rsi <= rsi_4h_ceiling,
        "1h_bullish_structure": he20 > he50 and hc >= he50,
        "1h_trend_strength": hadx >= min_adx_1h,
        "1h_rsi_pullback_zone": rsi_floor <= hrsi <= rsi_ceiling,
        "1h_momentum_positive": hmacd > 0.0,
        "1h_reclaim_ema20": (hppclose <= hppema20 and hpclose > hpema20) or (hpclose <= he20 and hc > he20),
        "1h_not_chasing": hc <= he20 + max_atr_distance * hatr,
        "15m_bullish_structure": me20 >= me50 and mc >= me20,
        "15m_trend_strength": madx >= min_adx_15m,
        "15m_reclaim_or_momentum": (mpc <= mpema20 and mc > me20) or mmacd > 0.0,
    }
    core = all(checks.values())
    live_ok = live_price > 0 and live_price <= he20 + max_atr_distance * hatr
    checks["live_not_chasing"] = live_ok
    result.update({
        "valid": bool(core and live_ok),
        "reason": None if core and live_ok else "long_setup_conditions_not_met",
        "checks": checks,
        "metrics": {
            "rsi_1h": hrsi, "rsi_4h": h4rsi, "adx_1h": hadx, "adx_15m": madx, "atr_1h": hatr,
            "ema20_1h": he20, "ema50_1h": he50,
            "macd_hist_1h": hmacd, "macd_hist_15m": mmacd,
            "live_price": float(live_price),
        },
    })
    return result
