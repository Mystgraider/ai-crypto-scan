"""Deterministic historical replay of the production scanner.

This harness reuses scanner_v5.main() and injects historical OHLCV/funding/OI
snapshots. It does not modify production code or write to production signals.

Replay semantics:
- Each evaluation timestamp is a 5-minute production scan boundary.
- All timeframes expose the in-progress candle visible at that exact boundary.
- scanner_v5 uses its production convention: forming-candle close/ticker price +
  previous completed-candle indicators.
- The forming candle is reconstructed only from completed 5m candles and the
  next 5m candle OPEN; its future high/low/close/volume are never used.
- Live ticker validation is replaced by that boundary 5m open price.
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
DAYS = int(os.getenv("BACKTEST_DAYS", "30"))
OFFSET_DAYS = int(os.getenv("BACKTEST_OFFSET_DAYS", "90"))
# Binance Vision daily futures archives can lag recent candles. REST fallback
# may be geo-restricted in CI, so keep the replay window behind a fixed archive
# publication buffer and fail closed if any remaining gaps cannot be recovered.
ARCHIVE_LAG_HOURS = int(os.getenv("BACKTEST_ARCHIVE_LAG_HOURS", "120"))
OUTCOME_LOOKAHEAD_HOURS = 72
# 300h provides 75 completed 4H candles for indicator warmup.
WARMUP_HOURS = 300
BINANCE = "https://fapi.binance.com/fapi/v1"
BINANCE_DATA = "https://fapi.binance.com/futures/data"


def symbol_to_binance(symbol: str) -> str:
    """Convert ccxt perpetual symbols to Binance Vision archive symbols."""
    base = symbol.split("/")[0]
    return f"{base}USDT"


def http_json(url: str, params: dict) -> list | dict:
    query = urllib.parse.urlencode(params)
    request_url = url + "?" + query
    last_error = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(
                request_url,
                headers={"User-Agent": "ai-crypto-scan-backtest/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            last_error = exc
            # Do not retry permanent client errors such as invalid parameters.
            code = getattr(exc, "code", None)
            if code is not None and 400 <= code < 500 and code != 429:
                raise
            if attempt < 3:
                time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"binance_rest_request_failed:{url}:{last_error}") from last_error


BINANCE_VISION = "https://data.binance.vision/data/futures/um"


def _archive_url(kind: str, symbol: str, interval: str, day: pd.Timestamp) -> str:
    date = day.strftime("%Y-%m-%d")
    return (
        f"{BINANCE_VISION}/daily/{kind}/{symbol}/{interval}/"
        f"{symbol}-{interval}-{date}.zip"
    )


def _download_archive_csv(url: str) -> pd.DataFrame | None:
    import io
    import zipfile

    last_error = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "ai-crypto-scan-backtest/1.0"},
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                payload = response.read()
            with zipfile.ZipFile(io.BytesIO(payload)) as zf:
                csv_names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
                if not csv_names:
                    raise ValueError("archive_contains_no_csv")
                with zf.open(csv_names[0]) as fh:
                    return pd.read_csv(fh)
        except Exception as exc:
            last_error = exc
            code = getattr(exc, "code", None)
            if code == 404:
                return None
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    print(f"ARCHIVE_DOWNLOAD_FAILED url={url} error={last_error}")
    return None


def _day_range(start_ms: int, end_ms: int) -> list[pd.Timestamp]:
    start = pd.to_datetime(start_ms, unit="ms", utc=True).floor("D")
    end = pd.to_datetime(end_ms, unit="ms", utc=True).floor("D")
    return list(pd.date_range(start, end, freq="D", tz="UTC"))


def _normalize_kline_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize Binance Vision CSV and REST kline rows to one OHLCV schema."""
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    if "open_time" in df.columns:
        mapping = {
            "open_time": "timestamp",
            "open": "open",
            "high": "high",
            "low": "low",
            "close": "close",
            "volume": "volume",
        }
        if any(name not in df.columns for name in mapping):
            return pd.DataFrame(columns=columns)
        out = df[list(mapping)].rename(columns=mapping).copy()
    elif len(df.columns) >= 6:
        out = df.iloc[:, :6].copy()
        out.columns = columns
    else:
        return pd.DataFrame(columns=columns)

    out["timestamp"] = pd.to_numeric(out["timestamp"], errors="coerce")
    valid = out["timestamp"].dropna()
    if valid.empty:
        return pd.DataFrame(columns=columns)
    unit = "us" if valid.median() > 10**14 else "ms"
    out["timestamp"] = pd.to_datetime(out["timestamp"], unit=unit, utc=True, errors="coerce")
    for name in ["open", "high", "low", "close", "volume"]:
        out[name] = pd.to_numeric(out[name], errors="coerce")
    return out.dropna(subset=["timestamp", "open", "high", "low", "close"])


def _fetch_klines_rest(
    symbol: str, interval: str, start_ms: int, end_ms: int
) -> pd.DataFrame:
    """Fetch a missing candle range from Binance Futures REST with pagination."""
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    interval_ms = int(INTERVAL_DELTAS[interval].total_seconds() * 1000)
    cursor = int(start_ms)
    frames = []
    while cursor <= end_ms:
        rows = http_json(
            f"{BINANCE}/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "startTime": cursor,
                "endTime": int(end_ms),
                "limit": 1500,
            },
        )
        if not isinstance(rows, list) or not rows:
            break
        raw = pd.DataFrame(
            [row[:6] for row in rows],
            columns=columns,
        )
        frames.append(_normalize_kline_frame(raw))
        last_open = int(rows[-1][0])
        next_cursor = last_open + interval_ms
        if next_cursor <= cursor:
            raise RuntimeError(
                f"binance_rest_pagination_stalled:{symbol}:{interval}:{cursor}"
            )
        cursor = next_cursor
        if len(rows) < 1500:
            break
        time.sleep(0.08)

    if not frames:
        return pd.DataFrame(columns=columns)
    return (
        pd.concat(frames, ignore_index=True)
        .drop_duplicates("timestamp")
        .sort_values("timestamp")
        .reset_index(drop=True)
    )


def fetch_klines(symbol: str, interval: str, start_ms: int, end_ms: int) -> pd.DataFrame:
    columns = ["timestamp", "open", "high", "low", "close", "volume"]
    frames = []
    for day in _day_range(start_ms, end_ms):
        url = _archive_url("klines", symbol, interval, day)
        normalized = _normalize_kline_frame(_download_archive_csv(url))
        if not normalized.empty:
            frames.append(normalized)

    candles = (
        pd.concat(frames, ignore_index=True)
        if frames else pd.DataFrame(columns=columns)
    )
    start = pd.to_datetime(start_ms, unit="ms", utc=True)
    interval_ms = int(INTERVAL_DELTAS[interval].total_seconds() * 1000)
    # end_ms is the end boundary. Only require candles fully closed by it.
    last_open_ms = ((int(end_ms) - interval_ms) // interval_ms) * interval_ms
    end = pd.to_datetime(last_open_ms, unit="ms", utc=True)
    candles = candles[
        (candles["timestamp"] >= start) & (candles["timestamp"] <= end)
    ].drop_duplicates("timestamp").sort_values("timestamp").reset_index(drop=True)

    first_open_ms = ((int(start_ms) + interval_ms - 1) // interval_ms) * interval_ms
    expected_ms = range(first_open_ms, last_open_ms + 1, interval_ms)
    observed_ms = set((candles["timestamp"].astype("int64") // 1_000_000).tolist())
    missing_ms = [stamp for stamp in expected_ms if stamp not in observed_ms]

    if missing_ms:
        print(
            f"KLINE_ARCHIVE_GAP symbol={symbol} interval={interval} "
            f"missing={len(missing_ms)} "
            f"first={pd.to_datetime(missing_ms[0], unit='ms', utc=True).isoformat()} "
            f"last={pd.to_datetime(missing_ms[-1], unit='ms', utc=True).isoformat()}; "
            f"requesting Binance REST fallback"
        )
        ranges = []
        range_start = previous = missing_ms[0]
        for stamp in missing_ms[1:]:
            if stamp != previous + interval_ms:
                ranges.append((range_start, previous))
                range_start = stamp
            previous = stamp
        ranges.append((range_start, previous))

        recovered = [
            _fetch_klines_rest(symbol, interval, gap_start, gap_end)
            for gap_start, gap_end in ranges
        ]
        recovered = [frame for frame in recovered if not frame.empty]
        if recovered:
            candles = pd.concat([candles, *recovered], ignore_index=True)
            candles = (
                candles.drop_duplicates("timestamp")
                .sort_values("timestamp")
                .reset_index(drop=True)
            )

    observed_ms = set((candles["timestamp"].astype("int64") // 1_000_000).tolist())
    remaining = [
        stamp for stamp in range(first_open_ms, last_open_ms + 1, interval_ms)
        if stamp not in observed_ms
    ]
    if remaining:
        first_missing = pd.to_datetime(remaining[0], unit="ms", utc=True).isoformat()
        raise RuntimeError(
            f"incomplete_kline_coverage:{symbol}:{interval}:"
            f"missing={len(remaining)}:first_missing={first_missing}"
        )
    return candles


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


def replay_boundary_price(store: HistoricalStore, symbol: str) -> float:
    """Return the first traded price at the replay boundary without scanning the full 5m frame."""
    five_min = store.candles[(symbol, "5m")]
    timestamps = five_min["timestamp"]
    position = int(timestamps.searchsorted(pd.Timestamp(store.end), side="left"))
    if position >= len(five_min) or timestamps.iloc[position] != pd.Timestamp(store.end):
        raise RuntimeError(
            f"missing_5m_boundary_price:{symbol}:{store.end.isoformat()}"
        )
    return float(five_min.iloc[position]["open"])
def replay_forming_candle(
    store: HistoricalStore, symbol: str, timeframe: str
) -> dict:
    """Build the in-progress exchange candle visible at the exact scan boundary.

    Only fully closed 5m candles before the boundary and the next 5m candle's
    OPEN are used. The next 5m candle's high/low/close/volume are never read.
    """
    if timeframe not in {"1h", "4h", "15m"}:
        raise ValueError(f"unsupported_forming_timeframe:{timeframe}")

    end = pd.Timestamp(store.end)
    floor_frequency = {"1h": "1h", "4h": "4h", "15m": "15min"}[timeframe]
    bucket_start = end.floor(floor_frequency)
    five_min = store.candles[(symbol, "5m")]
    timestamps = five_min["timestamp"]
    left = int(timestamps.searchsorted(bucket_start, side="left"))
    right = int(timestamps.searchsorted(end, side="left"))
    completed = five_min.iloc[left:right]
    boundary_price = replay_boundary_price(store, symbol)

    if completed.empty:
        opening = boundary_price
        high = boundary_price
        low = boundary_price
        volume = 0.0
    else:
        opening = float(completed.iloc[0]["open"])
        high = max(float(completed["high"].max()), boundary_price)
        low = min(float(completed["low"].min()), boundary_price)
        volume = float(completed["volume"].sum())

    return {
        "timestamp": bucket_start,
        "open": opening,
        "high": high,
        "low": low,
        "close": boundary_price,
        "volume": volume,
    }


class ReplayExchange:
    def __init__(self, store: HistoricalStore):
        self.store = store

    def fetch_ticker(self, symbol: str) -> dict:
        return {"last": replay_boundary_price(self.store, symbol)}

    def fetch_funding_rate(self, symbol: str) -> dict:
        df = self.store.funding.get(symbol)
        if df is None or df.empty:
            return {"fundingRate": None}
        position = int(df["timestamp"].searchsorted(pd.Timestamp(self.store.end), side="right")) - 1
        if position < 0:
            return {"fundingRate": None}
        return {"fundingRate": float(df.iloc[position]["fundingRate"])}

    def fetch_open_interest(self, symbol: str) -> dict:
        df = self.store.oi.get(symbol)
        if df is None or df.empty:
            return {}
        position = int(df["timestamp"].searchsorted(pd.Timestamp(self.store.end), side="right")) - 1
        if position < 0:
            return {}
        return {"openInterestValue": float(df.iloc[position]["sumOpenInterestValue"])}

    def fetch_open_interest_history(self, symbol: str, timeframe: str = "1h", limit: int = 2):
        df = self.store.oi.get(symbol)
        if df is None or df.empty:
            return []
        right = int(df["timestamp"].searchsorted(pd.Timestamp(self.store.end), side="right"))
        left = max(0, right - int(limit))
        past = df.iloc[left:right]
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
        effective_limit = (
            CONFIG["ohlcv_4h_limit"]
            if timeframe == "4h" and limit is None
            else CONFIG["ohlcv_limit"]
            if limit is None
            else int(limit)
        )
        cutoff = pd.Timestamp(self.store.end) - INTERVAL_DELTAS[timeframe]
        right = int(df["timestamp"].searchsorted(cutoff, side="right"))

        # Match MarketDataLoader's production contract: its default OHLCV limit
        # is 100, and the exchange response contains the currently forming bar.
        # Therefore reserve one slot for the replay-constructed forming candle.
        if timeframe in {"1h", "4h", "15m"}:
            completed_limit = max(0, effective_limit - 1)
            start = max(0, right - completed_limit)
            visible = df.iloc[start:right].copy()
            forming = replay_forming_candle(self.store, symbol, timeframe)
            visible = pd.concat([visible, pd.DataFrame([forming])], ignore_index=True)
            visible = visible.drop_duplicates("timestamp", keep="last").sort_values("timestamp")
        else:
            start = max(0, right - effective_limit)
            visible = df.iloc[start:right].copy()

        return visible.reset_index(drop=True)

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
    """Perform a constant-work boundary check.

    Full historical coverage is validated before replay starts. During the
    8,640-point loop we only need to prove that the current production 5m
    boundary exists for every candidate symbol.
    """
    end = pd.Timestamp(store.end)
    for symbol in SYMBOLS:
        five_min = store.candles.get((symbol, "5m"))
        if five_min is None or five_min.empty:
            raise AssertionError(f"missing_5m_store:{symbol}")
        timestamps = five_min["timestamp"]
        position = int(timestamps.searchsorted(end, side="left"))
        if position >= len(five_min) or timestamps.iloc[position] != end:
            raise AssertionError(
                f"missing_5m_boundary:{symbol}:{end.isoformat()}"
            )


def validate_hourly_timeline(
    timeline: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict:
    """Fail closed unless every expected hourly evaluation timestamp exists."""
    expected = pd.date_range(start=start, end=end, freq="1h", tz="UTC")
    observed = pd.DatetimeIndex(
        pd.to_datetime(timeline["timestamp"], utc=True) + INTERVAL_DELTAS["1h"]
    ).drop_duplicates().sort_values()
    missing = expected.difference(observed)
    unexpected = observed.difference(expected)
    report = {
        "expected_hours": int(len(expected)),
        "observed_hours": int(len(observed)),
        "missing_hours": int(len(missing)),
        "unexpected_hours": int(len(unexpected)),
        "first_missing": missing[0].isoformat() if len(missing) else None,
        "missing_examples": [value.isoformat() for value in missing[:10]],
    }
    if len(missing) or len(unexpected):
        raise RuntimeError(
            "incomplete_hourly_replay_timeline:"
            + json.dumps(report, sort_keys=True)
        )
    return report


def validate_five_minute_timeline(
    timeline: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp
) -> dict:
    """Fail closed unless every production 5-minute scan boundary exists."""
    delta = INTERVAL_DELTAS["5m"]
    expected = pd.date_range(start=start, end=end - delta, freq=delta, tz="UTC")
    observed = pd.DatetimeIndex(
        pd.to_datetime(timeline["timestamp"], utc=True)
    ).drop_duplicates().sort_values()
    missing = expected.difference(observed)
    unexpected = observed.difference(expected)
    report = {
        "expected_scans": int(len(expected)),
        "observed_scans": int(len(observed)),
        "missing_scans": int(len(missing)),
        "unexpected_scans": int(len(unexpected)),
        "first_missing": missing[0].isoformat() if len(missing) else None,
        "missing_examples": [value.isoformat() for value in missing[:10]],
        "scan_interval": "5m",
    }
    if len(missing) or len(unexpected):
        raise RuntimeError(
            "incomplete_five_minute_replay_timeline:"
            + json.dumps(report, sort_keys=True)
        )
    return report


def historical_outcome(signal: dict, future_5m: pd.DataFrame, expiry_hours: int = 72) -> dict:
    """Score only contiguous, fully observed 5m candles in the full expiry window.

    A TP/SL reached before a later data gap is valid. If a gap occurs before
    any terminal event, the outcome is INCOMPLETE_DATA, never EXPIRED.
    """
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
    delta = INTERVAL_DELTAS["5m"]
    # The first 5m candle opening exactly at the signal timestamp is the
    # first tradable candle after an entry made at the 1H close. Include it.
    expected_opens = pd.date_range(
        start=start,
        end=end - delta,
        freq=delta,
        tz="UTC",
    )
    window = future_5m[
        (future_5m["timestamp"] >= start)
        & (future_5m["timestamp"] + delta <= end)
    ].drop_duplicates("timestamp").set_index("timestamp")
    missing = [timestamp for timestamp in expected_opens if timestamp not in window.index]

    for timestamp in expected_opens:
        if timestamp not in window.index:
            return {
                "status": "INCOMPLETE_DATA",
                "missing_candles": len(missing),
                "expected_candles": len(expected_opens),
                "first_missing": timestamp.isoformat(),
                "milestones": milestones,
            }
        candle = window.loc[timestamp]
        low = float(candle["low"])
        high = float(candle["high"])

        if direction == "LONG":
            if low <= current_sl:
                return {"status": "SL_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
            if status == "OPEN":
                if high >= tp3:
                    return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
                if high >= tp2:
                    status, current_sl = "OPEN_TP2", entry
                    milestones.append("TP2")
                    continue
                if high >= tp1:
                    status, current_sl = "OPEN_TP1", entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if high >= tp3:
                    return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
                if high >= tp2:
                    status = "OPEN_TP2"
                    milestones.append("TP2")
            elif status == "OPEN_TP2" and high >= tp3:
                return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
        else:
            if high >= current_sl:
                return {"status": "SL_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
            if status == "OPEN":
                if low <= tp3:
                    return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
                if low <= tp2:
                    status, current_sl = "OPEN_TP2", entry
                    milestones.append("TP2")
                    continue
                if low <= tp1:
                    status, current_sl = "OPEN_TP1", entry
                    milestones.append("TP1")
                    continue
            elif status == "OPEN_TP1":
                if low <= tp3:
                    return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}
                if low <= tp2:
                    status = "OPEN_TP2"
                    milestones.append("TP2")
            elif status == "OPEN_TP2" and low <= tp3:
                return {"status": "TP3_HIT", "event_time": timestamp.isoformat(), "milestones": milestones}

    return {
        "status": "EXPIRED",
        "expected_candles": len(expected_opens),
        "observed_candles": len(expected_opens),
        "milestones": milestones,
    }

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

    anchor_raw = os.getenv("BACKTEST_ANCHOR_UTC")
    if anchor_raw:
        try:
            anchor = pd.Timestamp(anchor_raw)
            if anchor.tzinfo is None:
                anchor = anchor.tz_localize("UTC")
            else:
                anchor = anchor.tz_convert("UTC")
        except Exception as exc:
            raise RuntimeError(f"invalid_backtest_anchor_utc:{anchor_raw}") from exc
    else:
        anchor = pd.Timestamp.now(tz="UTC")

    # Use one explicit anchor for all chunks. Without this, independently
    # scheduled matrix jobs compute now at different wall-clock times,
    # producing non-contiguous 10-day windows even when offsets differ by 10d.
    end = anchor.floor("h") - pd.Timedelta(
        days=OFFSET_DAYS,
        hours=OUTCOME_LOOKAHEAD_HOURS + ARCHIVE_LAG_HOURS + 1,
    )
    start = end - pd.Timedelta(days=DAYS)

    print(f"Historical replay: {start} -> {end}")
    store = load_store(start, end)

    # Production scanner.yml runs every five minutes. Replaying only hourly
    # closes would omit 11 of every 12 production scan opportunities and can
    # materially distort signal selection, indicator state, and outcome mix.
    timeline = store.candles[(SYMBOLS[0], "5m")]
    timeline = timeline[
        (timeline["timestamp"] >= start)
        & (timeline["timestamp"] < end)
    ].copy()
    if timeline.empty:
        raise RuntimeError("empty_replay_timeline")

    # Validate every production scan boundary for every replay symbol. A
    # missing 5m candle must stop the replay rather than silently skip a scan.
    timeline_coverage = validate_five_minute_timeline(timeline, start, end)
    for symbol in SYMBOLS:
        symbol_timeline = store.candles[(symbol, "5m")]
        symbol_timeline = symbol_timeline[
            (symbol_timeline["timestamp"] >= start)
            & (symbol_timeline["timestamp"] < end)
        ]
        try:
            validate_five_minute_timeline(symbol_timeline, start, end)
        except RuntimeError as exc:
            raise RuntimeError(f"symbol_five_minute_coverage_failed:{symbol}:{exc}") from exc

    original_long_signals_enabled = os.environ.get("LONG_SIGNALS_ENABLED")
    os.environ["LONG_SIGNALS_ENABLED"] = "false"

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
            assert_replay_boundary(store)

            scanner.MarketDataLoader = lambda store=store: ReplayMarketLoader(store)
            scanner.TopSymbolsLoader = lambda: ReplayTopSymbols(SYMBOLS)
            # Diagnostic-only RRCE shadow replays are disabled for the long replay.
            # They never change candidate gating or captured signals. Production
            # defaults are untouched; this flag is scoped to this research run.
            scanner.CONFIG["_historical_replay_fast_mode"] = True

            def capture(**sig):
                sig["_replay_time"] = replay_time.isoformat()
                captured.append(sig)

            scanner.save_signal = capture

            print(f"\n=== replay {i}/{len(timeline)} @ {replay_time.isoformat()} ===")
            scanner.main()

    finally:
        for name, value in original.items():
            setattr(scanner, name, value)
        scanner.CONFIG.pop("_historical_replay_fast_mode", None)
        if original_long_signals_enabled is None:
            os.environ.pop("LONG_SIGNALS_ENABLED", None)
        else:
            os.environ["LONG_SIGNALS_ENABLED"] = original_long_signals_enabled

    results = []
    for sig in captured:
        symbol = sig["symbol"]
        future = store.candles[(symbol, "5m")]
        outcome = historical_outcome(sig, future)

        # Research-only EMA200: calculate from completed 1H closes available
        # at this signal timestamp. The 200-period EMA never sees future bars.
        signal_time = pd.Timestamp(sig["_replay_time"])
        one_hour = store.candles[(symbol, "1h")]
        completed_1h = one_hour[
            one_hour["timestamp"] + INTERVAL_DELTAS["1h"] <= signal_time
        ]
        close_series = completed_1h["close"].astype(float)
        ema200_1h = (
            float(close_series.ewm(span=200, adjust=False, min_periods=200).mean().iloc[-1])
            if len(close_series) >= 200 else None
        )
        signal_close_1h = float(close_series.iloc[-1]) if not close_series.empty else None
        ema200_distance_pct = (
            round((signal_close_1h / ema200_1h - 1.0) * 100, 4)
            if ema200_1h not in (None, 0) and signal_close_1h is not None else None
        )
        results.append(
            {
                "replay_time": sig["_replay_time"],
                "symbol": symbol,
                "direction": sig["direction"],
                # Signal-time values from the same completed 1H indicator row
                # used by production scanner candidate generation.
                "rsi": sig.get("rsi"),
                "adx": sig.get("adx"),
                "plus_di": sig.get("plus_di"),
                "minus_di": sig.get("minus_di"),
                "di_spread": sig.get("di_spread"),
                "ema20_ema50_gap_pct": sig.get("ema20_ema50_gap_pct"),
                "price_to_ema20_pct": sig.get("price_to_ema20_pct"),
                "support_distance_pct": sig.get("support_distance_pct"),
                "ema200_1h": round(ema200_1h, 10) if ema200_1h is not None else None,
                "signal_close_1h": round(signal_close_1h, 10) if signal_close_1h is not None else None,
                "ema200_distance_pct": ema200_distance_pct,
                "rel_volume": sig.get("rel_volume"),
                "spike_tier": sig.get("spike_tier"),
                "macd_hist": sig.get("macd_hist"),
                "stoch_k": sig.get("stoch_k"),
                "stoch_d": sig.get("stoch_d"),
                "bb_pct_b": sig.get("bb_pct_b"),
                "roc": sig.get("roc"),
                "atr_pct": sig.get("atr_pct"),
                "ema20_1h": sig.get("ema20_1h"),
                "ema50_1h": sig.get("ema50_1h"),
                "price_1h_signal": sig.get("price_1h_signal"),
                "rsi_4h": sig.get("rsi_4h"),
                "adx_4h": sig.get("adx_4h"),
                "ema20_4h": sig.get("ema20_4h"),
                "ema50_4h": sig.get("ema50_4h"),
                "macd_hist_4h": sig.get("macd_hist_4h"),
                "stoch_k_4h": sig.get("stoch_k_4h"),
                "bb_pct_b_4h": sig.get("bb_pct_b_4h"),
                "rsi_15m": sig.get("rsi_15m"),
                "adx_15m": sig.get("adx_15m"),
                "ema20_15m": sig.get("ema20_15m"),
                "ema50_15m": sig.get("ema50_15m"),
                "macd_hist_15m": sig.get("macd_hist_15m"),
                "stoch_k_15m": sig.get("stoch_k_15m"),
                "bb_pct_b_15m": sig.get("bb_pct_b_15m"),
                "mtf_status": sig.get("mtf_status"),
                "mtf_4h": sig.get("mtf_4h"),
                "mtf_15m": sig.get("mtf_15m"),
                "btc_regime": sig.get("btc_regime"),
                "score": sig.get("score", sig.get("composite")),
                "grade": sig.get("grade"),
                "rr": sig.get("rr"),
                "rrce_status": sig.get("rrce_status", "NOT_RUN"),
                "rrce_failed_stage": sig.get("rrce_failed_stage", ""),
                "rrce_choch_confirmed": bool(sig.get("rrce_choch_confirmed")),
                "rrce_stage1_passed": sig.get("rrce_stage1_passed"),
                "rrce_stage1_position_pct": sig.get("rrce_stage1_position_pct"),
                "rrce_stage1_zone": sig.get("rrce_stage1_zone"),
                "rrce_stage1_range_width_pct": sig.get("rrce_stage1_range_width_pct"),
                "rrce_stage2_passed": sig.get("rrce_stage2_passed"),
                "rrce_stage2_pool_level": sig.get("rrce_stage2_pool_level"),
                "rrce_stage2_sweep_extreme": sig.get("rrce_stage2_sweep_extreme"),
                "rrce_stage2_sweep_time": sig.get("rrce_stage2_sweep_time"),
                "rrce_stage3_passed": sig.get("rrce_stage3_passed"),
                "rrce_stage3_choch_level": sig.get("rrce_stage3_choch_level"),
                "rrce_stage3_break_time": sig.get("rrce_stage3_break_time"),
                "rrce_stage3_fvg_top": sig.get("rrce_stage3_fvg_top"),
                "rrce_stage3_fvg_bottom": sig.get("rrce_stage3_fvg_bottom"),
                "rrce_stage4_valid": sig.get("rrce_stage4_valid"),
                "rrce_stage4_entry_zone": sig.get("rrce_stage4_entry_zone"),
                "rrce_stage4_rr": sig.get("rrce_stage4_rr"),
                "rrce_stage4_ob_top": sig.get("rrce_stage4_ob_top"),
                "rrce_stage4_ob_bottom": sig.get("rrce_stage4_ob_bottom"),
                "rrce_stage4_fvg_top": sig.get("rrce_stage4_fvg_top"),
                "rrce_stage4_fvg_bottom": sig.get("rrce_stage4_fvg_bottom"),
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
            "offset_days": OFFSET_DAYS,
            "warmup_hours": WARMUP_HOURS,
            "research_indicators": ["EMA200_1H_from_completed_closes"],
            "symbols": SYMBOLS,
            "timeframes": list(INTERVALS),
            "lookahead_policy": "outcome candles open at or after replay timestamp; no candle data before the signal timestamp is scored",
            "same_candle_conflict_policy": "SL first, matching SignalTracker",
            "production_code_modified": False,
            "long_signals_enabled": False,
            "replay_direction_policy": ["SHORT"],
            "harness_mode": "scanner_v5.main historical injection",
            "scan_cadence": "5m (matches .github/workflows/scanner.yml cron */5)",
            "forming_candle_policy": "reconstruct 1h/4h/15m in-progress candles from completed 5m bars before the boundary plus boundary 5m open only; no post-boundary OHLCV is exposed",
            "timeline_coverage": timeline_coverage,
            "outcome_expiry_hours": OUTCOME_LOOKAHEAD_HOURS,
            "archive_lag_buffer_hours": ARCHIVE_LAG_HOURS,
            "outcome_candle_interval": "5m",
            "incomplete_outcome_policy": "INCOMPLETE_DATA unless all 864 expected 5m candles from the signal timestamp through the 72h expiry are contiguous or TP/SL is reached before a gap",
        },
        "summary": summarize(results),
        "results": results,
    }
    RESULTS.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    print(f"RESULT_FILE={RESULTS}")


if __name__ == "__main__":
    run()