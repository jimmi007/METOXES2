import os
import httpx

from dotenv import load_dotenv

from metoxes.services.excel_service import get_symbol_lookup
from metoxes.services.price_service import (
    get_monthly_percent_change,
    get_current_price,
    get_stock_currency,
    get_current_eur_rate,
    get_historical_eur_rate,
    get_vuaa_return,
    get_stock_info,
)


load_dotenv()

API_KEY = os.getenv("TRADING212_API_KEY")
API_SECRET = os.getenv("TRADING212_API_SECRET")

BASE_URL = "https://live.trading212.com/api/v0"


# ==========================================================
# CLEAN TRADING212 POSITIONS
# ==========================================================

async def get_clean_positions():

    positions = await get_positions()
    symbol_lookup = get_symbol_lookup()

    # --------------------------------------------------
    # TRADING212 TICKER -> YAHOO FINANCE TICKER
    # --------------------------------------------------

    TICKER_MAP = {
        "VUAAm_EQ": "VUAA.L",
        "VUSAl_EQ": "VUSA.L",
        "IUISl_EQ": "IUIS.L",
        "VACQ_US_EQ": "RKLB",
        "SXLIl_EQ": "SXLI.L",
        "SXRUd_EQ": "SXRU.DE",
        "EGLNl_EQ": "EGLN.L",
        "SXR8d_EQ": "SXR8.DE",
    }

    clean_positions = []

    # ==================================================
    # ΔΙΑΒΑΖΟΥΜΕ ΟΛΕΣ ΤΙΣ ΘΕΣΕΙΣ
    # ==================================================

    for p in positions:

        t212_ticker = p["instrument"]["ticker"]
        name = p["instrument"]["name"]

        # --------------------------------------------------
        # YAHOO SYMBOL
        # --------------------------------------------------

        if t212_ticker in TICKER_MAP:

            yahoo_symbol = TICKER_MAP[
                t212_ticker
            ]

        else:

            # π.χ. BSX_US_EQ -> BSX
            base_symbol = t212_ticker.split(
                "_"
            )[0]

            yahoo_symbol = symbol_lookup.get(
                base_symbol.upper()
            )

            if not yahoo_symbol:
                yahoo_symbol = base_symbol

        # --------------------------------------------------
        # SECTOR / COUNTRY
        # Από Yahoo Finance
        # --------------------------------------------------

        stock_info = get_stock_info(
            yahoo_symbol
        )

        sector = stock_info.get(
            "sector"
        )

        country = stock_info.get(
            "country"
        )

        # --------------------------------------------------
        # ΒΑΣΙΚΑ ΣΤΟΙΧΕΙΑ ΘΕΣΗΣ
        # --------------------------------------------------

        purchase_date = p["createdAt"]

        quantity = float(
            p["quantity"]
        )

        try:

            # --------------------------------------------------
            # TRADING212 WALLET VALUES
            #
            # Τα ποσά αυτά είναι ήδη σε EUR
            # --------------------------------------------------

            wallet = p["walletImpact"]

            total_cost = float(
                wallet["totalCost"]
            )

            current_value = float(
                wallet["currentValue"]
            )

            unrealized = float(
                wallet["unrealizedProfitLoss"]
            )

            # --------------------------------------------------
            # PURCHASE PRICE ΣΕ EUR
            # --------------------------------------------------

            if quantity > 0:

                purchase_price_eur = (
                    total_cost / quantity
                )

            else:

                purchase_price_eur = None

            # --------------------------------------------------
            # CURRENT PRICE ΣΕ EUR
            # --------------------------------------------------

            if quantity > 0:

                current_price_eur = (
                    current_value / quantity
                )

            else:

                current_price_eur = None

            # --------------------------------------------------
            # MARKET VALUE ΣΕ EUR
            # --------------------------------------------------

            market_value_eur = (
                current_value
            )

            # --------------------------------------------------
            # PERCENT CHANGE ΣΕ EUR
            # --------------------------------------------------

            if total_cost != 0:

                percent_change = (
                    unrealized
                    / total_cost
                ) * 100

            else:

                percent_change = None

            # --------------------------------------------------
            # MONTHLY CHANGE
            # Από Yahoo Finance
            # --------------------------------------------------

            try:

                monthly_change = (
                    get_monthly_percent_change(
                        yahoo_symbol
                    )
                )

            except Exception as e:

                print(
                    f"MONTHLY ERROR "
                    f"{yahoo_symbol}: {e}"
                )

                monthly_change = None

            # --------------------------------------------------
            # VUAA BENCHMARK RETURN
            # --------------------------------------------------

            try:

                vuaa_return = (
                    get_vuaa_return(
                        purchase_date
                    )
                )

            except Exception as e:

                print(
                    f"VUAA ERROR "
                    f"{yahoo_symbol}: {e}"
                )

                vuaa_return = None

            # --------------------------------------------------
            # EXCESS RETURN
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
            # FX IMPACT
            # Χρήσιμο για USD / GBP θέσεις
            # --------------------------------------------------

            fx_impact = wallet.get(
                "fxImpact"
            )

            # --------------------------------------------------
            # ΑΠΟΘΗΚΕΥΣΗ
            # --------------------------------------------------

            clean_positions.append({

                "symbol":
                    yahoo_symbol,

                "name":
                    name,

                "sector":
                    sector,

                "country":
                    country,

                "platform":
                    "Trading212",

                "purchase_date":
                    purchase_date,

                "purchase_price":
                    round(
                        purchase_price_eur,
                        2
                    )
                    if purchase_price_eur
                    is not None
                    else None,

                "quantity":
                    quantity,

                "current_price":
                    round(
                        current_price_eur,
                        2
                    )
                    if current_price_eur
                    is not None
                    else None,

                "market_value":
                    round(
                        market_value_eur,
                        2
                    ),

                "percent_change":
                    round(
                        percent_change,
                        2
                    )
                    if percent_change
                    is not None
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
                    if excess_return
                    is not None
                    else None,

                "fx_impact":
                    fx_impact,

                "status":
                    "OK"
            })

        except Exception as e:

            # --------------------------------------------------
            # ΑΝ ΥΠΑΡΞΕΙ ΠΡΟΒΛΗΜΑ
            # ΔΕΝ ΣΤΑΜΑΤΑ ΟΛΟ ΤΟ PORTFOLIO
            # --------------------------------------------------

            print(
                f"SKIP {name} | "
                f"T212={t212_ticker} | "
                f"Yahoo={yahoo_symbol} | "
                f"Error={e}"
            )

            clean_positions.append({

                "symbol":
                    yahoo_symbol,

                "name":
                    name,

                "sector":
                    sector,

                "country":
                    country,

                "platform":
                    "Trading212",

                "purchase_date":
                    purchase_date,

                "purchase_price":
                    None,

                "quantity":
                    quantity,

                "current_price":
                    None,

                "market_value":
                    None,

                "percent_change":
                    None,

                "monthly_percent_change":
                    None,

                "vuaa_return":
                    None,

                "excess_return":
                    None,

                "fx_impact":
                    None,

                "status":
                    "ERROR",

                "trading212_ticker":
                    t212_ticker
            })

    # ==================================================
    # PORTFOLIO WEIGHT
    # ==================================================

    total_portfolio_value = sum(
        stock["market_value"]
        for stock in clean_positions
        if stock.get("market_value")
        is not None
    )

    for stock in clean_positions:

        market_value = stock.get(
            "market_value"
        )

        if (
            market_value is not None
            and total_portfolio_value > 0
        ):

            stock["portfolio_weight"] = round(
                (
                    market_value
                    / total_portfolio_value
                ) * 100,
                2
            )

        else:

            stock["portfolio_weight"] = None

    return clean_positions


# ==========================================================
# RAW TRADING212 POSITIONS
# ==========================================================

async def get_positions():

    if not API_KEY or not API_SECRET:

        raise ValueError(
            "Λείπει το Trading212 API Key "
            "ή API Secret από το .env"
        )

    url = (
        f"{BASE_URL}/equity/positions"
    )

    async with httpx.AsyncClient() as client:

        response = await client.get(
            url,
            auth=(
                API_KEY,
                API_SECRET
            ),
            timeout=30
        )

        response.raise_for_status()

        return response.json()