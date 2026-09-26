from functools import lru_cache

import yfinance as yf

from metoxes.services.price_service import get_current_eur_rate


# ==========================================================
# FREEDOM24 SYMBOL -> YAHOO FINANCE SYMBOL
# ==========================================================



YAHOO_SYMBOL_MAP = {

    # -------------------------
    # USA
    # -------------------------

    "ACM.US": "ACM",
    "COP.US": "COP",
    "EE.US": "EE",
    "FCX.US": "FCX",
    "LNG.US": "LNG",
    "PSN.US": "PSN",

    # -------------------------
    # GREECE
    # -------------------------

    "AEGN.GR": "AEGN.AT",
    "ALPHA.GR": "ALPHA.AT",
    "BELA.GR": "BELA.AT",
    "ELHA.GR": "ELHA.AT",
    "ETE.GR": "ETE.AT",
    "EUROB.GR": "EUROB.AT",
    "FOYRK.GR": "FOYRK.AT",
    "LAMDA.GR": "LAMDA.AT",
    "MOH.GR": "MOH.AT",
    "OTOEL.GR": "OTOEL.AT",
    "PPC.GR": "PPC.AT",

    # METLEN PLC
    "MTLN.GR": "MTLN.L",

    # -------------------------
    # EUROPE
    # -------------------------

    "ASML.EU": "ASML.AS",
    "CAP.EU": "CAP.PA",
    "EVD.EU": "EVD.DE",
    "RHM.EU": "RHM.DE",
    "SIX3.EU": "SIX2.DE",
    "THEON.EU": "THEON.AS",

    # ETF
    "VUAA.EU": "VUAA.L",
}


# ==========================================================
# HELPER
# ==========================================================

def get_value(data, row, column):

    if data.empty:
        return None

    if row not in data.index:
        return None

    try:

        value = data.loc[row, column]

        # NaN
        if value != value:
            return None

        return float(value)

    except Exception:
        return None
def get_latest_values(data, row, limit=2):

    values = []

    if data.empty or row not in data.index:
        return values

    # Οι στήλες είναι ήδη newest -> oldest
    for column in data.columns:

        value = get_value(
            data,
            row,
            column
        )

        if value is not None:

            values.append(
                value
            )

        if len(values) == limit:
            break

    return values


def get_latest_fcf_values(cashflow, limit=2):

    values = []

    if cashflow.empty:
        return values

    for column in cashflow.columns:

        # ----------------------------------------------
        # 1. Προσπαθούμε έτοιμο Free Cash Flow
        # ----------------------------------------------

        fcf = get_value(
            cashflow,
            "Free Cash Flow",
            column
        )

        # ----------------------------------------------
        # 2. Αν λείπει:
        #
        # FCF = Operating Cash Flow + CapEx
        #
        # Στο Yahoo το Capital Expenditure
        # συνήθως είναι αρνητικός αριθμός.
        # ----------------------------------------------

        if fcf is None:

            operating_cash_flow = get_value(
                cashflow,
                "Operating Cash Flow",
                column
            )

            capital_expenditure = get_value(
                cashflow,
                "Capital Expenditure",
                column
            )

            if (
                operating_cash_flow is not None
                and capital_expenditure is not None
            ):

                fcf = (
                    operating_cash_flow
                    + capital_expenditure
                )

        if fcf is not None:

            values.append(
                fcf
            )

        if len(values) == limit:
            break

    return values

# ==========================================================
# YAHOO SYMBOL
# ==========================================================

def get_yahoo_symbol(symbol: str):

    if not symbol:
        return None

    symbol = (
        str(symbol)
        .strip()
        .strip('"')
        .strip("'")
        .upper()
    )

    return YAHOO_SYMBOL_MAP.get(
        symbol,
        symbol
    )


# ==========================================================
# NORMALIZE CURRENCY
# ==========================================================

def normalize_currency(currency):

    if not currency:
        return None

    currency = str(currency).upper()

    # Yahoo χρησιμοποιεί GBp / GBX
    # για μετοχές Λονδίνου.
    if currency in ("GBP", "GBX"):

        return "GBP"

    return currency


# ==========================================================
# CONVERT VALUE TO EUR
# ==========================================================

def convert_to_eur(value, currency):

    if value is None:
        return None

    currency = normalize_currency(
        currency
    )

    if not currency:
        return None

    # Ήδη EUR
    if currency == "EUR":

        return float(value)

    rate = get_current_eur_rate(
        currency
    )

    return float(value) * rate


# ==========================================================
# FUNDAMENTALS ΜΙΑΣ ΜΕΤΟΧΗΣ
# ==========================================================

@lru_cache(maxsize=256)
def get_stock_fundamentals(symbol: str):

    # ------------------------------------------------------
    # SYMBOL
    # ------------------------------------------------------

    symbol = get_yahoo_symbol(
        symbol
    )

    ticker = yf.Ticker(
        symbol
    )

    # ------------------------------------------------------
    # INFO
    # ------------------------------------------------------

    try:

        info = ticker.get_info()

    except Exception:

        info = {}

    # ------------------------------------------------------
    # FINANCIAL STATEMENTS
    # ------------------------------------------------------

    try:

        cashflow = ticker.get_cashflow(
            freq="yearly",
            pretty=True
        )

    except Exception:

        cashflow = None

    try:

        income = ticker.get_income_stmt(
            freq="yearly",
            pretty=True
        )

    except Exception:

        income = None

    try:

        balance = ticker.get_balance_sheet(
            freq="yearly",
            pretty=True
        )

    except Exception:

        balance = None

    # ------------------------------------------------------
    # ΑΝ ΑΠΟΤΥΧΕΙ YAHOO
    # ------------------------------------------------------

    if cashflow is None:

        cashflow = yf.Ticker(
            symbol
        ).cashflow

    if income is None:

        income = yf.Ticker(
            symbol
        ).income_stmt

    if balance is None:

        balance = yf.Ticker(
            symbol
        ).balance_sheet

    # ------------------------------------------------------
    # ΝΕΟΤΕΡΗ ΧΡΗΣΗ ΠΡΩΤΗ
    # ------------------------------------------------------

    if not cashflow.empty:

        cashflow = cashflow.sort_index(
            axis=1,
            ascending=False
        )

    if not income.empty:

        income = income.sort_index(
            axis=1,
            ascending=False
        )

    if not balance.empty:

        balance = balance.sort_index(
            axis=1,
            ascending=False
        )

    # ======================================================
    # MARKET CAP
    # ======================================================

    market_cap = None

    # Πρώτα χρησιμοποιούμε το marketCap από το Yahoo info.
    # Είναι ασφαλέστερο για London stocks όπως ULVR.L.
    try:
        market_cap = info.get("marketCap")
    except Exception:
        market_cap = None

    # Fallback μόνο αν δεν υπάρχει
    if market_cap is None:
        try:
            market_cap = ticker.fast_info["market_cap"]
        except Exception:
            market_cap = None

    # ======================================================
    # CURRENCIES
    # ======================================================

    financial_currency = normalize_currency(
        info.get(
            "financialCurrency"
        )
    )

    market_currency = normalize_currency(
        info.get(
            "currency"
        )
    )

    # ======================================================
    # FREE CASH FLOW
    # ======================================================

    free_cash_flow = None
    previous_fcf = None
    fcf_growth = None

    fcf_values = get_latest_fcf_values(
        cashflow,
        limit=2
    )

    if len(fcf_values) >= 1:
        free_cash_flow = (
            fcf_values[0]
        )

    if len(fcf_values) >= 2:
        previous_fcf = (
            fcf_values[1]
        )

    # ======================================================
    # FCF GROWTH
    #
    # Υπολογίζουμε growth μόνο όταν:
    #
    # latest FCF   > 0
    # previous FCF > 0
    #
    # Έτσι αποφεύγουμε παραπλανητικά ποσοστά όταν
    # μια εταιρεία περνά από αρνητικό FCF σε θετικό
    # ή από θετικό σε αρνητικό.
    # ======================================================

    if (
            free_cash_flow is not None
            and previous_fcf is not None
            and free_cash_flow > 0
            and previous_fcf > 0
    ):

        fcf_growth = (
                (
                        free_cash_flow
                        - previous_fcf
                )
                / previous_fcf
                * 100
        )

    else:

        fcf_growth = None
    # ======================================================
    # FCF YIELD
    # ======================================================

    fcf_yield = None

    if (
        free_cash_flow is not None
        and market_cap is not None
        and market_cap != 0
    ):

        try:

            # ------------------------------------------
            # ΙΔΙΟ ΝΟΜΙΣΜΑ
            # ------------------------------------------

            if (
                financial_currency
                and market_currency
                and financial_currency
                == market_currency
            ):

                fcf_yield = (
                    free_cash_flow
                    / market_cap
                    * 100
                )

            # ------------------------------------------
            # ΔΙΑΦΟΡΕΤΙΚΟ ΝΟΜΙΣΜΑ
            # π.χ. TSM:
            # FCF = TWD
            # Market Cap = USD
            # ------------------------------------------

            elif (
                financial_currency
                and market_currency
            ):

                free_cash_flow_eur = (
                    convert_to_eur(
                        free_cash_flow,
                        financial_currency
                    )
                )

                market_cap_eur = (
                    convert_to_eur(
                        market_cap,
                        market_currency
                    )
                )

                if (
                    free_cash_flow_eur
                    is not None
                    and market_cap_eur
                    is not None
                    and market_cap_eur != 0
                ):

                    fcf_yield = (
                        free_cash_flow_eur
                        / market_cap_eur
                        * 100
                    )

        except Exception as e:

            print(
                f"FCF CURRENCY ERROR "
                f"{symbol}: {e}"
            )

            fcf_yield = None

    # ======================================================
    # ROIC
    # ======================================================

    roic = None

    if (
        not income.empty
        and not balance.empty
    ):

        operating_values = get_latest_values(
            income,
            "Operating Income",
            limit=1
        )

        tax_values = get_latest_values(
            income,
            "Tax Provision",
            limit=1
        )

        pretax_values = get_latest_values(
            income,
            "Pretax Income",
            limit=1
        )

        invested_values = get_latest_values(
            balance,
            "Invested Capital",
            limit=1
        )

        operating_income = (
            operating_values[0]
            if operating_values
            else None
        )

        tax_provision = (
            tax_values[0]
            if tax_values
            else None
        )

        pretax_income = (
            pretax_values[0]
            if pretax_values
            else None
        )

        invested_capital = (
            invested_values[0]
            if invested_values
            else None
        )





        # ----------------------------------------------
        # TAX RATE
        # ----------------------------------------------

        if (
            tax_provision is not None
            and pretax_income is not None
            and pretax_income > 0
        ):

            tax_rate = (
                tax_provision
                / pretax_income
            )

            tax_rate = max(
                0,
                min(
                    tax_rate,
                    1
                )
            )

        else:

            tax_rate = 0

        # ----------------------------------------------
        # NOPAT
        # ----------------------------------------------

        if operating_income is not None:

            nopat = (
                operating_income
                * (1 - tax_rate)
            )

        else:

            nopat = None

        # ----------------------------------------------
        # ROIC
        # ----------------------------------------------

        if (
            nopat is not None
            and invested_capital is not None
            and invested_capital != 0
        ):

            roic = (
                nopat
                / invested_capital
                * 100
            )

    # ======================================================
    # RESULT
    # ======================================================

    return {

        "symbol": symbol,

        "market_cap": (
            round(
                float(market_cap),
                2
            )
            if market_cap is not None
            else None
        ),

        "free_cash_flow": (
            round(
                free_cash_flow,
                2
            )
            if free_cash_flow is not None
            else None
        ),

        "fcf_yield": (
            round(
                fcf_yield,
                2
            )
            if fcf_yield is not None
            else None
        ),

        "fcf_growth": (
            round(
                fcf_growth,
                2
            )
            if fcf_growth is not None
            else None
        ),

        "roic": (
            round(
                roic,
                2
            )
            if roic is not None
            else None
        ),

        "financial_currency": (
            financial_currency
        ),

        "market_currency": (
            market_currency
        ),
        "industry": info.get("industry"),
    }


# ==========================================================
# FUNDAMENTALS ΟΛΟΥ ΤΟΥ PORTFOLIO
# ==========================================================

def get_portfolio_fundamentals(stocks):

    results = []

    for stock in stocks:

        original_symbol = (
            stock.get("symbol")
        )

        if not original_symbol:
            continue

        # --------------------------------------------------
        # ΜΕΤΑΤΡΟΠΗ BROKER SYMBOL -> YAHOO SYMBOL
        #
        # Δεν εξαρτάται πλέον από το platform.
        # --------------------------------------------------

        yahoo_symbol = get_yahoo_symbol(
            original_symbol
        )

        try:

            fundamentals = (
                get_stock_fundamentals(
                    yahoo_symbol
                )
            )

            results.append({

                # Symbol όπως υπάρχει στο portfolio
                "symbol": original_symbol,

                # Symbol που χρησιμοποιεί Yahoo
                "yahoo_symbol": yahoo_symbol,

                "name": stock.get(
                    "name"
                ),

                "sector": stock.get(
                    "sector"
                ),

                "country": stock.get(
                    "country"
                ),

                "platform": stock.get(
                    "platform"
                ),

                "fcf_yield": (
                    fundamentals.get(
                        "fcf_yield"
                    )
                ),
                "industry": fundamentals.get("industry"),
                "fcf_growth": (
                    fundamentals.get(
                        "fcf_growth"
                    )
                ),

                "roic": (
                    fundamentals.get(
                        "roic"
                    )
                ),
            })

        except Exception as e:

            print(
                f"FUNDAMENTALS ERROR "
                f"{original_symbol} "
                f"-> {yahoo_symbol}: "
                f"{e}"
            )

            results.append({

                "symbol": original_symbol,

                "yahoo_symbol": yahoo_symbol,

                "name": stock.get(
                    "name"
                ),

                "sector": stock.get(
                    "sector"
                ),
                "industry": None,
                "country": stock.get(
                    "country"
                ),

                "platform": stock.get(
                    "platform"
                ),

                "fcf_yield": None,
                "fcf_growth": None,
                "roic": None,
            })

    return results