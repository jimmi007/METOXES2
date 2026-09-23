from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd


# --------------------------------------------------
# ΜΗΝΙΑΙΑ ΜΕΤΑΒΟΛΗ ΜΕΤΟΧΗΣ
# --------------------------------------------------

def get_monthly_percent_change(symbol: str) -> float:
    ticker = yf.Ticker(symbol)

    history = ticker.history(
        period="1mo",
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if len(prices) < 2:
        raise ValueError(
            f"Δεν υπάρχουν αρκετά δεδομένα για {symbol}"
        )

    first_price = float(prices.iloc[0])
    last_price = float(prices.iloc[-1])

    monthly_percent_change = (
        (last_price - first_price) / first_price
    ) * 100

    return round(monthly_percent_change, 2)


# --------------------------------------------------
# ΤΡΕΧΟΥΣΑ ΤΙΜΗ ΜΕΤΟΧΗΣ
# --------------------------------------------------

def get_current_price(symbol: str) -> float:
    ticker = yf.Ticker(symbol)

    history = ticker.history(
        period="5d",
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if prices.empty:
        raise ValueError(
            f"Δεν βρέθηκε τρέχουσα τιμή για {symbol}"
        )

    current_price = float(prices.iloc[-1])

    # Yahoo Finance:
    # αρκετές μετοχές του London Stock Exchange
    # επιστρέφονται σε pence αντί για pounds.
    if symbol.endswith(".L") and current_price > 1000:
        current_price = current_price / 100

    return current_price


# --------------------------------------------------
# ΝΟΜΙΣΜΑ ΜΕΤΟΧΗΣ
# --------------------------------------------------

def get_stock_currency(symbol: str) -> str:
    ticker = yf.Ticker(symbol)

    currency = ticker.fast_info.get("currency")

    if not currency:
        raise ValueError(
            f"Δεν βρέθηκε νόμισμα για {symbol}"
        )

    # Pence → GBP
    if currency in ("GBp", "GBX"):
        currency = "GBP"

    return currency.upper()


# --------------------------------------------------
# ΤΡΕΧΟΥΣΑ ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
# --------------------------------------------------

def get_current_eur_rate(currency: str) -> float:

    currency = currency.upper()

    if currency == "EUR":
        return 1.0

    pair = f"{currency}EUR=X"

    history = yf.Ticker(pair).history(
        period="5d",
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if prices.empty:
        raise ValueError(
            f"Δεν βρέθηκε ισοτιμία {currency} → EUR"
        )

    return float(prices.iloc[-1])


# --------------------------------------------------
# ΙΣΤΟΡΙΚΗ ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
# --------------------------------------------------

def get_historical_eur_rate(
    currency: str,
    purchase_date
) -> float:

    currency = currency.upper()

    if currency == "EUR":
        return 1.0

    # Το Trading212 μπορεί να μας δώσει ISO datetime
    # π.χ. 2026-08-10T12:30:00Z

    if isinstance(purchase_date, str):
        purchase_date = datetime.fromisoformat(
            purchase_date.replace("Z", "+00:00")
        )

    start_date = purchase_date.date()

    end_date = start_date + timedelta(days=7)

    pair = f"{currency}EUR=X"

    history = yf.Ticker(pair).history(
        start=start_date,
        end=end_date,
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if prices.empty:
        raise ValueError(
            f"Δεν βρέθηκε ιστορική ισοτιμία "
            f"{currency} → EUR για {start_date}"
        )

    # Πρώτη διαθέσιμη συνεδρίαση από την ημερομηνία αγοράς
    return float(prices.iloc[0])

# --------------------------------------------------
# VUAA RETURN ΑΠΟ ΤΗΝ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
# --------------------------------------------------

def get_vuaa_return(purchase_date) -> float:

    # --------------------------------------------------
    # ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
    # --------------------------------------------------

    if isinstance(purchase_date, str):
        purchase_date = datetime.fromisoformat(
            purchase_date.replace("Z", "+00:00")
        )

    start_date = purchase_date.date()
    end_date = start_date + timedelta(days=7)

    ticker = yf.Ticker("VUAA.L")

    # --------------------------------------------------
    # ΝΟΜΙΣΜΑ VUAA
    # --------------------------------------------------

    raw_currency = ticker.fast_info.get("currency")

    if not raw_currency:
        raise ValueError(
            "Δεν βρέθηκε νόμισμα για VUAA.L"
        )

    # Το Yahoo μπορεί να δίνει το VUAA.L σε GBp/GBX
    # δηλαδή pence.
    if raw_currency in ("GBp", "GBX"):
        currency = "GBP"
        price_divisor = 100
    else:
        currency = raw_currency.upper()
        price_divisor = 1

    # --------------------------------------------------
    # ΤΙΜΗ VUAA ΣΤΗΝ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
    # --------------------------------------------------

    history = ticker.history(
        start=start_date,
        end=end_date,
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if prices.empty:
        raise ValueError(
            f"Δεν βρέθηκε τιμή VUAA για {start_date}"
        )

    purchase_price_native = (
        float(prices.iloc[0]) / price_divisor
    )

    # --------------------------------------------------
    # ΙΣΟΤΙΜΙΑ ΤΟΤΕ -> EUR
    # --------------------------------------------------

    historical_eur_rate = (
        get_historical_eur_rate(
            currency,
            purchase_date
        )
    )

    purchase_price_eur = (
        purchase_price_native
        * historical_eur_rate
    )

    # --------------------------------------------------
    # ΣΗΜΕΡΙΝΗ ΤΙΜΗ VUAA
    # --------------------------------------------------

    current_history = ticker.history(
        period="5d",
        auto_adjust=False
    )

    current_prices = (
        current_history["Close"].dropna()
    )

    if current_prices.empty:
        raise ValueError(
            "Δεν βρέθηκε σημερινή τιμή VUAA"
        )

    current_price_native = (
        float(current_prices.iloc[-1])
        / price_divisor
    )

    # --------------------------------------------------
    # ΣΗΜΕΡΙΝΗ ΙΣΟΤΙΜΙΑ -> EUR
    # --------------------------------------------------

    current_eur_rate = (
        get_current_eur_rate(currency)
    )

    current_price_eur = (
        current_price_native
        * current_eur_rate
    )

    # --------------------------------------------------
    # VUAA RETURN ΣΕ EUR
    # --------------------------------------------------

    vuaa_return = (
        (
            current_price_eur
            - purchase_price_eur
        )
        / purchase_price_eur
    ) * 100

    return round(vuaa_return, 2)

def get_historical_fx_to_eur(currency, purchase_date):

    if currency == "EUR":
        return 1.0

    if not purchase_date:
        return None

    yahoo_fx_map = {
        "USD": "EUR=X",
        "GBP": "GBPEUR=X",
        "SEK": "SEKEUR=X",
    }

    ticker = yahoo_fx_map.get(currency)

    if ticker is None:
        return None

    try:
        start_date = pd.to_datetime(purchase_date)

        # Παίρνουμε λίγες ημέρες μετά,
        # γιατί η ημερομηνία μπορεί να είναι Σ/Κ
        end_date = start_date + pd.Timedelta(days=7)

        data = yf.download(
            ticker,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False
        )

        if data.empty:
            return None

        close = data["Close"].dropna()

        if close.empty:
            return None

        return float(close.iloc[0].item())

    except Exception as e:
        print(
            f"Historical FX error "
            f"{currency} {purchase_date}: {e}"
        )
        return None