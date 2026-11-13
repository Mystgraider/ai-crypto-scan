"""Research-only SHORT RRCE + indicator alignment audit.
Never changes scanner, LONG, risk, or SL/TP. Reads backtest_results.json.
"""
import collections, json, math
from pathlib import Path
from statistics import median

P=Path("backtest_results.json")
payload=json.loads(P.read_text(encoding="utf-8"))
rows=[r for r in payload.get("results",[]) if r.get("direction")=="SHORT"]

def n(v):
    try:
        x=float(v); return x if math.isfinite(x) else None
    except (TypeError,ValueError): return None

def stats(xs):
    c=collections.Counter(r.get("outcome","UNKNOWN") for r in xs)
    tp,sl=c["TP3_HIT"],c["SL_HIT"]; res=tp+sl
    sd=[]; td=[]
    for r in xs:
        e=n(r.get("entry"))
        if e and e>0:
            if n(r.get("sl")) is not None: sd.append(abs(n(r["sl"])-e)/e*100)
            if n(r.get("tp3")) is not None: td.append(abs(n(r["tp3"])-e)/e*100)
    return {"signals":len(xs),"tp3":tp,"sl":sl,"expired":c["EXPIRED"],
            "resolved":res,"tp3_rate_pct":round(100*tp/res,2) if res else None,
            "sl_distance_pct_median":round(median(sd),4) if sd else None,
            "tp3_distance_pct_median":round(median(td),4) if td else None}

def syms(xs):
    return {s:stats([r for r in xs if r.get("symbol")==s])
            for s in sorted({r.get("symbol") for r in xs if r.get("symbol")})}

def thirds(xs):
    x=sorted([r for r in xs if r.get("replay_time")],key=lambda r:r["replay_time"])
    if not x:return {}
    k=max(1,(len(x)+2)//3); out={}
    for i,label in enumerate(("first","middle","last")):
        q=x[i*k:(i+1)*k]
        if q: out[label]={"start":q[0]["replay_time"],"end":q[-1]["replay_time"],**stats(q)}
    return out

def ir(r):
    p=n(r.get("rrce_stage1_position_pct"))
    return p is not None and 0<=p<=100

stage1={
"current_premium_40_100":lambda r:ir(r) and n(r["rrce_stage1_position_pct"])>=40,
"midpoint_50_100":lambda r:ir(r) and n(r["rrce_stage1_position_pct"])>=50,
"inside_range":ir,
"lower_half_0_50":lambda r:ir(r) and n(r["rrce_stage1_position_pct"])<50,
"lower_40":lambda r:ir(r) and n(r["rrce_stage1_position_pct"])<40,
}
ind={
"rsi_50_55":lambda r:50<=n(r.get("rsi"))<55 if n(r.get("rsi")) is not None else False,
"adx4h_lt15":lambda r:n(r.get("adx_4h")) is not None and n(r["adx_4h"])<15,
"rsi15_lt55":lambda r:n(r.get("rsi_15m")) is not None and n(r["rsi_15m"])<55,
"macd15_nonpositive":lambda r:n(r.get("macd_hist_15m")) is not None and n(r["macd_hist_15m"])<=0,
"below_ema200_1h":lambda r:n(r.get("ema200_distance_pct")) is not None and n(r["ema200_distance_pct"])<0,
"atr_050_080":lambda r:n(r.get("atr_pct")) is not None and .5<=n(r["atr_pct"])<.8,
"di_not_bearish":lambda r:n(r.get("plus_di")) is not None and n(r.get("minus_di")) is not None and n(r["minus_di"])<=n(r["plus_di"]),
}
combo={
"inside_plus_macd15":lambda r:stage1["inside_range"](r) and ind["macd15_nonpositive"](r),
"lower40_plus_macd15":lambda r:stage1["lower_40"](r) and ind["macd15_nonpositive"](r),
"inside_plus_rsi15":lambda r:stage1["inside_range"](r) and ind["rsi15_lt55"](r),
"lower40_plus_rsi15":lambda r:stage1["lower_40"](r) and ind["rsi15_lt55"](r),
"inside_plus_adx4":lambda r:stage1["inside_range"](r) and ind["adx4h_lt15"](r),
"lower40_plus_adx4":lambda r:stage1["lower_40"](r) and ind["adx4h_lt15"](r),
"inside_plus_macd15_adx4":lambda r:stage1["inside_range"](r) and ind["macd15_nonpositive"](r) and ind["adx4h_lt15"](r),
}

families={**stage1,**ind,**combo}
ordered=sorted(rows,key=lambda r:r.get("replay_time",""))
split=max(1,(len(ordered)*2)//3); discovery=ordered[:split]; holdout=ordered[split:]
report={}
for name,pred in families.items():
    allx=[r for r in rows if pred(r)]; dx=[r for r in discovery if pred(r)]; hx=[r for r in holdout if pred(r)]
    h=stats(hx); b=stats(holdout)
    symbol_tp=sorted((v["tp3"] for v in syms(hx).values()),reverse=True)
    largest=(100*symbol_tp[0]/h["tp3"]) if symbol_tp and h["tp3"] else 0
    report[name]={
        "all":stats(allx),"discovery":stats(dx),"holdout":h,
        "holdout_by_symbol":syms(hx),"holdout_by_third":thirds(hx),
        "largest_holdout_symbol_tp3_share_pct":round(largest,2),
        "passes_holdout":bool(h["signals"]>=20 and h["tp3"]>=1 and
                              h["tp3_rate_pct"] is not None and b["tp3_rate_pct"] is not None and
                              h["tp3_rate_pct"]>=b["tp3_rate_pct"] and largest<60)
    }

summary={
"research_only":True,"production_strategy_changed":False,
"direction":"SHORT","long_changed":False,"risk_geometry_changed":False,
"sl_tp_changed":False,"rrce_gate_changed":False,
"baseline":stats(rows),"baseline_symbols":syms(rows),"baseline_thirds":thirds(rows),
"chronological_discovery_rows":len(discovery),"chronological_holdout_rows":len(holdout),
"families":report,
"approved_candidate":None,
"decision":"NO CANDIDATE APPROVED. The final chronological segment contains no TP3; any threshold that looks strong in discovery is regime-overfit and must not be promoted.",
"next_step":"Freeze no production change. Run a separate offset-60 30-day replay, then evaluate these same fixed structural families without retuning."
}
payload.setdefault("summary",{})["short_setup_alignment"]=summary
P.write_text(json.dumps(payload,indent=2,default=str),encoding="utf-8")
print(json.dumps(summary,indent=2))
