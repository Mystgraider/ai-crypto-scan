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
from config import CONFIG


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
WARMUP_HOURS = CONFIG["ohlcv_4h_limit"] * 4 + 48
BINANCE = "https://fapi.binance.com/fapi/v1"

from ai.signal_ranker import AISignalRanker


class ReplayTelemetryRanker(AISignalRanker):
    """Observation-only wrapper around the production AISignalRanker."""

    TELEMETRY_FIELDS = (
        "trend_score",
        "quality_score",
        "rs_score",
        "funding_pct_raw",
        "stoch_k",
        "macd_hist",
        "bb_pct_b",
        "mtf_4h",
        "mtf_15m",
    )

    def __init__(self, telemetry_sink=None):
        self.telemetry_sink = telemetry_sink if telemetry_sink is not None else {}

    def rank(self, candidates):
        ranked = super().rank(candidates)
        for candidate in ranked:
            key = (candidate.get("symbol"), candidate.get("direction"))
            snapshot = {
                field: candidate.get(field)
                for field in self.TELEMETRY_FIELDS
            }
            snapshot["__composite"] = candidate.get("composite")
            self.telemetry_sink.setdefault(key, []).append(snapshot)
        return ranked


def merge_replay_telemetry(sig: dict, telemetry_sink: dict) -> None:
    """Merge captured in-memory fields without overriding saved fields."""
    key = (sig.get("symbol"), sig.get("direction"))
    snapshots = telemetry_sink.get(key, [])
    if not snapshots:
        return

    snapshot = snapshots.pop(0)
    saved_score = sig.get("score", sig.get("composite"))
    candidate_score = snapshot.get("__composite")
    if (
        saved_score is not None
        and candidate_score is not None
        and abs(float(saved_score) - float(candidate_score)) > 1e-9
    ):
        raise AssertionError(
            f"replay_telemetry_score_mismatch:{key}:"
            f"{saved_score}!={candidate_score}"
        )

    for field, value in snapshot.items():
        if field != "__composite":
            sig.setdefault(field, value)
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


def _month_range(start_ms: int, end_ms: int) -> list[pd.Timestamp]:
    """Return UTC month starts covering the requested inclusive time window."""
    start = pd.Timestamp(start_ms, unit="ms", tz="UTC").normalize().replace(day=1)
    end = pd.Timestamp(end_ms, unit="ms", tz="UTC").normalize().replace(day=1)
    return list(pd.date_range(start=start, end=end, freq="MS"))


def _funding_archive_timestamps(values: pd.Series) -> pd.Series:
    """Parse Binance funding archive timestamps in either epoch or datetime form."""
    numeric = pd.to_numeric(values, errors="coerce")
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns, UTC]")
    numeric_mask = numeric.notna()
    if numeric_mask.any():
        magnitude = numeric.loc[numeric_mask].abs().median()
        unit = "ns" if magnitude > 1e17 else ("us" if magnitude > 1e14 else "ms")
        parsed.loc[numeric_mask] = pd.to_datetime(
            numeric.loc[numeric_mask], unit=unit, utc=True, errors="coerce"
        )
    text_mask = ~numeric_mask
    if text_mask.any():
        parsed.loc[text_mask] = pd.to_datetime(
            values.loc[text_mask], utc=True, errors="coerce"
        )
    return parsed


def fetch_funding(symbol: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    """Load monthly funding archives and retain only observations in the requested window."""
    frames = []
    start = pd.to_datetime(start_ms, unit="ms", utc=True)
    end = pd.to_datetime(end_ms, unit="ms", utc=True)
    for month in _month_range(start_ms, end_ms):
        url = (
            f"{BINANCE_VISION}/monthly/fundingRate/{symbol}/"
            f"{symbol}-fundingRate-{month.strftime('%Y-%m')}.zip"
        )
        df = _download_archive_csv(url)
        if df is None or df.empty:
            continue
        time_col = next((c for c in ("calc_time", "fundingTime", "timestamp") if c in df.columns), None)
        rate_col = next((c for c in ("last_funding_rate", "fundingRate") if c in df.columns), None)
        if not time_col or not rate_col:
            continue
        out = df[[time_col, rate_col]].copy()
        out.columns = ["timestamp_raw", "fundingRate"]
        out["timestamp"] = _funding_archive_timestamps(out["timestamp_raw"])
        out["fundingRate"] = pd.to_numeric(out["fundingRate"], errors="coerce")
        out = out.dropna(subset=["timestamp", "fundingRate"])
        # Archives can include records outside a partial first/last month.
        # Keep the replay's exact requested window; ReplayExchange separately
        # enforces timestamp <= each evaluation time to prevent look-ahead.
        out = out[(out["timestamp"] >= start) & (out["timestamp"] <= end)]
        frames.append(out[["timestamp", "fundingRate"]])
    if not frames:
        return pd.DataFrame(columns=["timestamp", "fundingRate"])
    result = pd.concat(frames, ignore_index=True)
    return result.drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)


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

    def _forming_row(self, symbol: str, timeframe: str):
        """Reconstruct the forming candle using only information available at T.

        Binance Vision archive rows are complete candles. Therefore the archived
        row for an unfinished candle cannot be exposed directly: its high/low/
        close/volume contain information from after the replay cutoff.
        """
        end = self.store.end
        delta = INTERVAL_DELTAS[timeframe]
        start = end.floor(delta)
        raw = self.store.candles[(symbol, timeframe)]
        archived = raw[raw["timestamp"] == start]

        # At the exact candle open, only the open is known.
        if start == end:
            if archived.empty:
                return None
            o = float(archived.iloc[0]["open"])
            return {"timestamp": start, "open": o, "high": o, "low": o,
                    "close": o, "volume": 0.0}

        # Historical replay cutoffs are hourly, hence 5m-aligned.
        five = INTERVAL_DELTAS["5m"]
        if end != end.floor(five):
            raise AssertionError(f"replay_cutoff_not_5m_aligned:{end.isoformat()}")

        # A 4H candle can already be forming before T. Rebuild it from only
        # fully closed 5m candles; never use the archived final 4H H/L/C/V.
        m5 = self.store.candles.get((symbol, "5m"))
        if m5 is None:
            raise RuntimeError(f"cannot_reconstruct_forming_candle_no_5m:{symbol}:{timeframe}")
        seg = m5[(m5["timestamp"] >= start) & (m5["timestamp"] + five <= end)]

        if not archived.empty:
            o = float(archived.iloc[0]["open"])
        elif not seg.empty:
            o = float(seg.iloc[0]["open"])
        else:
            return None

        if seg.empty:
            return {"timestamp": start, "open": o, "high": o, "low": o,
                    "close": o, "volume": 0.0}

        return {
            "timestamp": start,
            "open": o,
            "high": max(o, float(seg["high"].max())),
            "low": min(o, float(seg["low"].min())),
            "close": float(seg.iloc[-1]["close"]),
            "volume": float(seg["volume"].sum()),
        }

    def _frame(self, symbol: str, timeframe: str, limit: int | None):
        """Return the production-visible, strictly causal candle state at T."""
        raw = self.store.candles[(symbol, timeframe)]
        delta = INTERVAL_DELTAS[timeframe]

        # Match MarketDataLoader defaults: every production timeframe is
        # fetched with a 100-candle window unless a caller explicitly asks
        # for a smaller window.
        default_limit = (
            CONFIG["ohlcv_4h_limit"]
            if timeframe == "4h"
            else CONFIG["ohlcv_limit"]
        )
        effective_limit = default_limit if limit is None else min(int(limit), default_limit)

        completed = raw[raw["timestamp"] + delta <= self.store.end]
        forming = self._forming_row(symbol, timeframe)
        if forming is not None:
            row = pd.DataFrame([forming], columns=list(raw.columns))
            completed = pd.concat([completed, row], ignore_index=True)

        return completed.tail(effective_limit).copy(deep=True).reset_index(drop=True)

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
    """Verify every replay-visible candle is causal and production-shaped."""
    loader = ReplayMarketLoader(store)
    end = store.end

    for (symbol, timeframe) in store.candles:
        delta = INTERVAL_DELTAS[timeframe]
        frame = loader._frame(symbol, timeframe, None)
        if frame.empty:
            continue

        ts = frame["timestamp"]
        if (ts > end).any():
            raise AssertionError(f"future_visible_candle:{symbol}:{timeframe}:{end.isoformat()}")
        if not ts.is_monotonic_increasing or ts.duplicated().any():
            raise AssertionError(f"unordered_replay_candles:{symbol}:{timeframe}")

        unfinished = frame[ts + delta > end]
        if len(unfinished) > 1:
            raise AssertionError(f"multiple_unfinished_candles:{symbol}:{timeframe}")
        if len(unfinished) == 1:
            row = unfinished.iloc[0]
            if row["timestamp"] != end.floor(delta) or row["timestamp"] != ts.iloc[-1]:
                raise AssertionError(f"misplaced_forming_candle:{symbol}:{timeframe}")
            if row["timestamp"] == end and not (
                row["high"] == row["open"] == row["low"] == row["close"]
                and row["volume"] == 0
            ):
                raise AssertionError(
                    f"forming_candle_exposes_future_ohlcv:{symbol}:{timeframe}:{end.isoformat()}"
                )
            if not (row["low"] <= min(row["open"], row["close"])
                    and row["high"] >= max(row["open"], row["close"])):
                raise AssertionError(f"inconsistent_forming_candle:{symbol}:{timeframe}")

        if len(frame) >= 2 and len(unfinished) == 1:
            if ts.iloc[-2] + delta != ts.iloc[-1]:
                raise AssertionError(
                    f"noncontiguous_replay_candles:{symbol}:{timeframe}:"
                    f"{ts.iloc[-2].isoformat()}->{ts.iloc[-1].isoformat()}"
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



class ReplayCooldown:
    """Simulate the production symbol cooldown using replay time, not wall-clock time."""

    def __init__(self, hours: float):
        self.cooldown = pd.Timedelta(hours=float(hours))
        self.now: pd.Timestamp | None = None
        self.expires: dict[str, pd.Timestamp] = {}

    def advance(self, now: pd.Timestamp) -> None:
        self.now = pd.Timestamp(now)

    def is_on_cooldown(self, symbol: str) -> bool:
        expiry = self.expires.get(symbol)
        return self.now is not None and expiry is not None and self.now < expiry

    def set_cooldown(self, symbol: str) -> None:
        if self.now is not None:
            self.expires[symbol] = self.now + self.cooldown


def _stop_outcome(milestones: list[str], event_time: str) -> dict:
    """Distinguish a full stop from a stop at entry after TP milestones."""
    if "TP2" in milestones:
        status = "BREAKEVEN_AFTER_TP2"
    elif "TP1" in milestones:
        status = "BREAKEVEN_AFTER_TP1"
    else:
        status = "SL_HIT"
    return {"status": status, "event_time": event_time, "milestones": list(milestones)}


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
                return _stop_outcome(milestones, candle["timestamp"].isoformat())
            if status == "OPEN":
                if high >= tp3:
                    milestones.extend(["TP1", "TP2"])
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if high >= tp2:
                    status = "OPEN_TP2"
                    current_sl = entry
                    milestones.extend(["TP1", "TP2"])
                    continue
                if high >= tp1:
                    status = "OPEN_TP1"
                    current_sl = entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if high >= tp3:
                    milestones.append("TP2")
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if high >= tp2:
                    status = "OPEN_TP2"
                    milestones.append("TP2")
            elif status == "OPEN_TP2" and high >= tp3:
                return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
        else:
            if high >= current_sl:
                return _stop_outcome(milestones, candle["timestamp"].isoformat())
            if status == "OPEN":
                if low <= tp3:
                    milestones.extend(["TP1", "TP2"])
                    return {"status": "TP3_HIT", "event_time": candle["timestamp"].isoformat(), "milestones": milestones}
                if low <= tp2:
                    status = "OPEN_TP2"
                    current_sl = entry
                    milestones.extend(["TP1", "TP2"])
                    continue
                if low <= tp1:
                    status = "OPEN_TP1"
                    current_sl = entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if low <= tp3:
                    milestones.append("TP2")
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
    resolved_statuses = {
        "TP1_HIT", "TP2_HIT", "TP3_HIT", "SL_HIT",
        "BREAKEVEN_AFTER_TP1", "BREAKEVEN_AFTER_TP2",
    }
    resolved = [r for r in rows if r["outcome"] in resolved_statuses]
    tp = [r for r in resolved if r["outcome"].startswith("TP")]
    sl = [r for r in resolved if r["outcome"] == "SL_HIT"]
    be1 = [r for r in resolved if r["outcome"] == "BREAKEVEN_AFTER_TP1"]
    be2 = [r for r in resolved if r["outcome"] == "BREAKEVEN_AFTER_TP2"]
    by_rrce = {}
    for r in rows:
        bucket = r["rrce_status"]
        by_rrce.setdefault(bucket, {
            "signals": 0, "tp": 0, "sl": 0,
            "breakeven_after_tp1": 0, "breakeven_after_tp2": 0,
            "resolved": 0,
        })
        stats = by_rrce[bucket]
        stats["signals"] += 1
        outcome = r["outcome"]
        if outcome in resolved_statuses:
            stats["resolved"] += 1
        if outcome.startswith("TP"):
            stats["tp"] += 1
        elif outcome == "SL_HIT":
            stats["sl"] += 1
        elif outcome == "BREAKEVEN_AFTER_TP1":
            stats["breakeven_after_tp1"] += 1
        elif outcome == "BREAKEVEN_AFTER_TP2":
            stats["breakeven_after_tp2"] += 1

    return {
        "signals": len(rows),
        "resolved": len(resolved),
        "tp": len(tp),
        "sl": len(sl),
        "breakeven_after_tp1": len(be1),
        "breakeven_after_tp2": len(be2),
        "breakeven_exits": len(be1) + len(be2),
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
    replay_telemetry = {}

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
        replay_cooldown = ReplayCooldown(CONFIG["signal_cooldown_hours"])
        scanner.is_on_cooldown = replay_cooldown.is_on_cooldown
        scanner.set_cooldown = replay_cooldown.set_cooldown
        scanner.send_telegram_alert = lambda message: None
        scanner.circuit_check = lambda: {
            "is_tripped": False,
            "losses_today": 0,
            "max_losses": 999,
        }
        scanner.SignalTracker = ReplayTracker
        scanner.AnalyticsEngine = ReplayAnalytics
        scanner.AISignalRanker = lambda: ReplayTelemetryRanker(replay_telemetry)

        for i, row in enumerate(timeline.itertuples(index=False), start=1):
            replay_time = pd.Timestamp(row.timestamp) + INTERVAL_DELTAS["1h"]
            replay_cooldown.advance(replay_time)
            store.end = replay_time
            assert_replay_boundary(store)

            scanner.MarketDataLoader = lambda store=store: ReplayMarketLoader(store)
            scanner.TopSymbolsLoader = lambda: ReplayTopSymbols(SYMBOLS)

            # Snapshots are valid for this cycle only: a candidate ranked but rejected
            # afterwards must not leak into a later cycle's signal for the same key.
            replay_telemetry.clear()

            def capture(**sig):
                sig["_replay_time"] = replay_time.isoformat()
                merge_replay_telemetry(sig, replay_telemetry)
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
                # Forensic feature telemetry only. These values are already
                # produced by scanner_v5 for each candidate; exporting them
                # here does not alter candidate generation, gating, ranking,
                # risk, or outcome scoring.
                "trend_score": sig.get("trend_score"),
                "quality_score": sig.get("quality_score"),
                "rs_score": sig.get("rs_score"),
                "rs_label": sig.get("rs_label"),
                "rsi": sig.get("rsi"),
                "adx": sig.get("adx"),
                "rel_volume": sig.get("rel_volume"),
                "stoch_k": sig.get("stoch_k"),
                "macd_hist": sig.get("macd_hist"),
                "bb_pct_b": sig.get("bb_pct_b"),
                "mtf_status": sig.get("mtf_status"),
                "mtf_4h": sig.get("mtf_4h"),
                "mtf_15m": sig.get("mtf_15m"),
                "btc_regime": sig.get("btc_regime"),
                "funding_pct_raw": sig.get("funding_pct_raw"),
                "oi_signal": sig.get("oi_signal"),
                "beta_label": sig.get("beta_label"),
                "rrce_engine_mode": sig.get("rrce_engine_mode", ""),
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
            "cooldown_policy": "production symbol cooldown simulated on replay timestamps",
            "cooldown_hours": CONFIG["signal_cooldown_hours"],
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
