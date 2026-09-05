import json
from collections import Counter

P = "storage/scan_debug_log.jsonl"

def summarize(path=P):
    c = Counter()
    rows = 0
    stage1_positions = []
    stage2_pool_counts = []
    last_row = None
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    # try to recover by trimming trailing commas/brackets
                    try:
                        obj = json.loads(line.rstrip(', '))
                    except Exception:
                        continue
                rows += 1
                last_row = obj
                for k, v in obj.items():
                    if k.startswith('rrce_fail_') or k.startswith('rrce_stage'):
                        c[k] += int(v) if isinstance(v, int) else 0
                    if k.startswith('s2_reason_') or k.startswith('s3_reason_'):
                        c[k] += int(v) if isinstance(v, int) else 0
                # aggregated fields
                s1_count = obj.get('stage1_position_pct_count')
                if s1_count:
                    # try collecting sample via stage1_position_pct_* if present
                    # but the debug row only stores aggregated stats, not samples
                    pass
                s2_avg = obj.get('stage2_pool_count_avg')
                if s2_avg is not None:
                    try:
                        stage2_pool_counts.append(float(s2_avg))
                    except Exception:
                        pass
    except FileNotFoundError:
        print(f"File not found: {path}")
        return

    print("RRCE Failure Summary")
    print("=====================")
    print(f"Lines processed: {rows}")
    print("")
    if not rows:
        print("No rows found in log")
        return

    # Print rrce_fail counts
    rrce_keys = {k: v for k, v in c.items() if k.startswith('rrce_fail_')}
    if rrce_keys:
        print("RRCE fail counts:")
        for k, v in sorted(rrce_keys.items(), key=lambda x: x[1], reverse=True):
            print(f"  {k}: {v}")
    else:
        print("No rrce_fail_* keys found in the log (they may be zero or absent).")

    pass_keys = {k: v for k, v in c.items() if k.startswith('rrce_stage')}
    if pass_keys:
        print("\nRRCE pass-through counts:")
        for k, v in sorted(pass_keys.items()):
            print(f"  {k}: {v}")

    s2_keys = {k: v for k, v in c.items() if k.startswith('s2_reason_')}
    if s2_keys:
        print("\nStage2 (retail liquidity) reasons:")
        for k, v in sorted(s2_keys.items(), key=lambda x: x[1], reverse=True):
            print(f"  {k}: {v}")

    s3_keys = {k: v for k, v in c.items() if k.startswith('s3_reason_')}
    if s3_keys:
        print("\nStage3 (confirmation) reasons:")
        for k, v in sorted(s3_keys.items(), key=lambda x: x[1], reverse=True):
            print(f"  {k}: {v}")

    if stage2_pool_counts:
        avg = sum(stage2_pool_counts)/len(stage2_pool_counts)
        print(f"\nObserved avg stage2_pool_count_avg across rows: {avg:.2f} (from {len(stage2_pool_counts)} rows)")

    print("\nLast run summary (most recent debug row):")
    if last_row:
        # print selected fields
        keys = [
            'ts','symbols_scanned','candidates','btc_regime_label','btc_regime_allow_long','btc_regime_allow_short',
            'stage1_position_pct_count','stage1_position_pct_min','stage1_position_pct_max','stage1_position_pct_avg',
            'stage2_pool_count_avg','stage2_zero_pool_pct','rrce_invalid'
        ]
        for k in keys:
            if k in last_row:
                print(f"  {k}: {last_row.get(k)}")
    else:
        print("  (none)")

if __name__ == '__main__':
    summarize()
