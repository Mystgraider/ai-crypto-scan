from pathlib import Path

SCANNER = Path(__file__).resolve().parents[1] / "scanner_v5.py"


def _scanner_source():
    return SCANNER.read_text(encoding="utf-8")


def test_scanner_prefilters_rrce_stage1_before_lower_timeframe_fetches():
    source = _scanner_source()

    prefilter = source.index("rrce_stage1_prefilter = {}")
    fetch_5m = source.index("market_loader.get_5m(symbol)")
    fetch_4h = source.index("market_loader.get_4h(symbol)")

    assert prefilter < fetch_5m
    assert prefilter < fetch_4h


def test_scanner_has_stage1_fail_fast_before_funding_prefetch():
    source = _scanner_source()

    prefilter = source.index("rrce_stage1_prefilter = {}")
    funding = source.index("funding_result_base =")
    fail_fast = source.index('skip[_fail_key] = skip.get(_fail_key, 0) + 1')

    assert prefilter < funding
    assert fail_fast < funding


def test_scanner_keeps_shared_15m_fetch_for_stage1_and_defers_5m():
    source = _scanner_source()

    first_15m = source.index("market_loader.get_15m(symbol)")
    first_5m = source.index("market_loader.get_5m(symbol)")

    assert first_15m < first_5m
    assert "defer 5m/4h network" in source
