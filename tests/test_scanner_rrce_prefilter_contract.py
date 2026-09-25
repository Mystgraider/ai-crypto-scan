from pathlib import Path

SCANNER = Path(__file__).resolve().parents[1] / "scanner_v5.py"


def _scanner_source():
    return SCANNER.read_text(encoding="utf-8")


def test_scanner_prefilters_rrce_stage1_after_4h_and_before_5m_fetches():
    source = _scanner_source()

    prefilter = source.index("rrce_stage1_prefilter = {}")
    fetch_4h = source.index("market_loader.get_4h(symbol)")
    fetch_5m = source.index("market_loader.get_5m(symbol)")

    # V6.9 contract: Stage 1 must use 4H range data, while 5m is
    # deferred until after the Stage-1 prefilter.
    assert fetch_4h < prefilter
    assert prefilter < fetch_5m


def test_scanner_has_stage1_fail_fast_before_funding_prefetch():
    source = _scanner_source()

    prefilter = source.index("rrce_stage1_prefilter = {}")
    funding = source.index("funding_result_base =")
    fail_fast = source.index('skip[_fail_key] = skip.get(_fail_key, 0) + 1')

    assert prefilter < funding
    assert fail_fast < funding


def test_scanner_keeps_15m_confirmation_fetch_before_5m_execution_fetch():
    source = _scanner_source()

    first_15m = source.index("market_loader.get_15m(symbol)")
    first_5m = source.index("market_loader.get_5m(symbol)")

    assert first_15m < first_5m
