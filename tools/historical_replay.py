"""Deterministic historical replay of the production scanner.

This harness reuses scanner_v5.main() and injects historical OHLCV/funding/OI
snapshots. It does not modify production code or write to production signals.

Replay semantics:
- Each evaluation timestamp is the CLOSE of a completed 1H candle.
- All timeframes are truncated at that timestamp.
- scanner_v5 still uses its production indicator convention: current close +
  previous completed-candle indicators.
- Live ticker validation is replaced by the historical 1H close.
- Funding/OI are historical observations at/before the replay timestamp.
- Telegram, cooldown, circuit breaker, tracker, and persistent signal logging
  are disabled/captured.
- Future candles are used only after a candidate's replay timestamp to score
  TP/SL outcome.
- If one future candle spans SL and a TP, SL wins, matching SignalTracker's
  documented conservative ordering.

This is intentionally an isolated research harness. It must never be imported
by production scanner_v5.py.
"""

from __future__ import annotations

import csv
import json
import math
import os
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / "backtest_results.json"
BINANCE = "https://fapi.binance.com/fapi/v1"
BINANCE_DATA = "https://fapi.binance.com/futures/data"

SYMBOLS = [
    "ETH/USDT:USDT",
    "SOL/USDT:USDT",
    "BNB/USDT:USDT",
    "XRP/USDT:USDT",
    "LTC/USDT:USDT",
    "LINK/USDT:USDT",
    "AVAX/USDT:USDT",
    "SUI/USDT:USDT",
]

INTERVALS = {"1h": "1h", "4h": "4h", "15m": "15m", "5m": "5m"}
DAYS = int(os.getenv("BACKTEST_DAYS", "7"))
WARMUP_HOURS = 120


def symbol_to_binance(symbol: str) -> str:
    return symbol.split("/")[0]


def http_json(url: str, params: dict) -> list | dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url + "?" + query,
        headers={"User-Agent": "ai-crypto-scan-backtest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = []
    cursor = start_ms
    while cursor < end_ms:
        batch = http_json(
            BINANCE + "/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": end_ms,
                "limit": 1500,
            },
        )
        if not batch:
            break
        rows.extend(batch)
        last_open = int(batch[-1][0])
        next_cursor = last_open + 1
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        if len(batch) < 1500:
            break

    if not rows:
        raise RuntimeError(f"no_klines:{symbol}:{interval}")

    df = pd.DataFrame(
        [
            [r[0], r[1], r[2], r[3], r[4], r[5]]
            for r in rows
        ],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = http_json(
        BINANCE + "/fundingRate",
        {"symbol": symbol, "startTime": start_ms, "endTime": end_ms, "limit": 1000},
    )
    df = pd.DataFrame(rows or [])
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "fundingRate"])
    df["timestamp"] = pd.to_datetime(df["fundingTime"], unit="ms", utc=True)
    df["fundingRate"] = pd.to_numeric(df["fundingRate"], errors="coerce")
    return df[["timestamp", "fundingRate"]].dropna().sort_values("timestamp")


def fetch_oi(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    rows = http_json(
        BINANCE_DATA + "/openInterestHist",
        {
            "symbol": symbol,
            "period": "1h",
            "startTime": start_ms,
            "endTime": end_ms,
            "limit": 500,
        },
    )
    df = pd.DataFrame(rows or [])
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "sumOpenInterestValue"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    value_col = "sumOpenInterestValue"
    df[value_col] = pd.to_numeric(df[value_col], errors="coerce")
    return df[["timestamp", value_col]].dropna().sort_values("timestamp")


@dataclass
class HistoricalStore:
    candles: dict
    funding: dict
    oi: dict
    end: pd.Timestamp


class ReplayExchange:
    def __init__(self, store: HistoricalStore):
        self.store = store

    def fetch_ticker(self, symbol: str) -> dict:
        df = self.store.candles[(symbol, "1h")]
        row = df[df["timestamp"] <= self.store.end].iloc[-1]
        return {"last": float(row["close"])}

    def fetch_funding_rate(self, symbol: str) -> dict:
        df = self.store.funding.get(symbol)
        if df is None or df.empty:
            return {"fundingRate": None}
        past = df[df["timestamp"] <= self.store.end]
        if past.empty:
            return {"fundingRate": None}
        return {"fundingRate": float(past.iloc[-1]["fundingRate"])}

    def fetch_open_interest(self, symbol: str) -> dict:
        df = self.store.oi.get(symbol)
        if df is None or df.empty:
            return {}
        past = df[df["timestamp"] <= self.store.end]
        if past.empty:
            return {}
        return {"openInterestValue": float(past.iloc[-1]["sumOpenInterestValue"])}

    def fetch_open_interest_history(self, symbol: str, timeframe: str = "1h", limit: int = 2):
        df = self.store.oi.get(symbol)
        if df is None or df.empty:
            return []
        past = df[df["timestamp"] <= self.store.end].tail(limit)
        return [
            {
                "openInterestValue": float(row["sumOpenInterestValue"]),
                "timestamp": int(row["timestamp"].timestamp() * 1000),
            }
            for _, row in past.iterrows()
        ]


class ReplayMarketLoader:
    def __init__(self, store: HistoricalStore):
        self.store = store
        self.exchange = ReplayExchange(store)

    def _frame(self, symbol: str, timeframe: str, limit: int | None):
        df = self.store.candles[(symbol, timeframe)]
        df = df[df["timestamp"] <= self.store.end]
        if limit is not None:
            df = df.tail(int(limit))
        return df.copy(deep=True).reset_index(drop=True)

    def get_ohlcv(self, symbol: str, timeframe: str = None, limit: int = None):
        return self._frame(symbol, timeframe or "1h", limit)

    def get_1h(self, symbol: str, limit: int = None):
        return self._frame(symbol, "1h", limit)

    def get_4h(self, symbol: str, limit: int = None):
        return self._frame(symbol, "4h", limit)

    def get_15m(self, symbol: str, limit: int = None):
        return self._frame(symbol, "15m", limit)

    def get_5m(self, symbol: str, limit: int = None):
        return self._frame(symbol, "5m", limit)


class ReplayTopSymbols:
    def __init__(self, symbols):
        self.symbols = symbols

    def get_top_symbols(self):
        return list(self.symbols)


def historical_outcome(signal: dict, future_5m: pd.DataFrame, expiry_hours: int = 72) -> dict:
    direction = signal["direction"]
    entry = float(signal["entry"])
    sl = float(signal["sl"])
    tp1 = float(signal["tp1"])
    tp2 = float(signal["tp2"])
    tp3 = float(signal["tp3"])
    start = pd.Timestamp(signal["_replay_time"])
    end = start + pd.Timedelta(hours=expiry_hours)

    status = "OPEN"
    current_sl = sl
    milestones = []
    for _, candle in future_5m[
        (future_5m["timestamp"] > start) & (future_5m["timestamp"] <= end)
    ].iterrows():
        high = float(candle["high"])
        low = float(candle["low"])

        if direction == "LONG":
            if low <= current_sl:
                return {"status": "SL_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
            if status == "OPEN":
                if high >= tp3:
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if high >= tp2:
                    status = "OPEN_TP2"
                    current_sl = entry
                    milestones.append("TP2")
                    continue
                if high >= tp1:
                    status = "OPEN_TP1"
                    current_sl = entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if high >= tp3:
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if high >= tp2:
                    status = "OPEN_TP2"
                    milestones.append("TP2")
            elif status == "OPEN_TP2" and high >= tp3:
                return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
        else:
            if high >= current_sl:
                return {"status": "SL_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
            if status == "OPEN":
                if low <= tp3:
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if low <= tp2:
                    status = "OPEN_TP2"
                    current_sl = entry
                    milestones.append("TP2")
                    continue
                if low <= tp1:
                    status = "OPEN_TP1"
                    current_sl = entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if low <= tp3:
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if low <= tp2:
                    status = "OPEN_TP2"
                    milestones.append("TP2")
            elif status == "OPEN_TP2" and low <= tp3:
                return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}

    return {"status": "EXPIRED" if len(future_5m[(future_5m["timestamp"] > start) & (future_5m["timestamp"] <= end)]) else "OPEN"}


def load_store(start: pd.Timestamp, end: pd.Timestamp) -> HistoricalStore:
    fetch_start = start - pd.Timedelta(hours=WARMUP_HOURS)
    start_ms = int(fetch_start.timestamp() * 1000)
    end_ms = int((end + pd.Timedelta(hours=72)).timestamp() * 1000)
    candles = {}
    funding = {}
    oi = {}

    for symbol in SYMBOLS:
        base = symbol_to_binance(symbol)
        for key, interval in INTERVALS.items():
            print(f"Downloading {base} {interval}...")
            candles[(symbol, key)] = fetch_klines(base, interval, start_ms, end_ms)

        funding[symbol] = fetch_funding(base, start_ms, end_ms)
        oi[symbol] = fetch_oi(base, start_ms, end_ms)

    return HistoricalStore(candles=candles, funding=funding, oi=oi, end=end)


def summarize(rows: list[dict]) -> dict:
    resolved = [r for r in rows if r["outcome"] in {"TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT"}]
    tp = [r for r in resolved if r["outcome"].startswith("TP")]
    sl = [r for r in resolved if r["outcome"] == "SL_HIT"]
    by_rrce = {}
    for r in rows:
        bucket = r["rrce_status"]
        by_rrce.setdefault(bucket, {"signals": 0, "tp": 0, "sl": 0, "resolved": 0})
        by_rrce[bucket]["signals"] += 1
        if r["outcome"] in {"TP1_HIT", "TP2_HIT", "TP3_HIT"}:
            by_rrce[bucket]["tp"] += 1
            by_rrce[bucket]["resolved"] += 1
        elif r["outcome"] == "SL_HIT":
            by_rrce[bucket]["sl"] += 1
            by_rrce[bucket]["resolved"] += 1

    return {
        "signals": len(rows),
        "resolved": len(resolved),
        "tp": len(tp),
        "sl": len(sl),
        "tp_vs_sl_pct": round(100 * len(tp) / (len(tp) + len(sl)), 2) if tp or sl else None,
        "by_rrce_status": by_rrce,
    }


def run():
    import scanner_v5 as scanner

    now = pd.Timestamp.now(tz="UTC")
    end = now.floor("h") - pd.Timedelta(hours=1)
    start = end - pd.Timedelta(days=DAYS)

    print(f"Historical replay: {start} -> {end}")
    store = load_store(start, end)

    # Use timestamps for completed 1H candles only. The first 120 hours are
    # reserved for indicator warmup, so no early NaNs are treated as strategy
    # failures.
    timeline = store.candles[(SYMBOLS[0], "1h")]
    timeline = timeline[(timeline["timestamp"] >= start) & (timeline["timestamp"] <= end)]
    if timeline.empty:
        raise RuntimeError("empty_replay_timeline")

    original = {
        "MarketDataLoader": scanner.MarketDataLoader,
        "TopSymbolsLoader": scanner.TopSymbolsLoader,
        "is_on_cooldown": scanner.is_on_cooldown,
        "set_cooldown": scanner.set_cooldown,
        "send_telegram_alert": scanner.send_telegram_alert,
        "save_signal": scanner.save_signal,
        "circuit_check": scanner.circuit_check,
        "SignalTracker": scanner.SignalTracker,
        "AnalyticsEngine": scanner.AnalyticsEngine,
    }

    captured = []

    class ReplayAnalytics:
        def compute(self):
            # Confidence is diagnostic only. A neutral expanding-history WR
            # avoids leaking future outcomes into candidate generation.
            return {
                "total_signals": 0,
                "open": 0,
                "win_rate": 50.0,
                "profit_factor": 1.0,
            }

    class ReplayTracker:
        def run(self):
            return None

    try:
        scanner.is_on_cooldown = lambda symbol: False
        scanner.set_cooldown = lambda symbol: None
        scanner.send_telegram_alert = lambda message: None
        scanner.circuit_check = lambda: {
            "is_tripped": False,
            "losses_today": 0,
            "max_losses": 999,
        }
        scanner.SignalTracker = ReplayTracker
        scanner.AnalyticsEngine = ReplayAnalytics

        for i, row in enumerate(timeline.itertuples(index=False), start=1):
            replay_time = pd.Timestamp(row.timestamp)
            store.end = replay_time

            scanner.MarketDataLoader = lambda store=store: ReplayMarketLoader(store)
            scanner.TopSymbolsLoader = lambda: ReplayTopSymbols(SYMBOLS)

            def capture(**sig):
                sig["_replay_time"] = replay_time.isoformat()
                captured.append(sig)

            scanner.save_signal = capture

            print(f"\n=== replay {i}/{len(timeline)} @ {replay_time.isoformat()} ===")
            scanner.main()

    finally:
        for name, value in original.items():
            setattr(scanner, name, value)

    results = []
    for sig in captured:
        symbol = sig["symbol"]
        future = store.candles[(symbol, "5m")]
        outcome = historical_outcome(sig, future)
        results.append(
            {
                "replay_time": sig["_replay_time"],
                "symbol": symbol,
                "direction": sig["direction"],
                "score": sig.get("composite"),
                "grade": sig.get("grade"),
                "rr": sig.get("rr"),
                "rrce_status": sig.get("rrce_status", "NOT_RUN"),
                "rrce_failed_stage": sig.get("rrce_failed_stage", ""),
                "rrce_choch_confirmed": bool(sig.get("rrce_choch_confirmed")),
                "rrce_risk_contract": sig.get("rrce_risk_contract", "ATR_FALLBACK"),
                "entry": sig.get("entry"),
                "sl": sig.get("sl"),
                "tp1": sig.get("tp1"),
                "tp2": sig.get("tp2"),
                "tp3": sig.get("tp3"),
                "outcome": outcome["status"],
                "event_time": outcome.get("event_time"),
                "milestones": outcome.get("milestones", []),
            }
        )

    payload = {
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "start": start.isoformat(),
            "end": end.isoformat(),
            "days": DAYS,
            "symbols": SYMBOLS,
            "timeframes": list(INTERVALS),
            "lookahead_policy": "future candles begin strictly after replay timestamp",
            "same_candle_conflict_policy": "SL first, matching SignalTracker",
            "production_code_modified": False,
            "harness_mode": "scanner_v5.main historical injection",
        },
        "summary": summarize(results),
        "results": results,
    }
    RESULTS.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"RESULT_FILE={RESULTS}")


if __name__ == "__main__":
    run()
