"""Research-only SHORT indicator outcome comparison.

Compares indicator distributions for TP3_HIT versus SL_HIT on the existing
independent 120d/90d/60d windows. This is descriptive research, not a gate
selector: it emits no approved candidate and never changes production code.
"""
from __future__ import annotations
import json, math, statistics
from pathlib import Path

WINDOWS = (120, 90, 60)
BASE = Path('merged')
OUT = Path('pooled_short_interaction_audit.json')
FEATURES = (
    'rsi', 'adx', 'plus_di', 'minus_di', 'di_spread', 'macd_hist',
    'stoch_k', 'stoch_d', 'bb_pct_b', 'roc', 'atr_pct', 'rel_volume',
    'price_to_ema20_pct', 'ema20_ema50_gap_pct', 'support_distance_pct',
    'rsi_15m', 'adx_15m', 'macd_hist_15m', 'stoch_k_15m', 'bb_pct_b_15m',
    'rsi_4h', 'adx_4h', 'macd_hist_4h', 'stoch_k_4h', 'bb_pct_b_4h',
    'rrce_stage1_position_pct', 'rrce_stage1_range_width_pct', 'rrce_stage4_rr',
)
OUTCOMES = ('TP3_HIT', 'SL_HIT', 'EXPIRED')

def number(v):
    try:
        x = float(v)
        return x if math.isfinite(x) else None
    except (TypeError, ValueError):
        return None

def quantiles(values):
    xs = sorted(x for x in values if x is not None)
    if not xs:
        return {'n': 0, 'median': None, 'q25': None, 'q75': None, 'mean': None}
    def q(p):
        pos = (len(xs)-1)*p
        lo, hi = math.floor(pos), math.ceil(pos)
        return xs[lo] if lo == hi else xs[lo]*(hi-pos)+xs[hi]*(pos-lo)
    return {'n':len(xs), 'median':round(statistics.median(xs),6),
            'q25':round(q(.25),6), 'q75':round(q(.75),6),
            'mean':round(statistics.fmean(xs),6)}

def planned_sl_distance(r):
    entry, sl = number(r.get('entry')), number(r.get('sl'))
    if entry is None or entry <= 0 or sl is None: return None
    return abs(sl-entry)/entry*100

def outcome_counts(rows):
    c = {k:sum(r.get('outcome') == k for r in rows) for k in OUTCOMES}
    resolved = c['TP3_HIT'] + c['SL_HIT']
    return {'signals':len(rows), 'tp3':c['TP3_HIT'], 'sl':c['SL_HIT'],
            'expired':c['EXPIRED'], 'resolved':resolved,
            'tp3_rate_pct':round(100*c['TP3_HIT']/resolved,3) if resolved else None,
            'planned_entry_to_sl_distance_pct':quantiles([planned_sl_distance(r) for r in rows])}

def cohort(rows):
    out = {}
    for label in OUTCOMES:
        rr = [r for r in rows if r.get('outcome') == label]
        out[label] = {'count':len(rr), 'features':{k:quantiles([number(r.get(k)) for r in rr]) for k in FEATURES},
                      'planned_sl_distance_pct':quantiles([planned_sl_distance(r) for r in rr])}
    return out

def grouped(rows, key):
    result = {}
    for r in rows:
        value = r.get(key)
        value = str(value) if value is not None else 'MISSING'
        result.setdefault(value, []).append(r)
    return {k:outcome_counts(v) for k,v in sorted(result.items())}

def thirds(rows):
    ordered = sorted(rows, key=lambda r: str(r.get('replay_time') or r.get('event_time') or ''))
    n = len(ordered)
    return {f'third_{i+1}':outcome_counts(ordered[(i*n)//3:((i+1)*n)//3]) for i in range(3)}

def load_window(w):
    data = json.loads((BASE/f'short_window_{w}.json').read_text(encoding='utf-8'))
    rows = [r for r in data.get('results',[]) if r.get('direction') == 'SHORT']
    unknown = sorted({str(r.get('outcome')) for r in rows if r.get('outcome') not in OUTCOMES})
    if unknown: raise ValueError(f'{w}d contains unsupported outcomes: {unknown}')
    if not rows: raise ValueError(f'{w}d contains no SHORT rows')
    return data, rows

def main():
    windows, reports = {}, {}
    for w in WINDOWS:
        source, rows = load_window(w)
        windows[w] = rows
        reports[str(w)] = {
            'source_summary':source.get('summary',{}).get('outcomes',{}),
            'baseline':outcome_counts(rows),
            'tp3_vs_sl_feature_distributions':cohort(rows),
            'by_symbol':grouped(rows,'symbol'),
            'chronological_thirds':thirds(rows),
        }
    pooled = [r for w in WINDOWS for r in windows[w]]
    report = {
        'research_only':True,
        'production_strategy_changed':False,
        'long_logic_changed':False,
        'risk_or_sl_tp_geometry_changed':False,
        'decision':'NO_PRODUCTION_CHANGE',
        'purpose':'Compare actual TP3_HIT and SL_HIT indicator distributions and planned entry-to-SL distance. Descriptive diagnostics only; no thresholds, candidate approval, or production gate are generated.',
        'feature_fields_used':list(FEATURES),
        'windows':reports,
        'pooled_descriptive_counts':outcome_counts(pooled),
        'pooled_tp3_vs_sl_feature_distributions':cohort(pooled),
        'interpretation_guardrails':[
            'TP3 rate is TP3_HIT divided by TP3_HIT plus SL_HIT; EXPIRED is reported separately.',
            'Planned entry-to-SL distance is measured from entry and SL for every row, not only SL_HIT rows.',
            'A feature distribution difference is association, not proof of causality or a production-ready threshold.',
            'Check window, symbol, and chronological-third consistency before proposing any single indicator change.',
            'No LONG, risk engine, SL/TP geometry, or production strategy changes are made.'
        ]
    }
    OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'output':str(OUT),'windows':{w:reports[str(w)]['baseline'] for w in WINDOWS},'pooled':report['pooled_descriptive_counts']},indent=2))

if __name__ == '__main__': main()
