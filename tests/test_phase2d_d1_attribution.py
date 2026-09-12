from ai.attribution import ATTRIBUTION_VERSION, build_attribution


def test_attribution_schema_and_rounding():
    result = build_attribution(
        trend_component=28.004,
        quality_component=17.605,
        rs_component=14.404,
        oi_component=6.666,
        rr_component=6.401,
        sr_component=3.333,
        category_component=1.999,
        ai_rank_score=78.412,
        ai_rank_raw=78.412,
    )

    assert result["attribution_version"] == ATTRIBUTION_VERSION == "2D-D1"
    assert result["ai_rank_score"] == 78.41
    assert result["ai_rank_raw"] == 78.41
    assert result["components"] == {
        "trend": 28.0,
        "quality": 17.61,
        "rs": 14.4,
        "oi": 6.67,
        "rr": 6.4,
        "sr": 3.33,
        "category": 2.0,
    }


def test_attribution_preserves_aggregate_independently():
    # Attribution is a snapshot of existing rank outputs; it must not
    # recalculate or assume that arbitrary fixture components sum to the rank.
    result = build_attribution(
        trend_component=10,
        quality_component=20,
        rs_component=30,
        oi_component=4,
        rr_component=5,
        sr_component=2,
        category_component=1,
        ai_rank_score=81.5,
        ai_rank_raw=81.53,
    )

    assert result["ai_rank_score"] == 81.5
    assert result["ai_rank_raw"] == 81.53
    assert sum(result["components"].values()) == 72
    assert sum(result["components"].values()) != result["ai_rank_score"]


def test_attribution_does_not_mutate_inputs():
    result = build_attribution(
        trend_component=10,
        quality_component=20,
        rs_component=30,
        oi_component=4,
        rr_component=5,
        sr_component=2,
        category_component=1,
        ai_rank_score=72,
        ai_rank_raw=72,
    )

    assert result["ai_rank_score"] == 72.0
    assert result["ai_rank_raw"] == 72.0
    assert sum(result["components"].values()) == 72
