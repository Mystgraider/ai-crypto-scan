"""Research-only comparison of Candidate C and Candidate C5 from replay output.

Reads backtest_results.json produced by historical_replay.py and adds an
explicit C vs C5 comparison. Does not alter production signal generation.
"""
import json
import math
from pathlib import Path

path = Path("backtest_results.json")
payload = json.loads(path.read_text(encoding="utf-8"))
rows = payload.get("results", [])
shorts = [r for r in rows if r.get("direction") == "SHORT"]


def valid_num(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def counts(items):
    outcomes = {}
    for row in items:
        outcome = row.get("outcome", "UNKNOWN")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    tp3, sl = outcomes.get("TP3_HIT", 0), outcomes.get("SL_HIT", 0)
    resolved = tp3 + sl
    return {
        "signals": len(items),
        "outcomes": outcomes,
        "resolved_tp3_or_sl": resolved,
        "tp3": tp3,
        "sl": sl,
        "expired": outcomes.get("EXPIRED", 0),
        "tp3_rate_pct": round(100 * tp3 / resolved, 2) if resolved else None,
    }


candidate_c, candidate_c5 = [], []
missing_rsi_adx = 0
c5_missing_spike = 0
for row in shorts:
    rsi, adx = valid_num(row.get("rsi")), valid_num(row.get("adx"))
    if rsi is None or adx is None:
        missing_rsi_adx += 1
        continue
    if rsi >= 50 and adx >= 25:
        candidate_c.append(row)
    spike = str(row.get("spike_tier", "")).strip().upper()
    if rsi >= 50 and adx >= 30:
        if not spike:
            c5_missing_spike += 1
        elif spike == "NORMAL":
            candidate_c5.append(row)

times = sorted({str(r.get("replay_time", "")) for r in shorts})
windows = []
for idx in range(3):
    chunk = times[idx * len(times) // 3:(idx + 1) * len(times) // 3]
    if not chunk:
        continue
    time_set = set(chunk)
    base_window = [r for r in shorts if str(r.get("replay_time", "")) in time_set]
    c_window = [r for r in candidate_c if str(r.get("replay_time", "")) in time_set]
    c5_window = [r for r in candidate_c5 if str(r.get("replay_time", "")) in time_set]
    windows.append({
        "window": idx + 1,
        "start": chunk[0],
        "end": chunk[-1],
        "short_baseline": counts(base_window),
        "candidate_c_rsi50_adx25": counts(c_window),
        "candidate_c5_rsi50_adx30_spike_normal": counts(c5_window),
    })

payload.setdefault("summary", {})["candidate_c5_research"] = {
    "rule": "SHORT AND RSI >= 50 AND ADX >= 30 AND spike_tier == NORMAL",
    "research_only": True,
    "production_strategy_changed": False,
    "short_baseline": counts(shorts),
    "candidate_c_rsi50_adx25": counts(candidate_c),
    "candidate_c5_rsi50_adx30_spike_normal": counts(candidate_c5),
    "short_rows_missing_rsi_or_adx": missing_rsi_adx,
    "rows_with_rsi_adx_eligible_for_c5_but_spike_missing": c5_missing_spike,
    "chronological_diagnostic_windows_not_untouched_holdout": windows,
}
path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
print(json.dumps(payload["summary"]["candidate_c5_research"], indent=2))
