import os
from datetime import datetime

from dotenv import load_dotenv
from tradernet import Tradernet as tn
from metoxes.services.price_service import (
    get_monthly_percent_change,
    get_vuaa_return,
    get_historical_fx_to_eur,
    get_stock_info,
)
load_dotenv()

FREEDOM_PUBLIC_KEY = os.getenv("FREEDOM_PUBLIC_KEY")
FREEDOM_PRIVATE_KEY = os.getenv("FREEDOM_PRIVATE_KEY")
FREEDOM_TICKER_MAP = {
    "ACM.US": "ACM",
    "AEGN.GR": "AEGN.AT",
    "ALPHA.GR": "ALPHA.AT",
    "ASML.EU": "ASML",
    "BELA.GR": "BELA.AT",
    "CAP.EU": "CAP.PA",
    "COP.US": "COP",
    "EE.US": "EE",
    "ELHA.GR": "ELHA.AT",
    "ETE.GR": "ETE.AT",
    "EUROB.GR": "EUROB.AT",
    "EVD.EU": "EVD.DE",
    "FCX.US": "FCX",
    "FOYRK.GR": "FOYRK.AT",
    "LAMDA.GR": "LAMDA.AT",
    "LNG.US": "LNG",
    "MOH.GR": "MOH.AT",
    "MTLN.GR": "MTLN.L",
    "OTOEL.GR": "OTOEL.AT",
    "PPC.GR": "PPC.AT",
    "PSN.US": "PSN",
    "RHM.EU": "RHM.DE",
    "SIX3.EU": "SIX2.DE",
    "THEON.EU": "THEON.AS",
    "VUAA.EU": "VUAA.L",
}

# ==========================================================
# ΣΥΝΔΕΣΗ FREEDOM24
# ==========================================================

def get_freedom_connection():

    if not FREEDOM_PUBLIC_KEY or not FREEDOM_PRIVATE_KEY:
        raise ValueError(
            "Δεν βρέθηκαν τα Freedom24 API keys στο .env"
        )

    return tn(
        FREEDOM_PUBLIC_KEY,
        FREEDOM_PRIVATE_KEY
    )


# ==========================================================
# TEST ΣΥΝΔΕΣΗΣ
# ==========================================================

def test_freedom_connection():

    try:

        connection = get_freedom_connection()

        connection.authorized_request(
            "getPositionJson"
        )

        return {
            "status": "OK"
        }

    except Exception as e:

        return {
            "status": "ERROR",
            "message": str(e)
        }


# ==========================================================
# ΑΝΟΙΚΤΕΣ ΘΕΣΕΙΣ
# ==========================================================

def get_freedom_positions():

    connection = get_freedom_connection()

    response = connection.authorized_request(
        "getPositionJson"
    )

    try:
        positions = response["result"]["ps"]["pos"]

    except (KeyError, TypeError):
        return []

    return positions


# ==========================================================
# ΙΣΤΟΡΙΚΟ ΣΥΝΑΛΛΑΓΩΝ
# ==========================================================

def get_freedom_trades(
    begin_date="2020-01-01T00:00:00",
    end_date="2030-12-31T23:59:59",
    ticker=None
):

    connection = get_freedom_connection()

    params = {
        "beginDate": begin_date,
        "endDate": end_date,
        "max": 100,
        "sort": 1,
    }

    if ticker:
        params["nt_ticker"] = ticker

    response = connection.authorized_request(
        "getTradesHistory",
        params
    )

    try:
        trades = response["trades"]["trade"]

    except (KeyError, TypeError):
        return []

    if isinstance(trades, dict):
        trades = [trades]

    return trades


# ==========================================================
# FIFO + ΣΤΑΘΜΙΣΜΕΝΗ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
# ==========================================================

def get_weighted_purchase_date(
    symbol,
    current_quantity,
    trades
):

    # Συναλλαγές μόνο της συγκεκριμένης μετοχής
    symbol_trades = [
        trade
        for trade in trades
        if trade.get("instr_nm") == symbol
    ]

    # Παλαιότερη -> νεότερη
    symbol_trades.sort(
        key=lambda x: x.get("date", "")
    )

    lots = []

    for trade in symbol_trades:

        trade_type = str(
            trade.get("type")
        )

        quantity = abs(
            float(trade.get("q", 0))
        )

        date_string = trade.get("date")

        if quantity <= 0 or not date_string:
            continue

        trade_date = datetime.fromisoformat(
            date_string
        )

        # --------------------------
        # BUY
        # --------------------------

        if trade_type == "1":

            lots.append({
                "date": trade_date,
                "quantity": quantity
            })

        # --------------------------
        # SELL
        # --------------------------

        elif trade_type == "2":

            quantity_to_sell = quantity

            # FIFO
            while (
                quantity_to_sell > 0
                and lots
            ):

                first_lot = lots[0]

                if (
                    first_lot["quantity"]
                    <= quantity_to_sell
                ):

                    quantity_to_sell -= (
                        first_lot["quantity"]
                    )

                    lots.pop(0)

                else:

                    first_lot["quantity"] -= (
                        quantity_to_sell
                    )

                    quantity_to_sell = 0

    if not lots:
        return None

    remaining_quantity = sum(
        lot["quantity"]
        for lot in lots
    )

    if remaining_quantity <= 0:
        return None

    weighted_timestamp = sum(
        lot["date"].timestamp()
        * lot["quantity"]
        for lot in lots
    ) / remaining_quantity

    weighted_date = datetime.fromtimestamp(
        weighted_timestamp
    )

    return weighted_date.date().isoformat()


# ==========================================================
# CLEAN FREEDOM24 POSITIONS
# ==========================================================

def get_clean_freedom_positions():

    connection = get_freedom_connection()

    response = connection.authorized_request(
        "getPositionJson"
    )

    result = response.get("result", {})
    portfolio = result.get("ps", {})

    positions = portfolio.get("pos", [])
    accounts = portfolio.get("acc", [])

    # ==========================================================
    # 1. ΤΡΕΧΟΥΣΕΣ ΙΣΟΤΙΜΙΕΣ FREEDOM24
    # ==========================================================

    currency_rates = {}

    for account in accounts:

        currency = account.get("curr")
        currval = account.get("currval")

        if currency and currval is not None:
            currency_rates[currency] = float(currval)

    eur_currval = currency_rates.get("EUR")

    if not eur_currval:
        raise ValueError(
            "Δεν βρέθηκε EUR currval στο Freedom24 portfolio"
        )

    clean_positions = []

    # ==========================================================
    # 2. ΚΑΘΕ ΑΝΟΙΚΤΗ ΘΕΣΗ
    # ==========================================================

    for p in positions:

        symbol = p.get("i")
        name = p.get("name")
        currency = p.get("curr")

        quantity = float(
            p.get("q", 0) or 0
        )

        # Δεν μας ενδιαφέρουν μηδενικές/κλειστές θέσεις
        if quantity <= 0:
            continue

        # ======================================================
        # 3. TRADES ΤΗΣ ΣΥΓΚΕΚΡΙΜΕΝΗΣ ΜΕΤΟΧΗΣ
        # ======================================================

        trades = get_freedom_trades(
            ticker=symbol
        )

        # ======================================================
        # 4. ΣΤΑΘΜΙΣΜΕΝΗ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ ΜΕ FIFO
        # ======================================================

        purchase_date = get_weighted_purchase_date(
            symbol,
            quantity,
            trades
        )

        # ======================================================
        # 5. YAHOO FINANCE SYMBOL
        # ======================================================

        yahoo_symbol = FREEDOM_TICKER_MAP.get(
            symbol,
            symbol
        )
        # ======================================================
        # SECTOR / COUNTRY
        # Από Yahoo Finance με το σωστό Yahoo ticker
        # ======================================================

        stock_info = get_stock_info(
            yahoo_symbol
        )

        sector = stock_info.get(
            "sector"
        )

        country = stock_info.get(
            "country"
        )

        # ======================================================
        # 6. ΜΗΝΙΑΙΑ ΜΕΤΑΒΟΛΗ
        # ======================================================

        try:

            monthly_percent_change = (
                get_monthly_percent_change(
                    yahoo_symbol
                )
            )

        except Exception:

            monthly_percent_change = None

        # ======================================================
        # 7. ΑΠΟΔΟΣΗ VUAA
        # ======================================================

        if purchase_date:

            try:

                vuaa_return = get_vuaa_return(
                    purchase_date
                )

            except Exception:

                vuaa_return = None

        else:

            vuaa_return = None

        # ======================================================
        # 8. ΤΙΜΕΣ FREEDOM24 ΣΤΟ ΑΡΧΙΚΟ ΝΟΜΙΣΜΑ
        # ======================================================

        purchase_price_native = float(
            p.get("price_a", 0) or 0
        )

        current_price_native = float(
            p.get("profit_price", 0) or 0
        )

        market_value_native = float(
            p.get("market_value", 0) or 0
        )

        profit_native = float(
            p.get("profit_close", 0) or 0
        )

        # ======================================================
        # 9. ΤΡΕΧΟΥΣΑ ΙΣΟΤΙΜΙΑ -> EUR
        #
        # Για:
        # current_price
        # market_value
        # profit
        # ======================================================

        if currency == "EUR":

            fx_to_eur = 1.0

        else:

            currency_currval = currency_rates.get(
                currency
            )

            if currency_currval:

                fx_to_eur = (
                    currency_currval
                    / eur_currval
                )

            else:

                fx_to_eur = None

        # ======================================================
        # 10. ΙΣΤΟΡΙΚΗ ΙΣΟΤΙΜΙΑ -> EUR
        #
        # Χρησιμοποιείται για την τιμή αγοράς.
        # ======================================================

        if currency == "EUR":

            historical_fx_to_eur = 1.0

        elif purchase_date:

            try:

                historical_fx_to_eur = (
                    get_historical_fx_to_eur(
                        currency,
                        purchase_date
                    )
                )

            except Exception:

                historical_fx_to_eur = None

        else:

            historical_fx_to_eur = None

        # ======================================================
        # 11. PURCHASE PRICE ΣΕ EUR
        # ======================================================

        if historical_fx_to_eur is not None:

            purchase_price_eur = (
                purchase_price_native
                * historical_fx_to_eur
            )

        else:

            purchase_price_eur = None

        # ======================================================
        # 12. ΤΡΕΧΟΥΣΕΣ ΑΞΙΕΣ ΣΕ EUR
        # ======================================================

        if fx_to_eur is not None:

            current_price_eur = (
                current_price_native
                * fx_to_eur
            )

            market_value_eur = (
                market_value_native
                * fx_to_eur
            )

            profit_eur = (
                profit_native
                * fx_to_eur
            )

        else:

            current_price_eur = None
            market_value_eur = None
            profit_eur = None

        # ======================================================
        # 13. ΣΥΝΟΛΙΚΗ % ΑΠΟΔΟΣΗ ΣΕ EUR
        #
        # Ιστορική τιμή αγοράς EUR
        # έναντι
        # σημερινής τιμής EUR
        #
        # Έτσι λαμβάνεται υπόψη και η μεταβολή της ισοτιμίας.
        # ======================================================

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

        # ======================================================
        # 14. EXCESS RETURN
        #
        # Απόδοση επένδυσης σε EUR
        # μείον απόδοση VUAA
        # ======================================================

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

        # ======================================================
        # 15. STATUS
        # ======================================================

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
        # 16. ΤΕΛΙΚΟ CLEAN RECORD
        # ======================================================

        clean_positions.append({

            "symbol": symbol,

            "name": name,

            "sector": sector,

            "country": country,

            "platform": "Freedom24",

            "purchase_date": purchase_date,

            # Ιστορική τιμή αγοράς σε EUR
            "purchase_price": (
                round(
                    purchase_price_eur,
                    2
                )
                if purchase_price_eur is not None
                else None
            ),

            "quantity": quantity,

            # Σημερινή τιμή σε EUR
            "current_price": (
                round(
                    current_price_eur,
                    2
                )
                if current_price_eur is not None
                else None
            ),

            # Σημερινή αξία θέσης σε EUR
            "market_value": (
                round(
                    market_value_eur,
                    2
                )
                if market_value_eur is not None
                else None
            ),

            # Συνολική απόδοση σε EUR
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
                    monthly_percent_change,
                    2
                )
                if monthly_percent_change is not None
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

            # Κέρδος / ζημία Freedom24 σε EUR
            "profit": (
                round(
                    profit_eur,
                    2
                )
                if profit_eur is not None
                else None
            ),

            "original_currency": currency,

            # Σημερινή ισοτιμία
            "fx_to_eur": (
                round(
                    fx_to_eur,
                    6
                )
                if fx_to_eur is not None
                else None
            ),

            # Ιστορική ισοτιμία
            "historical_fx_to_eur": (
                round(
                    historical_fx_to_eur,
                    6
                )
                if historical_fx_to_eur is not None
                else None
            ),

            "status": status
        })

    return clean_positions