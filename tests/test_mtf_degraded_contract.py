from engines.multiframe_engine import MultiFrameEngine


def test_degraded_4h_high_adx_uses_explicit_proxy_contract():
    result = MultiFrameEngine.degraded_4h_fallback(30.0)

    assert result == {
        "status": "ALLOWED",
        "multiplier": 0.95,
        "direction": "PROXY",
        "reason": "4H unavailable after retry; ADX >= 30 permits degraded proxy mode",
    }


def test_degraded_4h_low_adx_skips_without_proxy_direction():
    result = MultiFrameEngine.degraded_4h_fallback(29.99)

    assert result == {
        "status": "SKIPPED",
        "multiplier": 1.0,
        "direction": "UNKNOWN",
        "reason": "4H unavailable after retry; ADX < 30 does not permit degraded proxy mode",
    }


def test_degraded_4h_never_fabricates_bullish_or_bearish_direction():
    for adx in (0, 18, 29.99, 30, 50, 100):
        result = MultiFrameEngine.degraded_4h_fallback(adx)
        assert result["direction"] in {"PROXY", "UNKNOWN"}
        assert result["direction"] not in {"BULLISH", "BEARISH"}


def test_scanner_uses_centralized_degraded_4h_contract():
    from pathlib import Path

    scanner = (Path(__file__).resolve().parents[1] / "scanner_v5.py").read_text(
        encoding="utf-8"
    )

    assert "mtf_engine.degraded_4h_fallback(adx)" in scanner
    assert 'mtf_status = fallback["status"]' in scanner
    assert 'mtf_multiplier = fallback["multiplier"]' in scanner
    assert 'mtf_4h_dir = fallback["direction"]' in scanner

    # The degraded policy must not be duplicated inline in the production scanner.
    assert 'if adx >= 30:' not in scanner
    assert 'mtf_status     = "ALLOWED"' not in scanner
    assert 'mtf_4h_dir     = "PROXY"' not in scanner
