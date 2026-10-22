"""Deterministic offline OI fixtures, v2 (numeric + leakage-proof).

usage: python oi_fixtures_v2.py <repo_root> <label> [--strict-oracle]
       results JSON is written to $OI_OUT_DIR (default: system temp dir) as oi_v2_<label>.json

Corrections vs v1:
  * v1's future-spike check used `e[2]==a[2] and e[1]==a[1] or e[2]==a[2]`, i.e. `(A and B) or A`,
    which is just `A` (label equality). v1 therefore passed even when price/OI numbers were wrong.
  * Every fixture now checks label AND numeric price_chg AND numeric oi_change.
  * The oracle receives ONLY the observations up to the cutoff (prefix arrays), so it cannot read
    future data, and this is itself tested (C6, C7).
  * Leakage is proven by invariance: results at cutoff T must be bit-identical when every observation
    after T is (a) shifted by a spike or (b) replaced with garbage; a positive control shows the same
    machinery DOES see the spike once the cutoff reaches it.

Exit code: 1 if any leakage/oracle-integrity test fails, or (with --strict-oracle) if any fixture
differs from the production-semantics oracle; otherwise 0.
"""
import json
import os
import sys
import tempfile

root, label = sys.argv[1], sys.argv[2]
STRICT = "--strict-oracle" in sys.argv
OUT_DIR = os.environ.get("OI_OUT_DIR", tempfile.gettempdir())
sys.path.insert(0, root)
import numpy as np
import pandas as pd
import tools.historical_replay as hr
from engines.oi_engine import OIEngine

SYM = "ETH/USDT:USDT"
T0 = pd.Timestamp("2026-10-01T00:00:00Z")
FIVE = pd.Timedelta(minutes=5)
GRID = pd.date_range(T0, T0 + pd.Timedelta(hours=7), freq=FIVE)          # 5-minute archive grid
SPIKE_TS = pd.Timestamp("2026-10-01T02:10:00Z")                          # injected FUTURE level shift
# Tolerances (percentage points):
#  * OIEngine.analyze rounds oi_change_pct to 2 decimals -> |error| <= 0.005
#  * the fixture labels a 5m candle by the time its CLOSE price is defined for, so the replay's
#    price_chg = p[T-5m]/p[H-5m]-1 whereas the oracle uses p[T]/p[H]-1; for the linear 0.6%/h path
#    the difference is <= 0.0003 pp (measured, printed below); 0.001 leaves >3x headroom.
TOL_OI, TOL_PRICE = 0.005, 0.001


def paths(price_dir, oi_dir, spike=False):
    h = np.asarray((GRID - T0) / pd.Timedelta(hours=1), dtype=float)
    price = 100.0 * (1 + price_dir * 0.006 * h)                          # +/-0.6% per hour
    oi = 1_000_000.0 * (1 + oi_dir * 0.012 * h)                          # +/-1.2% per hour
    if spike:                                                            # level shift from SPIKE_TS onward
        k = int(np.where(GRID == SPIKE_TS)[0][0])
        price[k:] *= 1.05
        oi[k:] *= 1.30
    return price, oi


def mk_store(price, oi, end, drop_oi=None, poison=False):
    p = pd.Series(price, index=GRID)
    m5 = pd.DataFrame({"timestamp": GRID, "open": p.shift(1).fillna(p.iloc[0]).values, "close": p.values})
    m5["high"] = m5[["open", "close"]].max(axis=1)
    m5["low"] = m5[["open", "close"]].min(axis=1)
    m5["volume"] = 1.0

    def agg(rule):
        g = m5.set_index("timestamp").resample(rule, origin="epoch", label="left", closed="left")
        return g.agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna().reset_index()

    candles = {(SYM, "5m"): m5, (SYM, "15m"): agg("15min"), (SYM, "1h"): agg("1h"), (SYM, "4h"): agg("4h")}
    odf = pd.DataFrame({"timestamp": GRID, "sumOpenInterestValue": oi})
    if drop_oi is not None:
        odf = odf[drop_oi(odf)]
    if poison:                                                           # replace everything NOT knowable at `end`
        odf = odf.copy()
        odf.loc[odf["timestamp"] > end, "sumOpenInterestValue"] = 1e15
        for key, df in candles.items():
            d = df.copy()
            delta = hr.INTERVAL_DELTAS[key[1]]
            unfinished = d["timestamp"] + delta > end
            future = d["timestamp"] > end
            d.loc[unfinished, ["high", "low", "close", "volume"]] = 9999.0
            d.loc[future, "open"] = 7777.0
            candles[key] = d
    return hr.HistoricalStore(candles=candles, funding={}, oi={SYM: odf}, end=end)


def oracle(grid_prefix, price_prefix, oi_prefix, T, direction):
    """Production-semantics oracle. Receives ONLY observations with timestamp <= T (prefix arrays)."""
    assert grid_prefix[-1] == T and len(grid_prefix) == len(price_prefix) == len(oi_prefix), "oracle fed non-prefix data"
    idx = {t: i for i, t in enumerate(grid_prefix)}
    H = T.floor("h")
    Hm1 = H - pd.Timedelta(hours=1)
    if Hm1 not in idx:
        return None, None, "UNAVAILABLE"
    pc = (price_prefix[idx[T]] / price_prefix[idx[H]] - 1) * 100         # forming-candle close vs last completed close
    oc = (oi_prefix[idx[T]] / oi_prefix[idx[Hm1]] - 1) * 100             # live OI vs hourly bar H-1h
    up, dn, ru, rd = pc > 0.1, pc < -0.1, oc > 0.5, oc < -0.5            # thresholds as written in OIEngine.analyze
    if direction == "SHORT":
        lab = "CONFIRMED" if dn and ru else "WEAK" if dn and rd else "DIVERGING" if up and ru else "NEUTRAL"
    else:
        lab = "CONFIRMED" if up and ru else "WEAK" if up and rd else "DIVERGING" if dn and ru else "NEUTRAL"
    return pc, oc, lab


def oracle_at(price, oi, T, direction):
    n = int(np.where(GRID == T)[0][0]) + 1                               # physically truncate at T
    return oracle(GRID[:n], price[:n], oi[:n], T, direction)


def actual(store, direction):
    ex = hr.ReplayExchange(store)
    ld = hr.ReplayMarketLoader(store)
    d = OIEngine().fetch_oi(ex, SYM)
    hist = ex.fetch_open_interest_history(SYM, timeframe="1h", limit=2)
    sel = [pd.to_datetime(h["timestamp"], unit="ms", utc=True).strftime("%H:%M") for h in hist]
    f = ld._frame(SYM, "1h", None)
    pc = float(f["close"].pct_change().iloc[-1] * 100) if len(f) >= 2 else float("nan")
    avail = d.get("data_available", d.get("available"))
    if not avail:
        return dict(sel=sel, cur=None, prev=None, price=None, oi=None, label="UNAVAILABLE", reason=d.get("reason"))
    r = OIEngine().analyze(d["current_oi"], d["previous_oi"], pc, direction)
    return dict(sel=sel, cur=d["current_oi"], prev=d["previous_oi"], price=pc, oi=r["oi_change_pct"], label=r["oi_signal"], reason=None)


def same(a, b):
    """Exact (bit-level) equality of two actual() results; NaN == NaN."""
    def eq(x, y):
        if isinstance(x, float) and isinstance(y, float) and x != x and y != y:
            return True
        return x == y
    return all(eq(a[k], b[k]) for k in a)


rows, integrity = [], []


def record(case, T, direction, e, a, expect_label=None):
    e_pc, e_oc, e_lab = e
    lab_ok = (a["label"] == (expect_label or e_lab))
    pr_ok = oi_ok = True
    d_pr = d_oi = None
    if e_pc is not None and a["price"] is not None and a["price"] == a["price"]:
        d_pr = a["price"] - e_pc
        pr_ok = abs(d_pr) <= TOL_PRICE
    elif e_pc is not None:
        pr_ok = False
    if e_oc is not None and a["oi"] is not None:
        d_oi = a["oi"] - e_oc
        oi_ok = abs(d_oi) <= TOL_OI
    elif e_oc is not None:
        oi_ok = False
    rows.append(dict(case=case, T=T, dir=direction, sel=a["sel"], cur=a["cur"], prev=a["prev"],
                     exp_price=None if e_pc is None else round(e_pc, 5), act_price=None if a["price"] is None else round(a["price"], 5),
                     d_price=None if d_pr is None else round(d_pr, 5),
                     exp_oi=None if e_oc is None else round(e_oc, 5), act_oi=a["oi"], d_oi=None if d_oi is None else round(d_oi, 5),
                     exp=expect_label or e_lab, act=a["label"], label_ok=lab_ok, price_ok=pr_ok, oi_ok=oi_ok, ok=lab_ok and pr_ok and oi_ok))


# ---- A. original 4 scenarios x 5 cutoffs x 2 directions (preserved) --------------------------------
SCEN = {"A price+ OI+": (1, 1), "B price- OI+": (-1, 1), "C price+ OI-": (1, -1), "D price- OI-": (-1, -1)}
for name, (pd_, od_) in SCEN.items():
    price, oi = paths(pd_, od_)
    for T in ("02:00", "02:05", "02:30", "02:55", "03:00"):
        Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
        for direction in ("LONG", "SHORT"):
            record(name, T, direction, oracle_at(price, oi, Tt, direction), actual(mk_store(price, oi, Tt), direction))

# ---- B. availability edge cases (preserved) --------------------------------------------------------
price, oi = paths(1, 1)
for name, T, fn in (("E1 current OI missing (no rows <= T)", "00:00", lambda d, Tt: d["timestamp"] > Tt),
                    ("E2 previous OI missing (1 row only)", "00:00", lambda d, Tt: d["timestamp"] <= Tt)):
    Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
    record(name, T, "LONG", (None, None, "UNAVAILABLE"),
           actual(mk_store(price, oi, Tt, drop_oi=lambda d, Tt=Tt, fn=fn: fn(d, Tt)), "LONG"))

# ---- C. NO-FUTURE-LEAKAGE (rewritten) --------------------------------------------------------------
sp_price, sp_oi = paths(1, 1, spike=True)
cl_price, cl_oi = paths(1, 1, spike=False)
for T in ("02:00", "02:05"):                                              # strictly before SPIKE_TS (02:10)
    Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
    assert Tt < SPIKE_TS
    clean = actual(mk_store(cl_price, cl_oi, Tt), "LONG")
    spiked = actual(mk_store(sp_price, sp_oi, Tt), "LONG")
    poisoned = actual(mk_store(cl_price, cl_oi, Tt, poison=True), "LONG")
    spiked_poisoned = actual(mk_store(sp_price, sp_oi, Tt, poison=True), "LONG")
    integrity.append((f"C1 spike@02:10 invisible at {T}: result(spiked) == result(clean), all fields exact", same(spiked, clean), {"clean": clean, "spiked": spiked}))
    integrity.append((f"C2 garbage after {T} invisible: result(poisoned) == result(clean), all fields exact", same(poisoned, clean), {"clean": clean, "poisoned": poisoned}))
    integrity.append((f"C2b spike+garbage after {T} invisible", same(spiked_poisoned, clean), {}))
    e = oracle_at(sp_price, sp_oi, Tt, "LONG")                            # oracle fed ONLY the prefix up to T
    record("C3 spiked store vs prefix-only oracle", T, "LONG", e, spiked)
# positive control: at/after the spike timestamp the same machinery MUST see the spiked observation.
# It tests visibility of the data (current OI). It must NOT also require the % change to differ: a level
# shift covering the whole lookback window (the 5-minute window on `main`) cancels in the ratio, which is a
# property of that window, not a visibility failure. The % values are reported as information.
for T in ("02:10", "02:15"):
    Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
    clean = actual(mk_store(cl_price, cl_oi, Tt), "LONG")
    spiked = actual(mk_store(sp_price, sp_oi, Tt), "LONG")
    integrity.append((f"C4 positive control at {T}: spike IS visible (current OI differs)", spiked["cur"] != clean["cur"],
                      {"clean_current_oi": clean["cur"], "spiked_current_oi": spiked["cur"], "clean_oi%": clean["oi"], "spiked_oi%": spiked["oi"],
                       "info": "oi% equal on main at 02:15 because both lookback points are inside the shifted region"}))
# C5: invariance over EVERY scenario/cutoff/direction (poison all future data)
bad = []
for name, (pd_, od_) in SCEN.items():
    price, oi = paths(pd_, od_)
    for T in ("02:00", "02:05", "02:30", "02:55", "03:00"):
        Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
        for direction in ("LONG", "SHORT"):
            if not same(actual(mk_store(price, oi, Tt), direction), actual(mk_store(price, oi, Tt, poison=True), direction)):
                bad.append((name, T, direction))
integrity.append(("C5 poisoning all post-cutoff data changes nothing, 40 cases", not bad, {"differing": bad}))
# C6: the oracle itself cannot see the future (clean arrays vs spiked arrays, cutoffs before the spike)
pairs = []
for T in ("02:00", "02:05"):
    Tt = pd.Timestamp(f"2026-10-01T{T}:00Z")
    pairs.append(oracle_at(cl_price, cl_oi, Tt, "LONG") == oracle_at(sp_price, sp_oi, Tt, "LONG"))
integrity.append(("C6 oracle(clean arrays) == oracle(spiked arrays) at cutoffs before the spike", all(pairs), {"pairs_equal": pairs}))
try:
    oracle(GRID[:10], cl_price[:12], cl_oi[:12], GRID[9], "LONG")
    guard = False
except AssertionError:
    guard = True
integrity.append(("C7 oracle rejects non-prefix (future-containing) input", guard, {}))

# ---- report -----------------------------------------------------------------------------------------
os.makedirs(OUT_DIR, exist_ok=True)
json.dump(dict(rows=rows, integrity=[dict(name=n, ok=bool(o), detail=d) for n, o, d in integrity]),
          open(os.path.join(OUT_DIR, f"oi_v2_{label}.json"), "w"), default=str, indent=1)
max_pr = max((abs(r["d_price"]) for r in rows if r["d_price"] is not None), default=0)
max_oi = max((abs(r["d_oi"]) for r in rows if r["d_oi"] is not None), default=0)
n = len(rows)
print(f"[{label}] oracle comparison: {n} fixtures | label mismatches {sum(not r['label_ok'] for r in rows)} | "
      f"price mismatches (>{TOL_PRICE}) {sum(not r['price_ok'] for r in rows)} | OI mismatches (>{TOL_OI}) {sum(not r['oi_ok'] for r in rows)} | "
      f"fully matching {sum(r['ok'] for r in rows)}")
print(f"[{label}] max |price diff| {max_pr:.5f} pp, max |OI diff| {max_oi:.5f} pp")
for nme, ok, det in integrity:
    print(f"[{label}] {'PASS' if ok else 'FAIL'}  {nme}")
fail_integrity = any(not ok for _, ok, _ in integrity)
fail_oracle = STRICT and any(not r["ok"] for r in rows)
sys.exit(1 if (fail_integrity or fail_oracle) else 0)
