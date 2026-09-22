import pandas as pd

from config import CONFIG
from loaders.market_data_loader import MarketDataLoader


class FakeExchange:
    def __init__(self):
        self.calls = []

    def fetch_ohlcv(self, symbol, timeframe, limit):
        self.calls.append((symbol, timeframe, limit))
        rows = []
        for i in range(limit):
            ts = 1_700_000_000_000 + i * 3_600_000
            price = 100.0 + i
            rows.append([ts, price, price + 1, price - 1, price, 10.0])
        return rows


def make_loader():
    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = FakeExchange()
    loader._ohlcv_cache = {}
    return loader


def test_repeated_same_market_request_fetches_once():
    loader = make_loader()

    first = loader.get_15m("ETH/USDT:USDT")
    second = loader.get_15m("ETH/USDT:USDT")

    assert len(loader.exchange.calls) == 1
    assert loader.exchange.calls[0] == (
        "ETH/USDT:USDT",
        "15m",
        CONFIG["ohlcv_limit"],
    )
    assert first.equals(second)
    assert first is not second


def test_cache_key_includes_limit():
    loader = make_loader()

    loader.get_4h("ETH/USDT:USDT", limit=100)
    loader.get_4h("ETH/USDT:USDT", limit=80)

    assert len(loader.exchange.calls) == 2
    assert loader.exchange.calls == [
        ("ETH/USDT:USDT", "4h", 100),
        ("ETH/USDT:USDT", "4h", 80),
    ]


def test_4h_default_uses_authoritative_config_window():
    loader = make_loader()

    loader.get_4h("ETH/USDT:USDT")

    assert loader.exchange.calls == [
        ("ETH/USDT:USDT", "4h", CONFIG["ohlcv_4h_limit"]),
    ]
    assert CONFIG["ohlcv_4h_limit"] >= 60


def test_cached_frame_isolated_from_caller_mutation():
    loader = make_loader()

    first = loader.get_1h("ETH/USDT:USDT")
    first.loc[0, "close"] = -999.0
    second = loader.get_1h("ETH/USDT:USDT")

    assert second.loc[0, "close"] != -999.0
    assert len(loader.exchange.calls) == 1


def test_btc_1h_failure_is_cached_as_explicit_unavailable_state():
    class FailingExchange:
        def __init__(self):
            self.calls = 0

        def fetch_ohlcv(self, symbol, timeframe, limit):
            self.calls += 1
            raise RuntimeError("temporary exchange failure")

    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = FailingExchange()
    loader._ohlcv_cache = {}

    first = loader.get_1h(CONFIG["btc_symbol"], limit=100)
    second = loader.get_1h(CONFIG["btc_symbol"], limit=100)

    assert loader.exchange.calls == 1
    assert bool(first.attrs["btc_data_unavailable"])
    assert bool(second.attrs["btc_data_unavailable"])
    assert bool(second.attrs["btc_market_data"])
    assert len(second) == 1


def test_rejects_duplicate_exchange_timestamps():
    class DuplicateExchange:
        def fetch_ohlcv(self, symbol, timeframe, limit):
            base = 1_700_000_000_000
            return [
                [base, 100, 101, 99, 100, 10],
                [base, 101, 102, 100, 101, 10],
                [base, 101, 102, 100, 101, 10],
            ]

    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = DuplicateExchange()
    loader._ohlcv_cache = {}

    import pytest
    with pytest.raises(ValueError, match="duplicate_exchange_timestamps"):
        loader.get_5m("ETH/USDT:USDT", limit=3)


def test_rejects_non_monotonic_exchange_timestamps():
    class NonMonotonicExchange:
        def fetch_ohlcv(self, symbol, timeframe, limit):
            base = 1_700_000_000_000
            return [
                [base, 100, 101, 99, 100, 10],
                [base + 10_000, 101, 102, 100, 101, 10],
                [base + 5_000, 102, 103, 101, 102, 10],
            ]

    loader = MarketDataLoader.__new__(MarketDataLoader)
    loader.exchange = NonMonotonicExchange()
    loader._ohlcv_cache = {}

    import pytest
    with pytest.raises(ValueError, match="non_monotonic_exchange_timestamps"):
        loader.get_5m("ETH/USDT:USDT", limit=3)
