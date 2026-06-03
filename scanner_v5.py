from loaders.top_symbols_loader import (
    TopSymbolsLoader
)

from loaders.market_data_loader import (
    MarketDataLoader
)

from indicators import Indicators

from engines.trend_engine import (
    TrendEngine
)


def main():

    symbols_loader = (
        TopSymbolsLoader()
    )

    market_loader = (
        MarketDataLoader()
    )

    trend_engine = (
        TrendEngine()
    )

    symbols = (
        symbols_loader.get_top_symbols()
    )

    print(
        f"Loaded {len(symbols)} symbols"
    )

    for symbol in symbols[:10]:

        try:

            df = (
                market_loader.get_ohlcv(
                    symbol,
                    timeframe="1h",
                    limit=100
                )
            )

            df = (
                Indicators.apply(df)
            )

            latest = df.iloc[-1]

            trend = (
                trend_engine.analyze(

                    price=latest["close"],

                    ema20=latest["ema20"],

                    ema50=latest["ema50"]
                )
            )

            print(

                symbol,

                trend["direction"],

                trend["score"]
            )

        except Exception as e:

            print(
                f"{symbol} -> {e}"
            )


if __name__ == "__main__":

    main()
