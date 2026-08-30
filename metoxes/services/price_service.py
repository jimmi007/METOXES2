from datetime import timedelta
import math

import yfinance as yf


def get_current_price(symbol: str) -> float:

    ticker = yf.Ticker(symbol)

    history = ticker.history(period="5d")

    if history.empty:
        raise ValueError(
            f"No price data found for {symbol}"
        )

    current_price = float(
        history["Close"].dropna().iloc[-1]
    )

    if symbol.endswith(".L") and current_price > 1000:
        current_price = current_price / 100

    return round(current_price, 4)


def get_benchmark_return(purchase_date):

    ticker = yf.Ticker("VUAA.L")

    history = ticker.history(
        start=purchase_date,
        end=purchase_date + timedelta(days=7),
        auto_adjust=False,
    )

    purchase_prices = history["Close"].dropna()

    if purchase_prices.empty:
        raise ValueError(
            f"No VUAA.L price for {purchase_date}"
        )

    benchmark_purchase_price = float(
        purchase_prices.iloc[0]
    )

    current_history = ticker.history(
        period="10d",
        auto_adjust=False,
    )

    current_prices = current_history["Close"].dropna()

    if current_prices.empty:
        raise ValueError(
            "No current VUAA.L price"
        )

    benchmark_current_price = float(
        current_prices.iloc[-1]
    )

    if not math.isfinite(benchmark_purchase_price):
        raise ValueError(
            "Invalid VUAA.L purchase price"
        )

    if not math.isfinite(benchmark_current_price):
        raise ValueError(
            "Invalid VUAA.L current price"
        )

    if benchmark_purchase_price == 0:
        raise ValueError(
            "VUAA.L purchase price is zero"
        )

    benchmark_return = (
        (
            benchmark_current_price
            - benchmark_purchase_price
        )
        / benchmark_purchase_price
        * 100
    )

    if not math.isfinite(benchmark_return):
        raise ValueError(
            "Invalid VUAA.L return"
        )

    return round(
        benchmark_return,
        2,
    )


def get_currency_and_eur_rate(symbol: str):

    ticker = yf.Ticker(symbol)

    currency = ticker.fast_info.get("currency")

    if not currency:
        raise ValueError(
            f"Currency not found for {symbol}"
        )

    if currency in ("GBp", "GBX"):
        currency = "GBP"

    if currency == "EUR":
        return "EUR", 1.0

    pair = f"{currency}EUR=X"

    fx_data = yf.Ticker(pair).history(
        period="5d"
    )

    if fx_data.empty:
        raise ValueError(
            f"EUR exchange rate not found for {currency}"
        )

    eur_rate = float(
        fx_data["Close"]
        .dropna()
        .iloc[-1]
    )

    return currency, eur_rate