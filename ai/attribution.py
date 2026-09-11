"""AI rank component attribution helpers.

Phase 2D-D1: exposes the already-computed rank components for evidence logging.
This module does not change ranking weights, thresholds, or trading decisions.
"""

ATTRIBUTION_VERSION = "2D-D1"


def build_attribution(*, trend_component: float, quality_component: float,
                       rs_component: float, oi_component: float,
                       rr_component: float, sr_component: float,
                       category_component: float, ai_rank_score: float,
                       ai_rank_raw: float) -> dict:
    """Return a read-only attribution snapshot from existing rank outputs."""
    components = {
        "trend": round(float(trend_component), 2),
        "quality": round(float(quality_component), 2),
        "rs": round(float(rs_component), 2),
        "oi": round(float(oi_component), 2),
        "rr": round(float(rr_component), 2),
        "sr": round(float(sr_component), 2),
        "category": round(float(category_component), 2),
    }
    return {
        "attribution_version": ATTRIBUTION_VERSION,
        "components": components,
        "ai_rank_raw": round(float(ai_rank_raw), 2),
        "ai_rank_score": round(float(ai_rank_score), 2),
    }
