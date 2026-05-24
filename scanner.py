# =====================================
# MAIN SCAN
# =====================================

def scan_all():

    signal_times = load_signal_times()

    now = datetime.utcnow()

    print(f"\n[{now}] ELITE SCAN STARTED\n")

    btc_state = get_btc_market_state()

    print(f"BTC Trend: {btc_state['trend']}")
    print(f"BTC Volatility: {btc_state['volatility']}")

    if not btc_state["safe"]:

        print("High volatility detected")
        return

    ALL_SYMBOLS = get_top_symbols(TOP_COINS_LIMIT)

    signals_found = 0

    for symbol in ALL_SYMBOLS:

        try:

            # =====================================
            # COOLDOWN
            # =====================================

            if is_on_cooldown(symbol, signal_times, now):
                continue

            # =====================================
            # LIQUIDITY FILTER
            # =====================================

            ticker = exchange.fetch_ticker(symbol)

            quote_volume = ticker.get("quoteVolume", 0)

            if quote_volume < MIN_LIQUIDITY_USDT:
                continue

            # =====================================
            # 4H TREND
            # =====================================

            df_4h = load_ohlcv(
                symbol,
                "4h",
                limit=40
            )

            df_4h = apply_indicators(df_4h)

            direction = detect_trend(df_4h)

            if direction is None:
                continue

            # =====================================
            # BTC ALIGNMENT
            # =====================================

            if (
                btc_state["trend"] == "BULL"
                and direction != "bullish"
            ):
                continue

            if (
                btc_state["trend"] == "BEAR"
                and direction != "bearish"
            ):
                continue

            # =====================================
            # 1H DATA
            # =====================================

            df_1h = load_ohlcv(
                symbol,
                "1h",
                limit=40
            )

            df_1h = apply_indicators(df_1h)

            # =====================================
            # 15M DATA
            # =====================================

            df_15m = load_ohlcv(
                symbol,
                "15m",
                limit=40
            )

            df_15m = apply_indicators(df_15m)

            price = df_15m["close"].iloc[-2]

            atr_1h = df_1h["atr"].iloc[-2]

            rel_vol = df_15m["rel_vol"].iloc[-2]

            if rel_vol < 0.7:
                continue

            # =====================================
            # SIGNAL TYPE
            # =====================================

            signal = (
                "LONG 🟢"
                if direction == "bullish"
                else "SHORT 🔴"
            )

            # =====================================
            # ENTRY / TP / SL
            # =====================================

            sl_distance = max(
                atr_1h * 1.5,
                price * MIN_SL_PCT
            )

            if direction == "bullish":

                stop_loss = (
                    price - sl_distance
                )

                take_profit = (
                    price + (sl_distance * MIN_RR)
                )

            else:

                stop_loss = (
                    price + sl_distance
                )

                take_profit = (
                    price - (sl_distance * MIN_RR)
                )

            # =====================================
            # DECIMALS
            # =====================================

            if price < 0.0001:
                decimals = 10

            elif price < 0.01:
                decimals = 8

            elif price < 1:
                decimals = 6

            else:
                decimals = 4

            # =====================================
            # MESSAGE
            # =====================================

            message = (
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🏆 ELITE SIGNAL\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"🪙 {symbol}\n"
                f"📢 {signal}\n"
                f"🏦 Bitget Futures\n\n"
                f"BTC Trend: {btc_state['trend']}\n"
                f"Volatility: {btc_state['volatility']}\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📊 ANALYSIS\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"✅ Trend aligned\n"
                f"✅ Strong momentum\n"
                f"✅ Relative Volume: {round(rel_vol,2)}x\n\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🎯 EXECUTION\n"
                f"━━━━━━━━━━━━━━━━━━\n\n"
                f"💰 Entry: {round(price, decimals)}\n"
                f"🛑 Stop Loss: {round(stop_loss, decimals)}\n"
                f"🎯 Take Profit: {round(take_profit, decimals)}\n"
                f"⚖ RR: 1:{MIN_RR}\n"
            )

            # =====================================
            # OUTPUT
            # =====================================

            print(
                f"✅ SIGNAL: {symbol} {signal}"
            )

            print(message)

            send_telegram_alert(message)

            signal_times[symbol] = now

            signals_found += 1

            time.sleep(0.15)

        except Exception as e:

            print(
                f"ERROR {symbol}: {e}"
            )

    save_signal_times(signal_times)

    print(
        f"\nDONE: {signals_found} signals sent.\n"
    )

# =====================================
# ENTRY
# =====================================

if __name__ == "__main__":
    scan_all()
