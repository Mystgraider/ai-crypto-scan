from loaders.top_symbols_loader import (
    TopSymbolsLoader
)

loader = TopSymbolsLoader()

symbols = (
    loader.get_top_symbols()
)

print(
    f"Symbols: {len(symbols)}"
)

print(
    symbols[:20]
)
