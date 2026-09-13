import pandas as pd

from engines.btc_filter import BTCFilter


def test_unexpected_analysis_error_fails_closed():
    # Deliberately provide malformed 1H data so analysis raises internally.
    df = pd.DataFrame({"close": [100.0, 101.0]})

    result = BTCFilter().analyze(df)

    assert result["regime"] == "UNKNOWN"
    assert result["allow_long"] is False
    assert result["allow_short"] is False
    assert "no signals" in result["reason"].lower()
