def analyze_volume(df):

    current_volume = df["volume"].iloc[-1]

    average_volume = (
        df["volume"]
        .rolling(20)
        .mean()
        .iloc[-1]
    )

    relative_volume = (
        current_volume / average_volume
    )

    return {
        "relative_volume": round(relative_volume, 2),
        "strong_volume": relative_volume >= 1.5
    }
