"""Research-only: rejection counterfactuals on a replay result file.

Compares the SAME candidate set under:
  A baseline | B reject RRCE-contract rows with final RR(TP3) > max_rr
  D reject RRCE-contract rows with stop distance < min_stop_pct | E both
Rejection counterfactuals keep retained signals' outcomes unchanged (their price
path is unaffected). Target ADJUSTMENT (option C) changes the path outcome and
needs candle data, so it is intentionally NOT computed here.

Thresholds are inputs fixed a priori (4.0 = code default cap, 0.3 = existing
CONFIG min_sl_pct); this tool never searches for a "best" threshold.
Usage: python tools/rr_counterfactuals.py results.json [out.json]
"""
import json
import sys

import numpy as np
import pandas as pd


def classify(df: pd.DataFrame) -> pd.Series:
    milestones = df["milestones"].apply(lambda m: len(m) > 0 if isinstance(m, list) else False)
    out = np.select(
        [df.outcome == "TP3_HIT", df.outcome == "BREAKEVEN_AFTER_TP1", df.outcome == "BREAKEVEN_AFTER_TP2",
         (df.outcome == "SL_HIT") & milestones, df.outcome == "SL_HIT", df.outcome == "EXPIRED"],
        ["TP3", "BE", "BE", "BE", "SL", "EXPIRED"], "OPEN")
    return pd.Series(out, index=df.index)


def summarize(x: pd.DataFrame) -> dict:
    c = x["cls"].value_counts()
    tp, sl = int(c.get("TP3", 0)), int(c.get("SL", 0))
    return {"n": int(len(x)), "TP3": tp, "SL": sl, "BE": int(c.get("BE", 0)), "EXPIRED": int(c.get("EXPIRED", 0)),
            "OPEN": int(c.get("OPEN", 0)),
            "TP3_over_TP3_plus_SL_pct": round(100 * tp / (tp + sl), 2) if tp + sl else None}


def run(rows, max_rr=4.0, min_stop_pct=0.3, split_ts=None):
    df = pd.DataFrame(rows)
    df["risk"] = (df.entry - df.sl).abs()
    df["rr3"] = (df.tp3 - df.entry).abs() / df.risk.replace(0, np.nan)
    df["stop_pct"] = 100 * df.risk / df.entry
    df["cls"] = classify(df)
    df["t"] = pd.to_datetime(df.replay_time, utc=True)
    rrce = df.rrce_risk_contract == "RRCE"
    rej = {
        "A_baseline": pd.Series(False, index=df.index),
        "B_reject_rr_above_max": rrce & (df.rr3 > max_rr + 1e-4),
        "D_reject_stop_below_min": rrce & (df.stop_pct < min_stop_pct),
    }
    rej["E_reject_both"] = rej["B_reject_rr_above_max"] | rej["D_reject_stop_below_min"]
    report = {"parameters": {"max_rr": max_rr, "min_stop_pct": min_stop_pct,
                             "scope": "RRCE-contract rows only; ATR_FALLBACK has its own ladder and min_sl_pct"},
              "option_C_adjust_target": "NOT VERIFIABLE without candle data (outcome path changes)",
              "level_audit": {
                  "rows": int(len(df)), "rrce_rows": int(rrce.sum()),
                  "zero_risk_rows": int((df.risk == 0).sum()),
                  "rrce_rr3_above_max": int((rrce & (df.rr3 > max_rr + 1e-4)).sum()),
                  "rrce_stop_below_min": int((rrce & (df.stop_pct < min_stop_pct)).sum()),
                  "rrce_max_rr3": round(float(df.loc[rrce, "rr3"].max()), 2) if rrce.any() else None,
                  "rrce_min_stop_pct": round(float(df.loc[rrce, "stop_pct"].min()), 4) if rrce.any() else None},
              "counterfactuals": {}}
    for name, m in rej.items():
        entry = {"rejected": int(m.sum()), "retained": int((~m).sum()),
                 "retained_outcomes": summarize(df[~m]), "rejected_outcomes_under_original_targets": summarize(df[m])}
        if split_ts is not None:
            sp = pd.Timestamp(split_ts)
            for lab, part in (("development_before_split", df.t < sp), ("validation_from_split", df.t >= sp)):
                entry[lab] = {"rejected": int((m & part).sum()), "retained_outcomes": summarize(df[~m & part])}
        report["counterfactuals"][name] = entry
    return report


if __name__ == "__main__":
    data = json.load(open(sys.argv[1]))
    rep = run(data["results"], split_ts=data.get("metadata", {}).get("split") or "2026-09-23T13:00:00Z")
    text = json.dumps(rep, indent=2)
    if len(sys.argv) > 2:
        open(sys.argv[2], "w").write(text)
    print(text)
