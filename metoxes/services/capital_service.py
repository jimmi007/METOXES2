import os
from metoxes.services.price_service import get_historical_fx_to_eur
import httpx
from dotenv import load_dotenv
from metoxes.services.price_service import (
    get_monthly_percent_change,
    get_vuaa_return,
)

load_dotenv()

CAPITAL_API_KEY = os.getenv("CAPITAL_API_KEY")
CAPITAL_IDENTIFIER = os.getenv("CAPITAL_IDENTIFIER")
CAPITAL_PASSWORD = os.getenv("CAPITAL_PASSWORD")

BASE_URL = "https://api-capital.backend-capital.com"
import yfinance as yf


def get_fx_to_eur(currency: str):

    if currency == "EUR":
        return 1.0

    yahoo_fx_map = {
        "USD": "EUR=X",       # 1 USD -> EUR
        "GBP": "GBPEUR=X",    # 1 GBP -> EUR
        "SEK": "SEKEUR=X",    # 1 SEK -> EUR
    }

    ticker = yahoo_fx_map.get(currency)

    if ticker is None:
        return None

    data = yf.Ticker(ticker).history(period="5d")

    if data.empty:
        return None

    return float(data["Close"].iloc[-1])


async def create_capital_session():

    if not CAPITAL_API_KEY:
        raise ValueError("Λείπει το CAPITAL_API_KEY")

    if not CAPITAL_IDENTIFIER:
        raise ValueError("Λείπει το CAPITAL_IDENTIFIER")

    if not CAPITAL_PASSWORD:
        raise ValueError("Λείπει το CAPITAL_PASSWORD")

    url = f"{BASE_URL}/api/v1/session"

    headers = {
        "X-CAP-API-KEY": CAPITAL_API_KEY,
        "Content-Type": "application/json"
    }

    data = {
        "identifier": CAPITAL_IDENTIFIER,
        "password": CAPITAL_PASSWORD,
        "encryptedPassword": False
    }

    async with httpx.AsyncClient() as client:

        response = await client.post(
            url,
            headers=headers,
            json=data,
            timeout=30
        )

        response.raise_for_status()

        cst = response.headers.get("CST")
        security_token = response.headers.get(
            "X-SECURITY-TOKEN"
        )

        return {
            "status": "CONNECTED",
            "cst_received": bool(cst),
            "security_token_received":
                bool(security_token)
        }

async def get_capital_positions():

    if not CAPITAL_API_KEY:
        raise ValueError("Λείπει το CAPITAL_API_KEY")

    # ------------------------------------------
    # 1. Δημιουργία session
    # ------------------------------------------

    session_url = f"{BASE_URL}/api/v1/session"

    session_headers = {
        "X-CAP-API-KEY": CAPITAL_API_KEY,
        "Content-Type": "application/json"
    }

    session_data = {
        "identifier": CAPITAL_IDENTIFIER,
        "password": CAPITAL_PASSWORD,
        "encryptedPassword": False
    }

    async with httpx.AsyncClient() as client:

        session_response = await client.post(
            session_url,
            headers=session_headers,
            json=session_data,
            timeout=30
        )

        session_response.raise_for_status()

        cst = session_response.headers.get("CST")

        security_token = session_response.headers.get(
            "X-SECURITY-TOKEN"
        )

        if not cst or not security_token:
            raise ValueError(
                "Δεν επιστράφηκαν session tokens από Capital"
            )

        # ------------------------------------------
        # 2. Ανάκτηση ανοικτών θέσεων
        # ------------------------------------------

        positions_url = f"{BASE_URL}/api/v1/positions"

        positions_headers = {
            "X-CAP-API-KEY": CAPITAL_API_KEY,
            "CST": cst,
            "X-SECURITY-TOKEN": security_token
        }

        response = await client.get(
            positions_url,
            headers=positions_headers,
            timeout=30
        )

        response.raise_for_status()

        return response.json()

from metoxes.services.price_service import (
    get_monthly_percent_change,
    get_vuaa_return,
)

CAPITAL_TICKER_MAP = {
   "AIRFR": "AIR.PA",
   "SAABB": "SAAB-B.ST",
    "RHM": "RHM.DE",
    "BEI": "BEI.DE",
    "HEN3": "HEN3.DE",
    "ITX": "ITX.MC",
    "LDO": "LDO.MI",
    "LHA": "LHA.DE",
    "RWE": "RWE.DE",

    "FFARM": "FFARM.AS",
    "ULVR": "ULVR.L",
}
async def get_clean_capital_positions():

    # ==========================================================
    # 1. ΠΑΙΡΝΟΥΜΕ ΤΙΣ RAW ΘΕΣΕΙΣ ΑΠΟ CAPITAL
    # ==========================================================

    data = await get_capital_positions()

    positions = data.get("positions", [])

    clean_positions = []

    # ==========================================================
    # 2. ΔΙΑΒΑΖΟΥΜΕ ΟΛΕΣ ΤΙΣ ΘΕΣΕΙΣ CAPITAL
    # ==========================================================

    for item in positions:

        position = item["position"]
        market = item["market"]

        # ------------------------------------------------------
        # ΒΑΣΙΚΑ ΣΤΟΙΧΕΙΑ
        # ------------------------------------------------------

        name = market["instrumentName"]

        capital_symbol = market["symbol"]

        # Μετατροπή Capital ticker -> Yahoo ticker
        # π.χ. RHM -> RHM.DE
        symbol = CAPITAL_TICKER_MAP.get(
            capital_symbol.upper(),
            capital_symbol
        )

        purchase_date = position["createdDateUTC"]

        quantity = float(
            position["size"]
        )

        # Τιμή αγοράς στο αρχικό νόμισμα
        purchase_price_native = float(
            position["level"]
        )

        direction = position["direction"]

        # ------------------------------------------------------
        # ΝΟΜΙΣΜΑ ΘΕΣΗΣ
        # ------------------------------------------------------

        original_currency = position["currency"]

        # ------------------------------------------------------
        # ΤΡΕΧΟΥΣΑ ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
        # ------------------------------------------------------

        fx_to_eur = get_fx_to_eur(
            original_currency
        )

        # ------------------------------------------------------
        # ΙΣΤΟΡΙΚΗ ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
        # Την ημερομηνία αγοράς
        # ------------------------------------------------------

        historical_fx_to_eur = (
            get_historical_fx_to_eur(
                original_currency,
                purchase_date
            )
        )

        # ------------------------------------------------------
        # PURCHASE PRICE ΣΕ EUR
        # ------------------------------------------------------

        if historical_fx_to_eur is not None:

            purchase_price_eur = (
                purchase_price_native
                * historical_fx_to_eur
            )

        else:

            purchase_price_eur = None

        # ------------------------------------------------------
        # CURRENT PRICE
        #
        # BUY  -> BID
        # SELL -> OFFER
        # ------------------------------------------------------

        if direction == "BUY":

            current_price_native = float(
                market["bid"]
            )

        else:

            current_price_native = float(
                market["offer"]
            )

        # ------------------------------------------------------
        # CURRENT PRICE ΣΕ EUR
        # ------------------------------------------------------

        if fx_to_eur is not None:

            current_price_eur = (
                current_price_native
                * fx_to_eur
            )

        else:

            current_price_eur = None

        # ------------------------------------------------------
        # MARKET VALUE ΣΕ EUR
        # ------------------------------------------------------

        if current_price_eur is not None:

            market_value_eur = (
                current_price_eur
                * quantity
            )

        else:

            market_value_eur = None

        # ------------------------------------------------------
        # UNREALIZED PROFIT / LOSS
        #
        # Το Capital δίνει το UPL στο νόμισμα της θέσης.
        # Το μετατρέπουμε σε EUR με τη σημερινή ισοτιμία.
        # ------------------------------------------------------

        upl_native = float(
            position["upl"]
        )

        if fx_to_eur is not None:

            upl_eur = (
                upl_native
                * fx_to_eur
            )

        else:

            upl_eur = None

        # ------------------------------------------------------
        # PERCENT CHANGE ΣΕ EUR
        #
        # Συγκρίνουμε:
        # ιστορική τιμή αγοράς σε EUR
        # με σημερινή τιμή σε EUR
        #
        # Άρα περιλαμβάνεται και η επίδραση της ισοτιμίας.
        # ------------------------------------------------------

        if (
            purchase_price_eur is not None
            and current_price_eur is not None
            and purchase_price_eur != 0
        ):

            percent_change = (
                (
                    current_price_eur
                    - purchase_price_eur
                )
                / purchase_price_eur
                * 100
            )

        else:

            percent_change = None

        # ------------------------------------------------------
        # MONTHLY PERCENT CHANGE
        # Από Yahoo Finance
        # ------------------------------------------------------

        try:

            monthly_change = (
                get_monthly_percent_change(
                    symbol
                )
            )

        except Exception as e:

            print(
                f"CAPITAL MONTHLY ERROR "
                f"{name} | "
                f"Capital={capital_symbol} | "
                f"Yahoo={symbol} | "
                f"Error={e}"
            )

            monthly_change = None

        # ------------------------------------------------------
        # VUAA RETURN
        # Από την ημερομηνία αγοράς
        # ------------------------------------------------------

        try:

            vuaa_return = (
                get_vuaa_return(
                    purchase_date
                )
            )

        except Exception as e:

            print(
                f"CAPITAL VUAA ERROR "
                f"{name} | "
                f"Error={e}"
            )

            vuaa_return = None

        # ------------------------------------------------------
        # EXCESS RETURN
        #
        # Απόδοση μετοχής σε EUR - Απόδοση VUAA
        # ------------------------------------------------------

        if (
            percent_change is not None
            and vuaa_return is not None
        ):

            excess_return = (
                percent_change
                - vuaa_return
            )

        else:

            excess_return = None

        # ------------------------------------------------------
        # STATUS
        # ------------------------------------------------------

        if (
            fx_to_eur is not None
            and historical_fx_to_eur is not None
        ):

            status = "OK"

        elif fx_to_eur is None:

            status = "FX_NOT_FOUND"

        else:

            status = "HISTORICAL_FX_NOT_FOUND"

        # ======================================================
        # 3. ΤΕΛΙΚΟ CLEAN RECORD
        # ======================================================

        clean_positions.append({

            "symbol": symbol,

            "name": name,

            "platform": "Capital",

            "purchase_date": purchase_date,

            # Τιμή αγοράς σε EUR
            "purchase_price": (
                round(
                    purchase_price_eur,
                    2
                )
                if purchase_price_eur is not None
                else None
            ),

            "quantity": quantity,

            # Απόδοση σε EUR
            "percent_change": (
                round(
                    percent_change,
                    2
                )
                if percent_change is not None
                else None
            ),

            "monthly_percent_change": (
                round(
                    monthly_change,
                    2
                )
                if monthly_change is not None
                else None
            ),

            "vuaa_return": (
                round(
                    vuaa_return,
                    2
                )
                if vuaa_return is not None
                else None
            ),

            "excess_return": (
                round(
                    excess_return,
                    2
                )
                if excess_return is not None
                else None
            ),

            # Τρέχουσα τιμή σε EUR
            "current_price": (
                round(
                    current_price_eur,
                    2
                )
                if current_price_eur is not None
                else None
            ),

            # Τρέχουσα αξία θέσης σε EUR
            "market_value": (
                round(
                    market_value_eur,
                    2
                )
                if market_value_eur is not None
                else None
            ),

            # UPL σε EUR
            "upl": (
                round(
                    upl_eur,
                    2
                )
                if upl_eur is not None
                else None
            ),

            "original_currency": original_currency,

            # Σημερινή ισοτιμία
            "fx_to_eur": (
                round(
                    fx_to_eur,
                    6
                )
                if fx_to_eur is not None
                else None
            ),

            # Ιστορική ισοτιμία αγοράς
            "historical_fx_to_eur": (
                round(
                    historical_fx_to_eur,
                    6
                )
                if historical_fx_to_eur is not None
                else None
            ),

            "direction": direction,

            "status": status
        })

    return clean_positions



