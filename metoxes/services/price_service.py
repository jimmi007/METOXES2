from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd
from functools import lru_cache

# --------------------------------------------------
# ΜΗΝΙΑΙΑ ΜΕΤΑΒΟΛΗ ΜΕΤΟΧΗΣ
# --------------------------------------------------

# --------------------------------------------------
# ΜΕΤΑΒΟΛΗ ΤΕΛΕΥΤΑΙΩΝ 30 ΗΜΕΡΩΝ
# --------------------------------------------------

def get_monthly_percent_change(symbol: str) -> float:

    ticker = yf.Ticker(symbol)

    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=30)

    history = ticker.history(
        start=start_date,
        end=end_date + timedelta(days=1),
        auto_adjust=False
    )

    prices = history["Close"].dropna()

    if len(prices) < 2:
        raise ValueError(
            f"Δεν υπάρχουν αρκετά δεδομένα για {symbol}"
        )

    first_price = float(prices.iloc[0])
    last_price = float(prices.iloc[-1])

    percent_change = (
        (last_price - first_price)
        / first_price
        * 100
    )

    return round(percent_change, 2)


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

# --------------------------------------------------
# VUAA RETURN ΑΠΟ ΤΗΝ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
# --------------------------------------------------

@lru_cache(maxsize=512)
def get_vuaa_return(purchase_date) -> float:

    if isinstance(purchase_date, str):
        purchase_date = datetime.fromisoformat(
            purchase_date.replace("Z", "+00:00")
        )

    start_date = purchase_date.date()
    end_date = start_date + timedelta(days=14)

    ticker = yf.Ticker("VUAA.L")

    # Νόμισμα VUAA
    raw_currency = ticker.fast_info.get("currency")

    if not raw_currency:
        raise ValueError("Δεν βρέθηκε νόμισμα VUAA")

    if raw_currency in ("GBp", "GBX"):
        currency = "GBP"
        divisor = 100
    else:
        currency = raw_currency.upper()
        divisor = 1

    # Τιμή VUAA τότε
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

    purchase_price = float(prices.iloc[0]) / divisor

    historical_fx = get_historical_eur_rate(
        currency,
        purchase_date
    )

    purchase_price_eur = (
        purchase_price * historical_fx
    )

    # Τιμή VUAA σήμερα
    current = ticker.history(
        period="5d",
        auto_adjust=False
    )["Close"].dropna()

    if current.empty:
        raise ValueError(
            "Δεν βρέθηκε σημερινή τιμή VUAA"
        )

    current_price = float(current.iloc[-1]) / divisor

    current_fx = get_current_eur_rate(currency)

    current_price_eur = (
        current_price * current_fx
    )

    return round(
        (
            (current_price_eur - purchase_price_eur)
            / purchase_price_eur
        ) * 100,
        2
    )

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

# --------------------------------------------------
# SECTOR / COUNTRY ΜΕΤΟΧΗΣ
# --------------------------------------------------

def get_stock_info(symbol: str):

    try:
        ticker = yf.Ticker(symbol)

        # Πληροφορίες εταιρείας από Yahoo Finance
        info = ticker.info

        sector = info.get("sector")
        country = info.get("country")

        return {
            "sector": sector,
            "country": country
        }

    except Exception as e:

        print(
            f"Stock info error {symbol}: {e}"
        )

        return {
            "sector": None,
            "country": None
        }