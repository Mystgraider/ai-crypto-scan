"""Research-only SHORT failure-mode audit.

Reads a merged backtest_results.json and diagnoses outcome, symbol/regime,
entry-timing, and SL-distance behavior. No production strategy/risk/LONG changes.
"""
from __future__ import annotations
import collections, json, math
from pathlib import Path
from statistics import median, quantiles

P=Path("backtest_results.json")

def num(v):
    try:
        x=float(v)
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):
        return None

def stats(rows):
    c=collections.Counter(r.get("outcome","UNKNOWN") for r in rows)
    tp,sl,ex=c["TP3_HIT"],c["SL_HIT"],c["EXPIRED"]
    res=tp+sl
    sd=[]; td=[]
    for r in rows:
        e=num(r.get("entry"))
        if e and e>0:
            for k,out in (("sl",sd),("tp3",td)):
                x=num(r.get(k))
                if x is not None: out.append(abs(x-e)/e*100)
    return {
        "signals":len(rows),"tp3":tp,"sl":sl,"expired":ex,"resolved":res,
        "tp3_rate_pct":round(100*tp/res,2) if res else None,
        "median_sl_distance_pct":round(median(sd),5) if sd else None,
        "median_tp3_distance_pct":round(median(td),5) if td else None,
        "sl_distance_n":len(sd)
    }

def group(rows,key):
    out={}
    for k in sorted({key(r) for r in rows},key=lambda x:str(x)):
        g=[r for r in rows if key(r)==k]
        out[str(k)]=stats(g)
    return out

def field(r,*names):
    for n in names:
        if r.get(n) is not None:
            return r.get(n)
    return None

def bucket_num(v,bounds):
    x=num(v)
    if x is None:return "MISSING"
    for lo,hi,label in bounds:
        if lo <= x < hi:return label
    return bounds[-1][2] if x >= bounds[-1][1] else "MISSING"

def median_by_bucket(rows, value_fn, buckets):
    out={}
    for label,pred in buckets:
        g=[r for r in rows if pred(r)]
        out[label]=stats(g)
    return out

def timing(rows):
    vals=[]
    for r in rows:
        rt=field(r,"replay_time")
        st=field(r,"rrce_stage2_sweep_time")
        bt=field(r,"rrce_stage3_break_time")
        if rt and st:
            try:
                a=__import__("datetime").datetime.fromisoformat(str(rt).replace("Z","+00:00"))
                b=__import__("datetime").datetime.fromisoformat(str(st).replace("Z","+00:00"))
                vals.append(("sweep_to_replay_min",(a-b).total_seconds()/60,r))
            except Exception: pass
        if st and bt:
            try:
                a=__import__("datetime").datetime.fromisoformat(str(bt).replace("Z","+00:00"))
                b=__import__("datetime").datetime.fromisoformat(str(st).replace("Z","+00:00"))
                vals.append(("sweep_to_choch_min",(a-b).total_seconds()/60,r))
            except Exception: pass
    return {
        "observations":len(vals),
        "sweep_to_replay_min_median":round(median([v for k,v,r in vals if k=="sweep_to_replay_min"]),3) if any(k=="sweep_to_replay_min" for k,v,r in vals) else None,
        "sweep_to_choch_min_median":round(median([v for k,v,r in vals if k=="sweep_to_choch_min"]),3) if any(k=="sweep_to_choch_min" for k,v,r in vals) else None,
    }

def main():
    payload=json.loads(P.read_text())
    rows=[r for r in payload.get("results",[]) if r.get("direction")=="SHORT"]
    rows.sort(key=lambda r:r.get("replay_time",""))
    thirds=[]
    n=len(rows)
    for i,label in enumerate(("first","middle","last")):
        a=(n*i)//3;b=(n*(i+1))//3
        thirds.append((label,rows[a:b]))
    outcome_by_third={k:stats(v) for k,v in thirds}

    symbols=group(rows,lambda r:r.get("symbol","MISSING"))
    # Indicator/structure buckets use actual replay field names and remain diagnostic.
    rsi=median_by_bucket(rows,None,[
        ("RSI_50_55",lambda r: (x:=num(field(r,"rsi","rsi_1h"))) is not None and 50<=x<55),
        ("RSI_55_60",lambda r: (x:=num(field(r,"rsi","rsi_1h"))) is not None and 55<=x<60),
        ("RSI_60_65",lambda r: (x:=num(field(r,"rsi","rsi_1h"))) is not None and 60<=x<65),
        ("RSI_65_70",lambda r: (x:=num(field(r,"rsi","rsi_1h"))) is not None and 65<=x<70),
    ])
    adx=median_by_bucket(rows,None,[
        ("ADX_0_10",lambda r:(x:=num(field(r,"adx","adx_1h"))) is not None and x<10),
        ("ADX_10_15",lambda r:(x:=num(field(r,"adx","adx_1h"))) is not None and 10<=x<15),
        ("ADX_15_20",lambda r:(x:=num(field(r,"adx","adx_1h"))) is not None and 15<=x<20),
    ])
    ema=median_by_bucket(rows,None,[
        ("EMA20_0_1pct",lambda r:(x:=num(field(r,"price_to_ema20_pct"))) is not None and 0<=x<1),
        ("EMA20_1_3pct",lambda r:(x:=num(field(r,"price_to_ema20_pct"))) is not None and 1<=x<3),
        ("EMA20_3_6pct",lambda r:(x:=num(field(r,"price_to_ema20_pct"))) is not None and 3<=x<6),
        ("EMA20_6pct_plus",lambda r:(x:=num(field(r,"price_to_ema20_pct"))) is not None and x>=6),
    ])
    support=median_by_bucket(rows,None,[
        ("SUPPORT_lt1pct",lambda r:(x:=num(field(r,"support_distance_pct"))) is not None and x<1),
        ("SUPPORT_1_2pct",lambda r:(x:=num(field(r,"support_distance_pct"))) is not None and 1<=x<2),
        ("SUPPORT_2_4pct",lambda r:(x:=num(field(r,"support_distance_pct"))) is not None and 2<=x<4),
        ("SUPPORT_4pct_plus",lambda r:(x:=num(field(r,"support_distance_pct"))) is not None and x>=4),
    ])
    structure=group(rows,lambda r:
        f"4H_{bucket_num(field(r,'rrce_stage1_position_pct'),[(0,40,'LT40'),(40,60,'40_60'),(60,80,'60_80'),(80,101,'80_100')])}"
    )
    stage2=group(rows,lambda r:str(field(r,"rrce_stage2_passed") if field(r,"rrce_stage2_passed") is not None else "MISSING"))
    stage3=group(rows,lambda r:str(field(r,"rrce_stage3_passed") if field(r,"rrce_stage3_passed") is not None else "MISSING"))

    # Outcome-specific geometry is the central diagnostic for "SL moves too far".
    by_outcome={k:stats([r for r in rows if r.get("outcome")==k]) for k in ("TP3_HIT","SL_HIT","EXPIRED")}
    sl_quantiles=[]
    slvals=[]
    for r in rows:
        if r.get("outcome")!="SL_HIT": continue
        e=num(r.get("entry")); s=num(r.get("sl"))
        if e and e>0 and s is not None: slvals.append(abs(s-e)/e*100)
    if slvals:
        qs=quantiles(slvals,n=4,method="inclusive")
        sl_quantiles=[round(x,5) for x in qs]

    report={
        "research_only":True,"production_strategy_changed":False,
        "long_logic_changed":False,"risk_or_sl_tp_geometry_changed":False,
        "method":"Fixed diagnostic audit across outcomes, symbols, chronological thirds, indicator bands, RRCE location, and SL-distance distributions. No threshold is promoted.",
        "baseline":stats(rows),"by_outcome":by_outcome,
        "chronological_thirds":outcome_by_third,
        "by_symbol":symbols,
        "rsi_bands":rsi,"adx_bands":adx,"price_to_ema20_bands":ema,
        "support_distance_bands":support,"rrce_4h_location":structure,
        "rrce_stage2":stage2,"rrce_stage3":stage3,
        "sl_distance_quartiles_pct":sl_quantiles,
        "timing":timing(rows),
        "diagnostic_conclusion":"NO PRODUCTION CHANGE. Use this audit to identify whether failures are regime/symbol/entry-timing/geometry driven before any new fixed candidate is tested on untouched chronology."
    }
    payload.setdefault("summary",{})["short_failure_mode_audit"]=report
    P.write_text(json.dumps(payload,indent=2),encoding="utf-8")
    print(json.dumps(report,indent=2))

if __name__=="__main__":
    main()
