from loaders.top_symbols_loader import TopSymbolsLoader
from loaders.market_data_loader import MarketDataLoader
from indicators import Indicators
from engines.trend_engine import TrendEngine
from alerts.telegram_alerts import send_telegram_alert
from storage.signal_logger import save_signal


def main():
    symbols_loader = TopSymbolsLoader()
    market_loader = MarketDataLoader()
    trend_engine = TrendEngine()

    symbols = symbols_loader.get_top_symbols()
    print(f"Loaded {len(symbols)} symbols")

    for symbol in symbols:
        try:
            df = market_loader.get_ohlcv(symbol, timeframe="1h", limit=100)
            df = Indicators.apply(df)

            latest = df.iloc[-1]

            trend = trend_engine.analyze(
                price=latest["close"],
                ema20=latest["ema_20"],
                ema50=latest["ema_50"]
            )

            print(symbol, trend["direction"], trend["score"])

            if trend["direction"] != "NONE" and trend["score"] >= 80:
                entry = float(latest["close"])
                atr = float(latest["atr"])

                if trend["direction"] == "LONG":
                    sl  = round(entry - (atr * 1.5), 6)
                    tp1 = round(entry + (atr * 2), 6)
                    tp2 = round(entry + (atr * 3), 6)
                    tp3 = round(entry + (atr * 5), 6)
                else:
                    sl  = round(entry + (atr * 1.5), 6)
                    tp1 = round(entry - (atr * 2), 6)
                    tp2 = round(entry - (atr * 3), 6)
                    tp3 = round(entry - (atr * 5), 6)

                message = (
                    f"🚨 V5 SIGNAL\n\n"
                    f"Coin: {symbol}\n"
                    f"Direction: {trend['direction']}\n"
                    f"Score: {round(trend['score'], 2)}\n\n"
                    f"Entry: {entry}\n"
                    f"SL: {sl}\n"
                    f"TP1: {tp1}\n"
                    f"TP2: {tp2}\n"
                    f"TP3: {tp3}"
                )

                send_telegram_alert(message)

                save_signal(
                    symbol=symbol,
                    direction=trend["direction"],
                    entry=entry,
                    sl=sl,
                    tp1=tp1,
                    tp2=tp2,
                    tp3=tp3,
                    score=trend["score"]
                )

        except Exception as e:
            print(f"{symbol} -> {e}")


if __name__ == "__main__":
    send_telegram_alert("✅ V5 Scanner Started")
    main()
