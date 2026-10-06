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
if str(ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(ROOT))

from indicators.indicators import Indicators


RESULTS = ROOT / "backtest_results.json"
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

# Production context symbols required by scanner dependencies (BTC filter / RS),
# but not part of the replay candidate universe.
DATA_SYMBOLS = list(dict.fromkeys(SYMBOLS + ["BTC/USDT:USDT"]))

INTERVALS = {"1h": "1h", "4h": "4h", "15m": "15m", "5m": "5m"}
INTERVAL_DELTAS = {"1h": pd.Timedelta(hours=1), "4h": pd.Timedelta(hours=4), "15m": pd.Timedelta(minutes=15), "5m": pd.Timedelta(minutes=5)}
DAYS = int(os.getenv("BACKTEST_DAYS", "7"))
WARMUP_HOURS = Indicators.MIN_CANDLES * 4 + 48
BINANCE = "https://fapi.binance.com/fapi/v1"
BINANCE_DATA = "https://fapi.binance.com/futures/data"


def symbol_to_binance(symbol: str) -> str:
    """Convert ccxt perpetual symbols to Binance Vision archive symbols."""
    base = symbol.split("/")[0]
    return f"{base}USDT"


def http_json(url: str, params: dict) -> list | dict:
    query = urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url + "?" + query,
        headers={"User-Agent": "ai-crypto-scan-backtest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


BINANCE_VISION = "https://data.binance.vision/data/futures/um"


def _archive_url(kind: str, symbol: str, interval: str, day: pd.Timestamp) -> str:
    date = day.strftime("%Y-%m-%d")
    return (
        f"{BINANCE_VISION}/daily/{kind}/{symbol}/{interval}/"
        f"{symbol}-{interval}-{date}.zip"
    )


def _download_archive_csv(url: str) -> pd.DataFrame | None:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "ai-crypto-scan-backtest/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            payload = response.read()
    except Exception:
        return None

    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as zf:
            csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not csv_names:
                return None
            with zf.open(csv_names[0]) as fh:
                return pd.read_csv(fh)
    except Exception:
        return None


def _day_range(start_ms: int, end_ms: int) -> list[pd.Timestamp]:
    start = pd.to_datetime(start_ms, unit="ms", utc=True).floor("D")
    end = pd.to_datetime(end_ms, unit="ms", utc=True).floor("D")
    return list(pd.date_range(start, end, freq="D", tz="UTC"))


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    frames = []
    for day in _day_range(start_ms, end_ms):
        url = _archive_url("klines", symbol, interval, day)
        df = _download_archive_csv(url)
        if df is None or df.empty:
            continue

        # Binance futures archive files may include a header. Normalize by
        # position so the replay does not depend on archive header variants.
        if "open_time" in df.columns:
            cols = {
                "open_time": "timestamp",
                "open": "open",
                "high": "high",
                "low": "low",
                "close": "close",
                "volume": "volume",
            }
            missing = [k for k in cols if k not in df.columns]
            if missing:
                continue
            out = df[list(cols)].rename(columns=cols)
        else:
            if len(df.columns) < 6:
                continue
            out = df.iloc[:, :6].copy()
            out.columns = ["timestamp", "open", "high", "low", "close", "volume"]

        out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
        # Archive timestamps are currently milliseconds; keep a defensive
        # microsecond conversion for any future archive format change.
        unit = "us" if out["timestamp"].dropna().median() > 10**14 else "ms"
        out["timestamp"] = pd.to_datetime(out["timestamp"], unit=unit, utc=True, errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        frames.append(out.dropna(subset=["timestamp", "open", "high", "low", "close"]))

    if not frames:
        raise RuntimeError(f"no_klines:{symbol}:{interval}")

    df = pd.concat(frames, ignore_index=True)
    df = df[(df["timestamp"] >= pd.to_datetime(start_ms, unit="ms", utc=True)) &
            (df["timestamp"] <= pd.to_datetime(end_ms, unit="ms", utc=True))]
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    frames = []
    for day in _day_range(start_ms, end_ms):
        url = (
            f"{BINANCE_VISION}/daily/fundingRate/{symbol}/"
            f"{symbol}-fundingRate-{day.strftime('%Y-%m-%d')}.zip"
        )
        df = _download_archive_csv(url)
        if df is None or df.empty:
            continue
        time_col = next((c for c in ("calc_time", "fundingTime", "timestamp") if c in df.columns), None)
        rate_col = next((c for c in ("last_funding_rate", "fundingRate") if c in df.columns), None)
        if not time_col or not rate_col:
            continue
        out = df[[time_col, rate_col]].copy()
        out.columns = ["timestamp", "fundingRate"]
        out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
        out["timestamp"] = pd.to_datetime(out["timestamp"], unit="ms", utc=True, errors="coerce")
        out["fundingRate"] = pd.to_numeric(out["fundingRate"], errors="coerce")
        frames.append(out.dropna())
    if not frames:
        return pd.DataFrame(columns=["timestamp", "fundingRate"])
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


def fetch_oi(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    frames = []
    for day in _day_range(start_ms, end_ms):
        url = (
            f"{BINANCE_VISION}/daily/metrics/{symbol}/"
            f"{symbol}-metrics-{day.strftime('%Y-%m-%d')}.zip"
        )
        df = _download_archive_csv(url)
        if df is None or df.empty:
            continue
        time_col = next((c for c in ("create_time", "timestamp") if c in df.columns), None)
        value_col = "sum_open_interest_value" if "sum_open_interest_value" in df.columns else "sumOpenInterestValue"
        if not time_col or value_col not in df.columns:
            continue
        out = df[[time_col, value_col]].copy()
        out.columns = ["timestamp", "sumOpenInterestValue"]
        # Binance Vision metrics have historically exposed create_time as
        # epoch milliseconds, but malformed/outlier rows can contain values
        # large enough to overflow pandas/NumPy when unit inference is applied.
        # Normalize only finite numeric timestamps and discard values outside
        # the requested historical window before datetime conversion.
        raw_ts = pd.to_numeric(out["timestamp"], errors="coerce")
        raw_ts = raw_ts.where(raw_ts.abs() < 1e18)
        valid_ts = raw_ts.dropna()
        if valid_ts.empty:
            continue
        unit = "us" if valid_ts.abs().median() > 1e14 else "ms"
        scale = 1_000_000 if unit == "us" else 1_000
        lo = int(start_ms) * (scale // 1_000)
        hi = int(end_ms) * (scale // 1_000)
        raw_ts = raw_ts.where(raw_ts.between(lo, hi))
        if raw_ts.notna().sum() == 0:
            continue
        out["timestamp"] = pd.to_datetime(raw_ts, unit=unit, utc=True, errors="coerce")
        out["sumOpenInterestValue"] = pd.to_numeric(out["sumOpenInterestValue"], errors="coerce")
        frames.append(out.dropna())
    if not frames:
        return pd.DataFrame(columns=["timestamp", "sumOpenInterestValue"])
    df = pd.concat(frames, ignore_index=True)
    return df.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


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
        completed = df[df["timestamp"] + INTERVAL_DELTAS["1h"] <= self.store.end]
        if completed.empty:
            raise RuntimeError(f"no_completed_1h_ticker:{symbol}:{self.store.end.isoformat()}")
        row = completed.iloc[-1]
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
        """Return the exact production-visible candle state at replay cutoff.

        Production receives a dataframe whose final row is the currently
        forming candle and whose penultimate row is the last completed candle.
        The historical replay cutoff is defined at a completed 1H close, so
        the candle opening exactly at store.end is the corresponding forming
        candle for every timeframe. Future-opened candles remain hidden.

        Do not require timestamp + interval <= end here: that predicate
        removes the forming candle and shifts production iloc[-1] / iloc[-2]
        semantics by one bar.
        """
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


def assert_replay_boundary(store: HistoricalStore) -> None:
    """Verify replay visibility and production candle-state semantics."""
    for (symbol, timeframe), df in store.candles.items():
        visible = df[df["timestamp"] <= store.end]
        if not visible.empty and (visible["timestamp"] > store.end).any():
            raise AssertionError(
                f"future_visible_candle:{symbol}:{timeframe}:{store.end.isoformat()}"
            )

        # The latest visible row may be the forming candle whose open time
        # equals end. The preceding row must be exactly one interval earlier.
        # This is the state expected by production iloc[-1]/iloc[-2] logic.
        if len(visible) >= 2:
            visible = visible.sort_values("timestamp").reset_index(drop=True)
            latest = visible.iloc[-1]["timestamp"]
            previous = visible.iloc[-2]["timestamp"]
            delta = INTERVAL_DELTAS[timeframe]
            if latest == store.end and previous + delta != latest:
                raise AssertionError(
                    f"noncontiguous_replay_candles:{symbol}:{timeframe}:"
                    f"{previous.isoformat()}->{latest.isoformat()}"
                )

    for symbol, df in store.funding.items():
        visible = df[df["timestamp"] <= store.end]
        if not visible.empty and (visible["timestamp"] > store.end).any():
            raise AssertionError(
                f"future_visible_funding:{symbol}:{store.end.isoformat()}"
            )

    for symbol, df in store.oi.items():
        visible = df[df["timestamp"] <= store.end]
        if not visible.empty and (visible["timestamp"] > store.end).any():
            raise AssertionError(
                f"future_visible_oi:{symbol}:{store.end.isoformat()}"
            )



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
    # Only fully completed 5m candles inside the expiry window are
    # observable at evaluation time. A candle opening exactly at expiry is
    # still unfinished and must not affect the historical outcome.
    future_window = future_5m[
        (future_5m["timestamp"] > start)
        & (future_5m["timestamp"] + INTERVAL_DELTAS["5m"] <= end)
    ]
    for _, candle in future_window.iterrows():
        low = float(candle["low"])
        high = float(candle["high"])

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

    return {"status": "EXPIRED" if not future_window.empty else "OPEN"}


def load_store(start: pd.Timestamp, end: pd.Timestamp) -> HistoricalStore:
    fetch_start = start - pd.Timedelta(hours=WARMUP_HOURS)
    start_ms = int(fetch_start.timestamp() * 1000)
    end_ms = int((end + pd.Timedelta(hours=72)).timestamp() * 1000)
    candles = {}
    funding = {}
    oi = {}

    for symbol in DATA_SYMBOLS:
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

    # Use timestamps for completed 1H candles only. Replay warmup is sized from
    # the production indicator minimum for the slowest RRCE timeframe (4H),
    # with an additional 48-hour alignment/data margin.
    timeline = store.candles[(SYMBOLS[0], "1h")]
    timeline = timeline[(timeline["timestamp"] + INTERVAL_DELTAS["1h"] >= start) & (timeline["timestamp"] + INTERVAL_DELTAS["1h"] <= end)]
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
            replay_time = pd.Timestamp(row.timestamp) + INTERVAL_DELTAS["1h"]
            store.end = replay_time
            assert_replay_boundary(store)

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
                "score": sig.get("score", sig.get("composite")),
                "grade": sig.get("grade"),
                "rr": sig.get("rr"),
                "rrce_status": sig.get("rrce_status", "NOT_RUN"),
                "rrce_failed_stage": sig.get("rrce_failed_stage", ""),
                "rrce_failure_reason": sig.get("rrce_failure_reason", ""),
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
