"""Research-only SHORT gate audit on persisted live signals (storage/signals.csv).

Uses ONLY fields that are actually persisted in signals.csv (adx, rsi, btc_regime,
entry/initial_sl/tp*, status, realized_r). It never touches scanner, risk, or LONG
logic and is not imported by production code.

Method
- SHORT signals from ``--start`` onward (the contiguous v6.2 window).
- Resolved = TP3_HIT / SL_HIT. EXPIRED is reported separately and counted as 0R in
  E[R] (assumption: expired rows carry no realized_r).
- Chronological thirds by resolved-trade rank: discovery / development / holdout.
- Uncertainty via day-clustered bootstrap (signals within a day are not independent).
"""
import argparse
import json

import numpy as np
import pandas as pd

RESOLVED = ("TP3_HIT", "SL_HIT")
KNOWN = RESOLVED + ("EXPIRED",)


def load_short(path: str, start: str) -> pd.DataFrame:
    df = pd.read_csv(path, low_memory=False)
    df = df[df["direction"].astype(str).str.upper() == "SHORT"].copy()
    df["ts"] = pd.to_datetime(df["timestamp"], utc=True, errors="raise")
    for col in ("entry", "initial_sl", "adx", "rsi", "realized_r"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df[(df["ts"] >= pd.Timestamp(start, tz="UTC")) & df["status"].isin(KNOWN)]
    df = df.sort_values("ts").copy()
    df["resolved"] = df["status"].isin(RESOLVED)
    df["y"] = (df["status"] == "TP3_HIT").astype(int)
    df["day"] = df["ts"].dt.date
    df["R"] = df["realized_r"].fillna(0.0)
    df["sl_dist_pct"] = (df["initial_sl"] - df["entry"]) / df["entry"] * 100.0
    return df


def assign_thirds(df: pd.DataFrame) -> pd.DataFrame:
    res = df[df["resolved"]]
    if len(res) < 3:
        raise ValueError("need at least 3 resolved trades for chronological thirds")
    ranks = res["ts"].rank(method="first")
    labels = pd.qcut(ranks, 3, labels=["discovery", "development", "holdout"])
    bounds = res.assign(seg=labels).groupby("seg", observed=True)["ts"].agg(["min", "max"])
    first, last = bounds["min"].min(), bounds["max"].max()

    def seg_of(t):
        if t < first:
            return "discovery"
        if t > last:
            return "holdout"
        for name, row in bounds.iterrows():
            if row["min"] <= t <= row["max"]:
                return name
        return "development"

    out = df.copy()
    out["seg"] = out["ts"].map(seg_of)
    return out


def configs(df: pd.DataFrame) -> dict:
    rsi_band = (df["rsi"] >= 50) & (df["rsi"] <= 70)
    adx_low = df["adx"] < 20
    bear_caution = df["btc_regime"] == "BEAR_CAUTION"
    return {
        "A_baseline": pd.Series(True, index=df.index),
        "B_current_rsi_adx": rsi_band & adx_low,
        "C_rsi_not_bear_caution": rsi_band & ~bear_caution,
        "D_current_plus_not_bear_caution": rsi_band & adx_low & ~bear_caution,
    }


def _summary(df: pd.DataFrame, mask: pd.Series) -> dict:
    sel = df[mask]
    res = sel[sel["resolved"]]
    return {
        "signals": int(len(sel)),
        "resolved": int(len(res)),
        "tp3": int(res["y"].sum()),
        "sl": int(len(res) - res["y"].sum()),
        "expired": int((sel["status"] == "EXPIRED").sum()),
        "tp3_rate": float(res["y"].mean()) if len(res) else None,
        "expectancy_r_per_signal": float(sel["R"].mean()) if len(sel) else None,
        "days": int(sel["day"].nunique()),
        "sl_dist_pct_median": float(sel["sl_dist_pct"].median()) if len(sel) else None,
        "sl_dist_pct_p75": float(sel["sl_dist_pct"].quantile(0.75)) if len(sel) else None,
        "tp3_rate_by_third": {
            seg: (float(res[res["seg"] == seg]["y"].mean()) if (res["seg"] == seg).any() else None)
            for seg in ("discovery", "development", "holdout")
        },
    }


def clustered_diff(df: pd.DataFrame, mask: pd.Series, boots: int, seed: int) -> dict:
    res = df[df["resolved"]]
    m = mask.loc[res.index].to_numpy()
    y = res["y"].to_numpy()
    days = res["day"].unique()
    idx_by_day = {d: np.where(res["day"].to_numpy() == d)[0] for d in days}
    rng = np.random.default_rng(seed)
    diffs = []
    for _ in range(boots):
        pick = rng.choice(days, len(days))
        idx = np.concatenate([idx_by_day[p] for p in pick])
        yy, mm = y[idx], m[idx]
        if mm.sum():
            diffs.append(yy[mm].mean() - yy.mean())
    arr = np.array(diffs)
    return {
        "diff_pp": float(arr.mean() * 100),
        "ci95_pp": [float(np.percentile(arr, 2.5) * 100), float(np.percentile(arr, 97.5) * 100)],
        "p_diff_le_0": float((arr <= 0).mean()),
    }


def run(path: str, start: str, boots: int = 3000, seed: int = 11) -> dict:
    df = assign_thirds(load_short(path, start))
    out = {"source": path, "start": start, "rows": int(len(df)), "configs": {}}
    for name, mask in configs(df).items():
        entry = _summary(df, mask)
        if name != "A_baseline":
            entry["vs_baseline_day_clustered"] = clustered_diff(df, mask, boots, seed)
        out["configs"][name] = entry
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--signals", default="storage/signals.csv")
    ap.add_argument("--start", default="2026-10-01")
    ap.add_argument("--out", default="short_live_signal_audit.json")
    ap.add_argument("--boots", type=int, default=3000)
    args = ap.parse_args()
    result = run(args.signals, args.start, args.boots)
    with open(args.out, "w") as fh:
        json.dump(result, fh, indent=2, sort_keys=True)
    print(json.dumps(result, indent=2, sort_keys=True))
