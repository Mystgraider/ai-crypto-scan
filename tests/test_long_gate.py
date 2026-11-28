import pandas as pd
from engines.long_gate import evaluate_long_setup

def _frame(rows):
    return pd.DataFrame(rows)

def _base():
    h1=_frame([
        {"close":100,"ema_20":99,"ema_50":97,"atr":2,"rsi":55,"macd_hist":-0.2,"adx":32},
        {"close":98,"ema_20":99,"ema_50":97,"atr":2,"rsi":52,"macd_hist":0.1,"adx":31},
        {"close":101,"ema_20":100,"ema_50":97,"atr":2,"rsi":58,"macd_hist":0.4,"adx":34},
        {"close":101.2,"ema_20":100.2,"ema_50":97.2,"atr":2,"rsi":58,"macd_hist":0.45,"adx":34},
    ])
    h4=_frame([
        {"close":99,"ema_20":98,"ema_50":96,"rsi":60},
        {"close":101,"ema_20":99,"ema_50":97,"rsi":62},
        {"close":101.5,"ema_20":99.5,"ema_50":97.5,"rsi":63},
    ])
    m15=_frame([
        {"close":99,"ema_20":100,"ema_50":98,"macd_hist":-0.1,"adx":24},
        {"close":98.5,"ema_20":99.5,"ema_50":98,"macd_hist":0.0,"adx":24},
        {"close":100.5,"ema_20":100,"ema_50":98.5,"macd_hist":0.2,"adx":28},
        {"close":101,"ema_20":100.2,"ema_50":98.7,"macd_hist":0.25,"adx":28},
    ])
    return h1,h4,m15

def _rrce_stage1_pass():
    return {"passed": True, "position_pct": 45.0}

def test_long_pullback_reclaim_passes():
    h1,h4,m15=_base()
    r=evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())
    assert r["valid"] is True
    assert r["setup"]=="LONG_PULLBACK_RECLAIM"

def test_long_rejects_overextended_rsi():
    h1,h4,m15=_base()
    h1.loc[h1.index[-2],"rsi"]=72
    assert evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())["valid"] is False

def test_long_requires_bullish_15m():
    h1,h4,m15=_base()
    m15.loc[m15.index[-2],["ema_20","ema_50","close","macd_hist"]]=[101.0,102.0,99.0,-0.3]
    assert evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())["valid"] is False

def test_long_rejects_weak_1h_trend():
    h1,h4,m15=_base()
    h1.loc[h1.index[-2],"adx"]=24
    assert evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())["valid"] is False

def test_long_rejects_weak_15m_trend():
    h1,h4,m15=_base()
    m15.loc[m15.index[-2],"adx"]=18
    assert evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())["valid"] is False

def test_long_rejects_chase():
    h1,h4,m15=_base()
    assert evaluate_long_setup(h1,h4,m15,104.0,rrce_stage1=_rrce_stage1_pass())["valid"] is False

def test_long_requires_rrce_stage1_alignment():
    h1,h4,m15=_base()
    failed={"passed":False,"position_pct":78.0}
    r=evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=failed)
    assert r["valid"] is False
    assert r["checks"]["rrce_stage1_alignment"] is False

def test_long_records_rrce_stage1_position():
    h1,h4,m15=_base()
    r=evaluate_long_setup(h1,h4,m15,101.0,rrce_stage1=_rrce_stage1_pass())
    assert r["metrics"]["rrce_stage1_passed"] is True
    assert r["metrics"]["rrce_stage1_position_pct"] == 45.0
