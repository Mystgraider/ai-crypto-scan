"""RRCE Engine — restored strategy semantics on the production 4H -> 1H -> 15m -> 5m path.

Restored V6.7.2 semantics:
- liquidity is a recent swing liquidity level; equal-high/equal-low pools are not mandatory;
- CHOCH is required; BOS is optional;
- FVG and OB are alternative entry-zone structures;
- structure uses closed/knowable candles only;
- Stage 3 starts only after the completed 1H sweep.
"""
import pandas as pd
import numpy as np


class RRCEEngine:

    def __init__(self, swing_lookback: int = 10, eq_tolerance_pct: float = 0.15):
        self.swing_lookback = swing_lookback
        self.eq_tolerance_pct = eq_tolerance_pct

    @staticmethod
    def live_entry_levels(direction: str, live_price: float, stage4: dict,
                          max_deviation_pct: float, min_rr: float) -> dict:
        """Validate a live fill against the RRCE pullback zone."""
        if not stage4:
            return {"valid": False, "reason": "missing_stage4"}
        if stage4.get("valid") is not True:
            return {"valid": False, "reason": "invalid_stage4"}

        planned_entry = float(stage4["entry"])
        sl = float(stage4["sl"])
        tp = float(stage4["tp"])
        if planned_entry <= 0 or live_price <= 0:
            return {"valid": False, "reason": "invalid_price"}

        deviation_pct = abs(live_price - planned_entry) / planned_entry * 100
        if deviation_pct > max_deviation_pct:
            return {
                "valid": False,
                "reason": "price_away_from_rrce_entry",
                "planned_entry": planned_entry,
                "deviation_pct": round(deviation_pct, 3),
            }

        if direction == "LONG":
            valid_structure = sl < live_price < tp
        elif direction == "SHORT":
            valid_structure = tp < live_price < sl
        else:
            return {"valid": False, "reason": "invalid_direction"}

        if not valid_structure:
            return {"valid": False, "reason": "invalid_live_structure"}

        risk = abs(live_price - sl)
        reward = abs(tp - live_price)
        rr = reward / risk if risk else 0.0
        if rr < min_rr:
            return {"valid": False, "reason": "rr_below_minimum", "rr": round(rr, 2)}

        return {
            "valid": True,
            "entry": live_price,
            "sl": sl,
            "tp1": tp,
            "tp2": tp,
            "tp3": tp,
            "rr": round(rr, 2),
            "planned_entry": planned_entry,
            "deviation_pct": round(deviation_pct, 3),
        }

    # ── shared helper ────────────────────────────────────────────────────
    def _find_swings(self, df: pd.DataFrame, n: int = None) -> pd.DataFrame:
        n = n or self.swing_lookback
        # Structure must never be allowed to use the currently-forming candle
        # as the "future" confirmation bar for a swing point.
        d = df.iloc[:-1].copy() if len(df) >= 2 else df.iloc[0:0].copy()
        d["swing_high"] = d["high"].where(
            d["high"] == d["high"].rolling(2 * n + 1, center=True).max()
        )
        d["swing_low"] = d["low"].where(
            d["low"] == d["low"].rolling(2 * n + 1, center=True).min()
        )
        return d

    def _find_swings_v69_shadow(self, df: pd.DataFrame, n: int = None) -> pd.DataFrame:
        """Raw V6.9 shadow swing detector; intentionally keeps the forming row."""
        n = n or self.swing_lookback
        d = df.copy()
        d["swing_high"] = d["high"].where(
            d["high"] == d["high"].rolling(2 * n + 1, center=True).max()
        )
        d["swing_low"] = d["low"].where(
            d["low"] == d["low"].rolling(2 * n + 1, center=True).min()
        )
        return d

    def stage1_v69_shadow(self, df_htf: pd.DataFrame, direction: str, price: float,
                          lookback: int = 60) -> dict | None:
        """Non-blocking replay of raw V6.9 Stage 1 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None
        range_high = float(highs.max())
        range_low = float(lows.min())
        if range_high <= range_low:
            return None
        midpoint = (range_high + range_low) / 2.0
        position_pct = (price - range_low) / (range_high - range_low) * 100
        passed = price <= midpoint if direction == "LONG" else price >= midpoint
        return {"passed": bool(passed), "range_high": range_high,
                "range_low": range_low, "position_pct": round(position_pct, 1)}

    def stage2_v69_shadow(self, df_mtf: pd.DataFrame, direction: str,
                          range_low: float, range_high: float,
                          proximity_pct: float = 5.0, lookback: int = 80) -> dict | None:
        """Non-blocking replay of raw V6.9 Stage 2 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_mtf).tail(lookback)
        if len(df_mtf) < 2:
            return None
        last = df_mtf.iloc[-2]
        if direction == "LONG":
            pools = self._equal_levels(d["swing_low"].dropna().tolist())
            near = [p for p in pools if abs(p["level"] - range_low) / range_low * 100 <= proximity_pct]
            if not near:
                return {"passed": False, "reason": "no_equal_lows_near_range_low"}
            pool = min(near, key=lambda p: abs(p["level"] - range_low))
            swept = float(last["low"]) < pool["level"] and float(last["close"]) > pool["level"]
        elif direction == "SHORT":
            pools = self._equal_levels(d["swing_high"].dropna().tolist())
            near = [p for p in pools if abs(p["level"] - range_high) / range_high * 100 <= proximity_pct]
            if not near:
                return {"passed": False, "reason": "no_equal_highs_near_range_high"}
            pool = min(near, key=lambda p: abs(p["level"] - range_high))
            swept = float(last["high"]) > pool["level"] and float(last["close"]) < pool["level"]
        else:
            return None
        return {"passed": bool(swept), "reason": None if swept else "pool_found_not_swept"}

    def stage3_v69_shadow(self, df_ltf: pd.DataFrame, direction: str,
                           lookback: int = 60) -> dict | None:
        """Non-blocking replay of the raw V6.9 Stage 3 for diagnostics only."""
        d = self._find_swings_v69_shadow(df_ltf).tail(lookback)
        if len(df_ltf) < 3:
            return {"passed": False, "reason": "insufficient_closed_candles"}
        last_close = float(df_ltf["close"].iloc[-2])
        if direction == "LONG":
            levels = d["swing_high"].dropna()
            if levels.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(levels.iloc[-1])
            choch = last_close > choch_level
        elif direction == "SHORT":
            levels = d["swing_low"].dropna()
            if levels.empty:
                return {"passed": False, "reason": "no_structure"}
            choch_level = float(levels.iloc[-1])
            choch = last_close < choch_level
        else:
            return {"passed": False, "reason": "invalid_direction"}
        if not choch:
            return {"passed": False, "reason": "no_choch", "choch_level": choch_level}
        fvg = self._detect_fvg_near_v69_shadow(df_ltf, direction)
        if not fvg:
            return {"passed": False, "reason": "choch_without_fvg", "choch_level": choch_level}
        return {"passed": True, "choch_level": choch_level, "fvg": fvg,
                "break_idx": len(df_ltf) - 2,
                "break_time": df_ltf["timestamp"].iloc[-2] if "timestamp" in df_ltf.columns else None}

    def _detect_fvg_near_v69_shadow(self, df: pd.DataFrame, direction: str,
                                    lookback: int = 10) -> dict | None:
        d = df.tail(lookback + 2).reset_index(drop=True)
        for i in range(2, len(d)):
            c0, c2 = d.iloc[i - 2], d.iloc[i]
            if direction == "LONG" and c2["low"] > c0["high"]:
                return {"top": float(c2["low"]), "bottom": float(c0["high"]), "break_idx": i}
            if direction == "SHORT" and c2["high"] < c0["low"]:
                return {"top": float(c0["low"]), "bottom": float(c2["high"]), "break_idx": i}
        return None

    # ── Stage 1: RANGE (HTF) ─────────────────────────────────────────────
    def stage1_range(self, df_htf: pd.DataFrame, direction: str, price: float,
                      lookback: int = 45, zone_threshold_pct: float = 60.0) -> dict | None:
        d = self._find_swings(df_htf).tail(lookback)
        highs = d["swing_high"].dropna()
        lows  = d["swing_low"].dropna()
        if highs.empty or lows.empty:
            return None

        # V6.9 contract: the HTF range is the swing envelope over the
        # configured lookback — highest confirmed swing high and lowest
        # confirmed swing low. Do not replace this with an alternating
        # "latest high/latest low pair"; that changes the range itself and
        # can move the Discount/Premium boundary between decisions.
        range_high = float(highs.max())
        range_low = float(lows.min())
        last_high_idx = highs.idxmax()
        last_low_idx = lows.idxmin()

        if range_high <= range_low:
            return None

        midpoint = (range_high + range_low) / 2.0
        range_width_pct = (range_high - range_low) / range_low * 100 if range_low else None
        position_pct = (price - range_low) / (range_high - range_low) * 100

        def _timestamp_for(idx):
            if "timestamp" not in df_htf.columns or idx not in df_htf.index:
                return None
            try:
                return str(df_htf.loc[idx, "timestamp"])
            except Exception:
                return None

        range_high_time = _timestamp_for(last_high_idx)
        range_low_time = _timestamp_for(last_low_idx)

        # A structural range is only valid while price is inside that
        # range. Without this bound, LONG setups below range_low and SHORT
        # setups above range_high can pass the one-sided discount/premium
        # test, producing negative or >100% position_pct values.
        inside_range = 0.0 <= position_pct <= 100.0

        if direction == "LONG":
            zone_ok = inside_range and position_pct <= zone_threshold_pct
            zone = "discount"
        elif direction == "SHORT":
            zone_ok = inside_range and position_pct >= (100 - zone_threshold_pct)
            zone = "premium"
        else:
            zone_ok = False
            zone = "invalid"

        return {
            "passed": zone_ok,
            "range_high": range_high,
            "range_low": range_low,
            "midpoint": midpoint,
            "zone": zone,
            "position_pct": round(position_pct, 1),
            "range_width_pct": round(range_width_pct, 4) if range_width_pct is not None else None,
            "range_high_time": range_high_time,
            "range_low_time": range_low_time,
            "range_high_index": str(last_high_idx),
            "range_low_index": str(last_low_idx),
            "price_above_range_high_pct": round((price - range_high) / range_high * 100, 4) if range_high else None,
            "price_below_range_low_pct": round((range_low - price) / range_low * 100, 4) if range_low else None,
        }

    # ── Stage 2: RETAIL LIQUIDITY (MTF) ──────────────────────────────────
    def _equal_levels(self, levels: list[float]) -> list[dict]:
        """Groups nearby levels (within eq_tolerance_pct) into pools of 2+."""
        if len(levels) < 2:
            return []
        levels = sorted(levels)
        pools, current = [], [levels[0]]
        for lvl in levels[1:]:
            ref = current[-1]
            if ref != 0 and abs(lvl - ref) / abs(ref) * 100 <= self.eq_tolerance_pct:
                current.append(lvl)
            else:
                if len(current) >= 2:
                    pools.append(current)
                current = [lvl]
        if len(current) >= 2:
            pools.append(current)
        return [{"level": float(np.mean(p)), "touches": len(p)} for p in pools]

    def stage2_retail_liquidity(self, df_mtf: pd.DataFrame, direction: str,
                                 range_low: float, range_high: float,
                                 proximity_pct: float = 5.0, lookback: int = 80,
                                 patience_bars: int = 6) -> dict | None:
        """Detect a recent swing-liquidity sweep using restored V6.7.2 semantics."""
        pool_window_start=max(0,len(df_mtf)-(patience_bars+1))
        d=self._find_swings(df_mtf.iloc[:pool_window_start]).tail(lookback)
        window=df_mtf.iloc[-(patience_bars+1):-1]
        if window.empty:return {"passed":False,"reason":"empty_sweep_window","pools":[]}
        if direction=="LONG":
            levels=d["swing_low"].dropna()
            if levels.empty:return {"passed":False,"reason":"no_liquidity_swing_low","pools":[]}
            level=float(levels.iloc[-1]); mask=(window["low"]<level)&(window["close"]>level); side="low"
        elif direction=="SHORT":
            levels=d["swing_high"].dropna()
            if levels.empty:return {"passed":False,"reason":"no_liquidity_swing_high","pools":[]}
            level=float(levels.iloc[-1]); mask=(window["high"]>level)&(window["close"]<level); side="high"
        else:return {"passed":False,"reason":"invalid_direction","pools":[]}
        extreme=range_low if direction=="LONG" else range_high
        dist=abs(level-extreme)/abs(extreme)*100 if extreme else None
        base={"pools":[{"level":level,"touches":1}],"near_pool_count":1,"all_pool_count":1,
              "pool_level":level,"pool_side":side,"pool_distance_from_range_extreme_pct":round(dist,4) if dist is not None else None,
              "proximity_pct":float(proximity_pct),"patience_bars":int(patience_bars)}
        if not bool(mask.any()):return {"passed":False,"reason":"pool_found_not_swept",**base}
        idx=mask[mask].index[-1]
        candle_time=window.loc[idx,"timestamp"] if "timestamp" in window.columns else None
        sweep_time=pd.to_datetime(candle_time,utc=True,errors="raise")+pd.Timedelta(hours=1) if candle_time is not None else None
        sweep_extreme=float(window.loc[idx,"low"] if direction=="LONG" else window.loc[idx,"high"])
        return {"passed":True,"reason":None,**base,"sweep_candle_time":str(candle_time) if candle_time is not None else None,
                "sweep_time":str(sweep_time) if sweep_time is not None else None,"sweep_extreme":sweep_extreme}

    def _detect_fvg_near(self, df: pd.DataFrame, direction: str,
                         lookback: int = 10, break_idx: int = None) -> dict | None:
        """Detect a recent FVG; it is not required to be the exact CHOCH candle."""
        if break_idx is not None:
            end=min(int(break_idx),len(df)-1)
            start=max(0,end-lookback-1)
            d=df.iloc[start:end+1].reset_index(drop=True)
        else:
            d=df.tail(lookback+2).reset_index(drop=True)
        for i in range(2,len(d)):
            c0,c2=d.iloc[i-2],d.iloc[i]
            if direction=="LONG" and c2["low"]>c0["high"]:
                return {"top":float(c2["low"]),"bottom":float(c0["high"]),"break_idx":i}
            if direction=="SHORT" and c2["high"]<c0["low"]:
                return {"top":float(c0["low"]),"bottom":float(c2["high"]),"break_idx":i}
        return None

    def stage3_confirmation(self, df_ltf: pd.DataFrame, direction: str,
                            lookback: int = 60, sweep_time=None,
                            confirmation_bars: int = 3) -> dict | None:
        """Confirm CHOCH after sweep; FVG is optional and not tied to the exact break candle."""
        closed=df_ltf.iloc[:-1].copy() if len(df_ltf)>=2 else df_ltf.iloc[0:0].copy()
        if len(closed)<5:return {"passed":False,"reason":"insufficient_closed_candles"}
        bars=max(1,int(confirmation_bars))
        if sweep_time is not None:
            if "timestamp" not in closed.columns:return {"passed":False,"reason":"missing_ltf_timestamp"}
            try:
                sweep_ts=pd.to_datetime(sweep_time,utc=True,errors="raise"); ts=pd.to_datetime(closed["timestamp"],utc=True,errors="raise")
            except (TypeError,ValueError,OverflowError):return {"passed":False,"reason":"invalid_sweep_timestamp"}
            candidates=[i for i in range(len(closed)) if i>=2 and ts.iloc[i]>sweep_ts][:bars]
        else:candidates=list(range(max(2,len(closed)-bars),len(closed)))
        for break_idx in candidates:
            structure=self._find_swings(closed.iloc[:break_idx+1],n=self.swing_lookback).tail(lookback)
            levels=(structure["swing_high"] if direction=="LONG" else structure["swing_low"]).dropna()
            if levels.empty:continue
            level=float(levels.iloc[-1]); close=float(closed["close"].iloc[break_idx])
            if not (close>level if direction=="LONG" else close<level):continue
            return {"passed":True,"choch":True,"bos":False,"choch_level":level,
                    "fvg":self._detect_fvg_near(closed,direction,break_idx=None),
                    "break_idx":break_idx,
                    "break_time":closed["timestamp"].iloc[break_idx] if "timestamp" in closed.columns else None,
                    "structure_lookback":self.swing_lookback,"fvg_exact_choch_required":False}
        return {"passed":False,"reason":"no_choch","saw_choch":False}

    # ── Stage 4: EXECUTION (LTF, finest) ─────────────────────────────────
    def _order_block(self, df: pd.DataFrame, direction: str, break_idx: int = None,
                      lookback: int = 15) -> dict | None:
        """Legacy OB: opposite-colored candle before an impulsive move."""
        end=min(max(2,break_idx if break_idx is not None else len(df)-2),len(df)-1); start=max(2,end-lookback)
        for i in range(end,start-1,-1):
            impulse=df.iloc[i]; body=abs(float(impulse["close"])-float(impulse["open"]))
            prior=(df.iloc[max(0,i-10):i]["close"]-df.iloc[max(0,i-10):i]["open"]).abs(); avg=float(prior.mean()) if len(prior) else 0.0
            prev=df.iloc[i-1]
            if avg>0 and body<=1.5*avg:continue
            if direction=="LONG" and impulse["close"]>impulse["open"] and prev["close"]<prev["open"]:
                return {"top":float(prev["high"]),"bottom":float(prev["low"]),"anchored":False,"impulsive":True}
            if direction=="SHORT" and impulse["close"]<impulse["open"] and prev["close"]>prev["open"]:
                return {"top":float(prev["high"]),"bottom":float(prev["low"]),"anchored":False,"impulsive":True}
        return None

    def stage4_execution(self, df_exec: pd.DataFrame, direction: str, fvg: dict | None,
                          sweep_extreme: float, opposite_pool_level: float, break_idx: int = None,
                          max_rr_cap: float = 4.0) -> dict:
        """Use FVG OR OB for the entry zone."""
        ob=self._order_block(df_exec,direction,break_idx=break_idx)
        if ob:entry=(ob["top"]+ob["bottom"])/2.0; zone="OB"
        elif fvg:entry=(float(fvg["top"])+float(fvg["bottom"]))/2.0; zone="FVG"
        else:return {"valid":False,"reason":"no_fvg_or_order_block"}
        atr=None
        if "atr" in df_exec.columns:
            ai=break_idx if break_idx is not None else len(df_exec)-2
            if 0<=ai<len(df_exec):
                v=df_exec["atr"].iloc[ai]
                if not pd.isna(v) and float(v)>0:atr=float(v)
        buffer=atr*0.3 if atr is not None else abs(entry)*0.003
        sl=sweep_extreme-buffer if direction=="LONG" else sweep_extreme+buffer; risk=abs(entry-sl)
        if risk<=0:return {"valid":False,"reason":"invalid_risk"}
        raw=float(opposite_pool_level); cap=entry+max_rr_cap*risk if direction=="LONG" else entry-max_rr_cap*risk
        tp=min(raw,cap) if direction=="LONG" and raw>entry else (max(raw,cap) if direction=="SHORT" and raw<entry else cap)
        return {"valid":True,"entry":round(entry,8),"sl":round(sl,8),"tp":round(tp,8),"rr":round(abs(tp-entry)/risk,2),
                "order_block":ob,"fvg":fvg,"entry_zone":zone}

    # ── Full sequence ────────────────────────────────────────────────────
    def evaluate(self, df_htf: pd.DataFrame, df_mtf: pd.DataFrame,
                 df_ltf_confirm: pd.DataFrame, df_ltf_exec: pd.DataFrame,
                 direction: str, price: float, patience_bars: int = 6, confirmation_bars: int = 3) -> dict:
        """Run the restored RRCE sequence."""
        result={"valid":False,"failed_at":None,"stage1":None,"stage2":None,"stage3":None,"stage4":None,"bonus":0.0}
        s1=self.stage1_range(df_htf,direction,price); result["stage1"]=s1
        if not s1 or not s1["passed"]:result["failed_at"]="stage1_range";return result
        s2=self.stage2_retail_liquidity(df_mtf,direction,s1["range_low"],s1["range_high"],patience_bars=patience_bars);result["stage2"]=s2
        if not s2 or not s2["passed"]:result["failed_at"]="stage2_retail_liquidity";return result
        s3=self.stage3_confirmation(df_ltf_confirm,direction,sweep_time=s2.get("sweep_time"),confirmation_bars=confirmation_bars);result["stage3"]=s3
        if not s3 or not s3["passed"]:result["failed_at"]="stage3_confirmation";return result
        bi=s3.get("break_idx")
        if bi is None or "timestamp" not in df_ltf_confirm.columns or "timestamp" not in df_ltf_exec.columns:
            result["failed_at"]="stage3_dataframe_alignment";result["stage3"]["reason"]="missing_execution_timestamp_or_break_idx";return result
        try:cts=pd.to_datetime(df_ltf_confirm["timestamp"].iloc[bi],utc=True,errors="raise");ets=pd.to_datetime(df_ltf_exec["timestamp"],utc=True,errors="raise")
        except (TypeError,ValueError,OverflowError):result["failed_at"]="stage3_dataframe_alignment";result["stage3"]["reason"]="invalid_execution_timestamp";return result
        matches=[i for i,t in enumerate(ets) if t==cts]
        if len(matches)!=1:
            result["failed_at"]="stage3_dataframe_alignment";result["stage3"]["reason"]="execution_candle_not_found" if not matches else "multiple_execution_candles_at_break_time";return result
        ebi=matches[0];result["stage3"]["execution_break_idx"]=ebi;result["stage3"]["execution_break_time"]=str(cts)
        opposite=s1["range_high"] if direction=="LONG" else s1["range_low"]
        s4=self.stage4_execution(df_ltf_exec,direction,s3.get("fvg"),s2["sweep_extreme"],opposite,break_idx=ebi);result["stage4"]=s4
        if not s4.get("valid"):result["failed_at"]="stage4_execution";return result
        result["valid"]=True;result["bonus"]=15.0;return result