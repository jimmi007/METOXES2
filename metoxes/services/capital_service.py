import os

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
    "AIRfr": "AIR",
    "RHM": "RHM.DE",
    "BEI": "BEI.DE",
    "HEN3": "HEN3.DE",
    "ITX": "ITX.MC",
    "LDO": "LDO.MI",
    "LHA": "LHA.DE",
    "RWE": "RWE.DE",
    "SAAB-B": "SAAB-B.ST",
    "FFARM": "FFARM.AS",
    "ULVR": "ULVR.L",
}
async def get_clean_capital_positions():

    # Παίρνουμε τα raw positions από Capital
    data = await get_capital_positions()

    positions = data.get("positions", [])

    # Παίρνουμε τα σωστά Yahoo symbols
    # από το portfolio.xlsx


    clean_positions = []

    # ==================================================
    # ΔΙΑΒΑΖΟΥΜΕ ΟΛΕΣ ΤΙΣ ΘΕΣΕΙΣ CAPITAL
    # ==================================================

    for item in positions:

        position = item["position"]
        market = item["market"]

        # --------------------------------------------------
        # ΒΑΣΙΚΑ ΣΤΟΙΧΕΙΑ
        # --------------------------------------------------

        name = market["instrumentName"]

        capital_symbol = market["symbol"]

        # Μετατροπή Capital ticker σε Yahoo ticker
        # π.χ. RHM -> RHM.DE
        symbol = CAPITAL_TICKER_MAP.get(
            capital_symbol.upper(),
            capital_symbol
        )

        purchase_date = position["createdDateUTC"]

        quantity = float(
            position["size"]
        )

        purchase_price = float(
            position["level"]
        )

        direction = position["direction"]

        # --------------------------------------------------
        # CURRENT PRICE
        #
        # BUY  -> BID
        # SELL -> OFFER
        # --------------------------------------------------

        if direction == "BUY":

            current_price = float(
                market["bid"]
            )

        else:

            current_price = float(
                market["offer"]
            )

        # --------------------------------------------------
        # MARKET VALUE
        # --------------------------------------------------

        market_value = (
            current_price
            * quantity
        )

        # --------------------------------------------------
        # UNREALIZED PROFIT / LOSS
        # Το παίρνουμε απευθείας από Capital
        # --------------------------------------------------

        upl = float(
            position["upl"]
        )

        # --------------------------------------------------
        # ΑΡΧΙΚΟ ΚΟΣΤΟΣ ΘΕΣΗΣ
        # --------------------------------------------------

        total_cost = (
            purchase_price
            * quantity
        )

        # --------------------------------------------------
        # PERCENT CHANGE
        # --------------------------------------------------

        if total_cost != 0:

            percent_change = (
                upl
                / total_cost
            ) * 100

        else:

            percent_change = None

        # --------------------------------------------------
        # MONTHLY PERCENT CHANGE
        # Από Yahoo Finance με το σωστό ticker
        # --------------------------------------------------

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

        # --------------------------------------------------
        # VUAA RETURN
        # Από την ημερομηνία αγοράς της θέσης
        # --------------------------------------------------

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

        # --------------------------------------------------
        # EXCESS RETURN
        #
        # Απόδοση μετοχής - Απόδοση VUAA
        # --------------------------------------------------

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

        # --------------------------------------------------
        # ΠΡΟΣΘΗΚΗ ΣΤΗ CLEAN ΛΙΣΤΑ
        # --------------------------------------------------

        clean_positions.append({

            "symbol":
                symbol,

            "name":
                name,

            "platform":
                "Capital",

            "purchase_date":
                purchase_date,

            "purchase_price":
                round(
                    purchase_price,
                    2
                ),

            "quantity":
                quantity,

            "current_price":
                round(
                    current_price,
                    2
                ),

            "market_value":
                round(
                    market_value,
                    2
                ),

            "percent_change":
                round(
                    percent_change,
                    2
                )
                if percent_change is not None
                else None,

            "monthly_percent_change":
                monthly_change,

            "vuaa_return":
                vuaa_return,

            "excess_return":
                round(
                    excess_return,
                    2
                )
                if excess_return is not None
                else None,

            "upl":
                round(
                    upl,
                    2
                ),

            "direction":
                direction,

            "status":
                "OK"
        })

    return clean_positions