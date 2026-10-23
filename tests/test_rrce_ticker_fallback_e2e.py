"""Production-path regression: RRCE live-ticker failure must fall back to ATR.

Drives the REAL scanner_v5.main() with external dependencies faked (market data,
exchange, Telegram, storage). Only RRCEEngine.evaluate is patched, to force an
RRCE-valid Stage-4 candidate; everything after it (ticker fetch, live
revalidation, ATR fallback, RiskEngine, validation, ranking, live validation,
alert, persistence) is production code.

Contract (scanner_v5.py, RRCE live revalidation block):
  * live price unavailable (exception/None/missing/non-numeric/<=0) -> rrce_risk=None
    -> documented ATR fallback (RiskEngine.calculate) -> candidate continues;
  * explicit invalid RRCE revalidation (price away / bad structure) -> same demotion;
  * valid RRCE revalidation -> RRCE contract, ATR NOT used;
  * no valid ATR -> RiskEngine returns None -> candidate rejected, nothing fabricated.
"""
import contextlib
import io
import math
import os
import tempfile
import unittest
from unittest import mock

import numpy as np
import pandas as pd

import scanner_v5 as scanner
from config import CONFIG
from engines.rrce_engine import RRCEEngine
from indicators.indicators import Indicators

SYMBOLS = ["ETH/USDT:USDT", "SOL/USDT:USDT", "XRP/USDT:USDT"]
BTC = "BTC/USDT:USDT"
FIVE = pd.Timedelta(minutes=5)
CUTOFFS = [pd.Timestamp("2026-10-01T00:00:00Z") + pd.Timedelta(hours=h) for h in (30, 33, 36, 39, 42, 45)]


def _agg(m5, rule):
    g = m5.set_index("timestamp").resample(rule, origin="epoch", label="left", closed="left")
    return g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()


def build_market(flat=False):
    rng = np.random.default_rng(11)
    ts = pd.date_range("2026-09-10T00:00:00Z", "2026-10-03T00:00:00Z", freq=FIVE, inclusive="left")
    out = {}
    for k, sym in enumerate([*SYMBOLS, BTC]):
        n = len(ts)
        if flat:
            c = np.full(n, 100.0)
            o, h, l = c.copy(), c.copy(), c.copy()
        else:
            r = rng.normal(0, 0.0035, n) + 0.0004 * np.sin(np.arange(n) / (180 + 40 * k))
            c = 100 * np.exp(np.cumsum(r)); o = np.r_[c[0], c[:-1]]
            h = np.maximum(o, c) * (1 + rng.uniform(0, .002, n)); l = np.minimum(o, c) * (1 - rng.uniform(0, .002, n))
        m5 = pd.DataFrame(dict(timestamp=ts, open=o, high=h, low=l, close=c, volume=rng.uniform(50, 500, n)))
        out[sym] = {"5m": m5, "15m": _agg(m5, "15min"), "1h": _agg(m5, "1h"), "4h": _agg(m5, "4h")}
    return out


class FakeExchange:
    """No network. Ticker behaviour is programmable; funding is normal; OI unsupported (as on Bitget)."""
    def __init__(self, loader):
        self.loader = loader; self.mode = None; self.pending = False

    def fetch_ticker(self, symbol):
        real = {"last": float(self.loader.frame(symbol, "1h").iloc[-1]["close"])}
        if self.pending:
            self.pending = False
            if self.mode == "raise":
                raise RuntimeError("simulated ticker outage")
            if self.mode == "away":
                return {"last": real["last"] * 1.05}
            return self.mode
        return real

    def fetch_funding_rate(self, symbol):
        return {"fundingRate": 0.0001}

    def fetch_open_interest(self, symbol):
        raise NotImplementedError("fetchOpenInterest unsupported")

    def fetch_open_interest_history(self, symbol, timeframe="1h", limit=2):
        raise NotImplementedError("fetchOpenInterestHistory unsupported")


class FakeLoader:
    def __init__(self, market, end):
        self.market, self.end = market, end
        self.exchange = FakeExchange(self)

    def frame(self, symbol, tf, limit=None):
        df = self.market[symbol][tf]
        df = df[df["timestamp"] <= self.end]
        if limit is not None:
            df = df.tail(int(limit))
        return df.copy().reset_index(drop=True)

    get_ohlcv = lambda self, s, timeframe=None, limit=None: self.frame(s, timeframe or "1h", limit)
    get_1h = lambda self, s, limit=None: self.frame(s, "1h", limit)
    get_4h = lambda self, s, limit=None: self.frame(s, "4h", limit)
    get_15m = lambda self, s, limit=None: self.frame(s, "15m", limit)
    get_5m = lambda self, s, limit=None: self.frame(s, "5m", limit)


def run_scanner(market, ticker_mode=None, rrce="off", atr_nan=False):
    """rrce: 'off' = real RRCE (baseline) | 'valid' = force an RRCE-valid Stage-4 candidate."""
    signals, order, hits = [], [], {"n": 0}
    orig_eval = RRCEEngine.evaluate
    orig_apply = Indicators.apply

    def fake_eval(self, *a, **k):
        price = float(k["price"]); step = price * 0.01; long_ = k["direction"] == "LONG"
        if holder["loader"] is not None and ticker_mode is not None:
            holder["loader"].exchange.pending = True
            holder["loader"].exchange.mode = ticker_mode
            hits["n"] += 1
        return {"valid": True, "failed_at": None, "bonus": 0.0,
                "stage1": {"passed": True}, "stage2": {"passed": True}, "stage3": {"passed": True},
                "stage4": {"valid": True, "entry": price, "sl": price - step if long_ else price + step,
                           "tp": price + 3 * step if long_ else price - 3 * step, "rr": 3.0}}

    def nan_atr_apply(df, *a, **k):
        out = orig_apply(df, *a, **k)
        if atr_nan and "atr" in out.columns:
            out["atr"] = float("nan")
        return out

    holder = {"loader": None}
    log = io.StringIO()
    cwd = os.getcwd(); tmp = tempfile.mkdtemp(); os.makedirs(os.path.join(tmp, "storage")); os.chdir(tmp)
    try:
        for end in CUTOFFS:
            def mk(end=end):
                holder["loader"] = FakeLoader(market, end)
                return holder["loader"]
            with mock.patch.object(scanner, "MarketDataLoader", mk), \
                 mock.patch.object(scanner, "TopSymbolsLoader", lambda: type("T", (), {"get_top_symbols": lambda s: list(SYMBOLS)})()), \
                 mock.patch.object(scanner, "is_on_cooldown", lambda s: False), \
                 mock.patch.object(scanner, "set_cooldown", lambda s: None), \
                 mock.patch.object(scanner, "send_telegram_alert", lambda m: order.append("alert")), \
                 mock.patch.object(scanner, "save_signal", lambda **s: (order.append("save"), signals.append(dict(s, _end=str(end))))), \
                 mock.patch.object(scanner, "circuit_check", lambda: {"is_tripped": False, "losses_today": 0, "max_losses": 999}), \
                 mock.patch.object(scanner, "SignalTracker", lambda: type("Tr", (), {"run": lambda s: None})()), \
                 mock.patch.object(scanner, "AnalyticsEngine", lambda: type("An", (), {"compute": lambda s: {"total_signals": 0, "open": 0, "win_rate": 50.0, "profit_factor": 1.0}})()), \
                 mock.patch.object(Indicators, "apply", staticmethod(nan_atr_apply)), \
                 mock.patch.dict(CONFIG, {"signal_cooldown_hours": 0}):
                if rrce == "valid":
                    with mock.patch.object(RRCEEngine, "evaluate", fake_eval), contextlib.redirect_stdout(log):
                        scanner.main()
                else:
                    with contextlib.redirect_stdout(log):
                        scanner.main()
    finally:
        os.chdir(cwd)
    return signals, order, log.getvalue(), hits["n"]


def level_ok(s):
    e, sl, t1, t2, t3 = (float(s[k]) for k in ("entry", "sl", "tp1", "tp2", "tp3"))
    if not all(math.isfinite(x) and x > 0 for x in (e, sl, t1, t2, t3)):
        return False
    return (sl < e < t1 <= t2 <= t3) if s["direction"] == "LONG" else (t3 <= t2 <= t1 < e < sl)


KEY = lambda s: (s["_end"], s["symbol"], s["direction"])
MARKET = None
BASE = None


def setUpModule():
    global MARKET, BASE
    MARKET = build_market()
    BASE = run_scanner(MARKET)          # real RRCE, real ATR path: reference population


class TickerFallbackE2E(unittest.TestCase):
    def test_00_baseline_population_is_non_trivial(self):
        sigs = BASE[0]
        self.assertGreaterEqual(len(sigs), 4, "synthetic market produced too few baseline signals")
        self.assertTrue(all(level_ok(s) for s in sigs))

    def _assert_falls_back_to_atr(self, mode):
        sigs, order, log, injected = run_scanner(MARKET, ticker_mode=mode, rrce="valid")
        base_sigs = BASE[0]
        self.assertGreater(injected, 0, "fault was never injected")
        self.assertEqual(sorted(map(KEY, sigs)), sorted(map(KEY, base_sigs)),
                         f"candidates lost/added vs ATR baseline for ticker mode {mode!r}")
        self.assertNotIn("'NoneType' object has no attribute", log)
        by = {KEY(s): s for s in base_sigs}
        for s in sigs:
            self.assertEqual(s["rrce_risk_contract"], "ATR_FALLBACK")
            self.assertTrue(level_ok(s))
            for f in ("entry", "sl", "tp1", "tp2", "tp3"):          # same price and ATR inputs as the baseline ATR path
                self.assertEqual(s[f], by[KEY(s)][f], f)
        self.assertEqual(len({KEY(s) for s in sigs}), len(sigs), "duplicate candidate processing")
        self.assertEqual(order, ["alert", "save"] * len(sigs), "alert/persistence ordering changed")

    def test_01_ticker_raises(self):
        self._assert_falls_back_to_atr("raise")

    def test_02_ticker_unavailable_or_invalid_payloads(self):
        for name, payload in (("missing last", {}), ("last=None", {"last": None}), ("last='abc'", {"last": "abc"}),
                              ("last=0", {"last": 0}), ("last=-5", {"last": -5.0})):
            with self.subTest(payload=name):
                self._assert_falls_back_to_atr(payload)

    def test_02b_non_finite_prices_are_rejected_by_revalidation_and_fall_back(self):
        for name, payload in (("NaN", {"last": float("nan")}), ("inf", {"last": float("inf")})):
            with self.subTest(payload=name):
                self._assert_falls_back_to_atr(payload)

    def test_03_valid_rrce_risk_is_used_and_atr_is_not(self):
        sigs, order, log, _ = run_scanner(MARKET, ticker_mode=None, rrce="valid")
        self.assertGreater(len(sigs), 0)
        for s in sigs:
            self.assertEqual(s["rrce_risk_contract"], "RRCE")
            self.assertTrue(level_ok(s))
        base_by = {KEY(s): s for s in BASE[0]}
        self.assertTrue(any(s["tp3"] != base_by.get(KEY(s), {}).get("tp3") for s in sigs), "RRCE levels identical to ATR levels")
        self.assertEqual(order, ["alert", "save"] * len(sigs))

    def test_04_explicit_invalid_rrce_result_keeps_established_demotion(self):
        # live price 5% away from the planned entry => RRCE revalidation returns invalid (price_away_from_rrce_entry)
        sigs, order, log, injected = run_scanner(MARKET, ticker_mode="away", rrce="valid")
        self.assertGreater(injected, 0)
        self.assertEqual(sorted(map(KEY, sigs)), sorted(map(KEY, BASE[0])))
        self.assertTrue(all(s["rrce_risk_contract"] == "ATR_FALLBACK" for s in sigs))   # RRCE result rejected, ATR demotion
        self.assertNotIn("'NoneType' object has no attribute", log)

    def test_05_invalid_atr_fails_safely_without_fabricating_levels(self):
        """ATR validity is guarded in depth: (1) scanner skips NaN ATR before RRCE (line ~336), (2) the fallback
        derives ATR only if > 0, (3) RiskEngine returns None for any non-positive/non-numeric ATR and the candidate
        is rejected (`if risk is None`). A zero/NaN-ATR market never reaches the fallback with real data (other
        indicator guards stop it first), so (3) is verified against the real engine directly."""
        sigs, order, log, _ = run_scanner(MARKET, ticker_mode="raise", rrce="valid", atr_nan=True)
        self.assertEqual(sigs, [], "signals produced although ATR was NaN")
        self.assertNotIn("Traceback", log)
        flat = build_market(flat=True)                                  # constant price => ATR == 0
        sigs, order, log, _ = run_scanner(flat, ticker_mode="raise", rrce="valid")
        self.assertEqual(sigs, [])
        self.assertNotIn("Traceback", log)
        from engines.risk_engine import RiskEngine
        eng = RiskEngine()
        for direction in ("LONG", "SHORT"):
            for bad_atr in (None, 0, 0.0, -1.0, float("nan"), "x"):
                self.assertIsNone(eng.calculate(direction, 100.0, bad_atr), (direction, bad_atr))
            for bad_entry in (None, 0, -5.0, "x"):
                self.assertIsNone(eng.calculate(direction, bad_entry, 2.0), (direction, bad_entry))
            good = eng.calculate(direction, 100.0, 2.0)
            self.assertTrue(good and level_ok(dict(good, direction=direction, entry=100.0)))


if __name__ == "__main__":
    unittest.main()
