"""
Volume Spike Detection Engine — Phase 4
=========================================
Detects unusual volume activity that often precedes
or confirms strong breakout moves.

Spike tiers:
  EXTREME  >= 4.0x avg  → very high conviction
  HIGH     >= 2.5x avg  → strong confirmation
  ELEVATED >= 1.5x avg  → moderate confirmation
  NORMAL   >= 1.0x avg  → baseline
  WEAK      < 1.0x avg  → no conviction
"""


class VolumeSpikeEngine:

    TIERS = [
        (4.0, "EXTREME",  100),
        (2.5, "HIGH",      85),
        (1.5, "ELEVATED",  70),
        (1.0, "NORMAL",    55),
        (0.0, "WEAK",      20),
    ]

    def analyze(self, rel_volume: float) -> dict:

        for threshold, label, score in self.TIERS:
            if rel_volume >= threshold:
                return {
                    "tier":        label,
                    "rel_volume":  round(rel_volume, 2),
                    "spike_score": score,
                    "is_spike":    rel_volume >= 1.5,
                }

        return {
            "tier":        "WEAK",
            "rel_volume":  round(rel_volume, 2),
            "spike_score": 20,
            "is_spike":    False,
        }
