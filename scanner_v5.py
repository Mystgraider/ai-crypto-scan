--- a/scanner_v5.py
+++ b/scanner_v5.py
@@
-    rrce_engine    = RRCEEngine()
+    # Allow runtime override via CONFIG (safe toggle). Default 0.15 in engine
+    rrce_eq_override = CONFIG.get("rrce_eq_tolerance_override")
+    if rrce_eq_override is not None:
+        rrce_engine = RRCEEngine(eq_tolerance_pct=float(rrce_eq_override))
+    else:
+        rrce_engine    = RRCEEngine(eq_tolerance_pct=0.6)
@@
-    experiment_4h_engine = RRCEEngine(swing_lookback=10, eq_tolerance_pct=0.6)
+    experiment_4h_engine = RRCEEngine(swing_lookback=10, eq_tolerance_pct=0.6)
