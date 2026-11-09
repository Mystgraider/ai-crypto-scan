"""Probe historical replay's 15m candle and indicator path at one fixed boundary."""
from __future__ import annotations

import json
import os
import sys
from datetime import timedelta

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engines.multiframe_engine import MultiFrameEngine
from indicators.indicators import Indicators
from tools.historical_replay import (
    DATA_SYMBOLS,
    OFFSET_DAYS,
    WARMUP_HOURS,
    load_store,
    ReplayMarketLoader,
    SYMBOLS,
)


def main() -> None:
    now = pd.Timestamp.now(tz="UTC")
    replay_end = now.floor("h") - pd.Timedelta(
        days=OFFSET_DAYS,
        hours=72 + 120 + 1,
    )
    replay_start = replay_end - pd.Timedelta(days=1)
    store = load_store(replay_start, replay_end)
    store.end = replay_start
    loader = ReplayMarketLoader(store)
    mtf = MultiFrameEngine()
    report = {
        "offset_days": OFFSET_DAYS,
        "probe_boundary": replay_start.isoformat(),
        "symbols": {},
    }
    failures = []

    for symbol in SYMBOLS:
        try:
            raw = loader.get_15m(symbol)
            if raw is None or len(raw) < Indicators.MIN_CANDLES:
                raise RuntimeError(
                    f"insufficient_15m_rows:{0 if raw is None else len(raw)}"
                )
            prepared = Indicators.apply(raw)
            if len(prepared) < 2:
                raise RuntimeError(f"insufficient_prepared_15m_rows:{len(prepared)}")
            previous = prepared.iloc[-2]
            required = ("ema_20", "ema_50", "adx", "rsi")
            missing = [name for name in required if pd.isna(previous.get(name))]
            if missing:
                raise RuntimeError(f"missing_completed_15m_indicators:{missing}")
            trend = mtf.analyze_15m(prepared)
            if trend.get("direction") not in {"BULLISH", "BEARISH", "NEUTRAL"}:
                raise RuntimeError(f"invalid_15m_direction:{trend}")
            report["symbols"][symbol] = {
                "raw_rows": len(raw),
                "prepared_rows": len(prepared),
                "last_closed_15m": str(previous["timestamp"]),
                "rsi_15m": round(float(previous["rsi"]), 4),
                "adx_15m": round(float(previous["adx"]), 4),
                "ema20_15m": round(float(previous["ema_20"]), 10),
                "ema50_15m": round(float(previous["ema_50"]), 10),
                "mtf_15m": trend["direction"],
            }
        except Exception as exc:
            failures.append({"symbol": symbol, "error": f"{type(exc).__name__}:{exc}"})
            report["symbols"][symbol] = {"error": f"{type(exc).__name__}:{exc}"}

    report["failures"] = failures
    report["passed"] = not failures and len(report["symbols"]) == len(SYMBOLS)
    print(json.dumps(report, indent=2, default=str))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
