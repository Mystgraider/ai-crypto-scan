def should_skip_trade(
    momentum,
    volatility,
    volume,
    regime
):

    if not momentum["strong"]:
        return True, "Weak momentum"

    if not volatility["active"]:
        return True, "Low volatility"

    if not volume["strong_volume"]:
        return True, "Weak volume"

    if regime == "dead_market":
        return True, "Dead market"

    return False, "Valid setup"
