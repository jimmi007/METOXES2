import yfinance as yf


def get_current_price(symbol: str) -> float:
    ticker = yf.Ticker(symbol)

    data = ticker.history(
        period="1d"
    )

    if data.empty:
        raise ValueError(
            f"No price found for {symbol}"
        )

    return float(
        data["Close"].iloc[-1]
    )