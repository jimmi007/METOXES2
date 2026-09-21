from io import BytesIO
from metoxes.services.excel_service import update_portfolio_excel
from fastapi import APIRouter, UploadFile, File, HTTPException
from metoxes.services.freedom_service import test_freedom_connection
from openpyxl import load_workbook
from metoxes.services.freedom_service import (
    test_freedom_connection,
    get_freedom_positions,
    get_freedom_trades,
)
from metoxes.services.capital_service import create_capital_session
from metoxes.services.price_service import get_monthly_percent_change
from metoxes.services.trading212_service import get_positions
from metoxes.services.excel_service import get_excel_stocks
from metoxes.services.excel_service import create_portfolio_excel
from metoxes.services.trading212_service import get_clean_positions
from metoxes.services.capital_service import (
    create_capital_session,
    get_capital_positions,
    get_clean_capital_positions,
)
router = APIRouter()
from metoxes.services.freedom_service import (
    test_freedom_connection,
    get_freedom_positions,
    get_freedom_trades,
    get_clean_freedom_positions,
)
from metoxes.services.freedom_service import get_freedom_connection

@router.get("/stocks")
async def get_stocks():
    return {
        "message": "METOXES2 REST API works"
    }


@router.get("/stocks/trading212")
async def get_trading212_positions():
    positions = await get_positions()

    return {
        "count": len(positions),
        "positions": positions
    }


@router.post("/stocks/read-excel")
async def read_excel(file: UploadFile = File(...)):

    if not file.filename.endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Το αρχείο πρέπει να είναι Excel (.xlsx ή .xlsm)"
        )

    contents = await file.read()

    workbook = load_workbook(
        BytesIO(contents),
        data_only=True
    )

    worksheet = workbook.active

    headers = []

    for cell in worksheet[1]:
        if cell.value is not None:
            headers.append(str(cell.value).strip().lower())
        else:
            headers.append(None)

    required_columns = [
        "symbol",
        "name",
        "sector",
        "country",
        "platform",
        "purchase_date",
        "purchase_price",
        "quantity",
        "current_price",
        "market_value",
        "percent_change",
        "portfolio_weight",
        "vuaa_return",
        "excess_return"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in headers
    ]

    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Λείπουν στήλες από το Excel",
                "missing_columns": missing_columns
            }
        )

    stocks = []

    for row in worksheet.iter_rows(
        min_row=2,
        values_only=True
    ):

        if not any(row):
            continue

        stock = {}

        for index, header in enumerate(headers):

            if header is not None:
                stock[header] = row[index]

        if not stock.get("symbol"):
            continue

        stocks.append(stock)

    return {
        "filename": file.filename,
        "count": len(stocks),
        "stocks": stocks
    }

@router.get("/stocks/monthly/{symbol}")
async def get_monthly_change(symbol: str):
    monthly_change = get_monthly_percent_change(symbol)

    return {
        "symbol": symbol,
        "monthly_percent_change": monthly_change
    }

@router.get("/stocks/excel-symbols")
async def get_symbols_from_excel():

    stocks = get_excel_stocks()

    return {
        "count": len(stocks),
        "stocks": stocks
    }

@router.get("/stocks/clean")
async def get_clean_stocks():
    stocks = await get_clean_positions()

    return {
        "count": len(stocks),
        "stocks": stocks
    }

@router.post("/stocks/create-excel")
async def create_excel():
    stocks = await get_clean_positions()

    file_path = create_portfolio_excel(stocks)

    return {
        "message": "Excel created successfully",
        "stocks": len(stocks),
        "file": str(file_path)
    }

@router.post("/stocks/update-excel")
async def update_excel():

    stocks = await get_clean_positions()

    file_path = update_portfolio_excel(stocks)

    return {
        "message": "Portfolio Excel updated successfully",
        "stocks": len(stocks),
        "file": str(file_path)
    }
@router.get("/stocks/capital/test")
async def test_capital():

    result = await create_capital_session()

    return result

@router.get("/stocks/capital")
async def capital_positions():

    positions = await get_capital_positions()

    return positions

@router.get("/stocks/capital/clean")
async def clean_capital_positions():

    stocks = await get_clean_capital_positions()

    return {
        "count": len(stocks),
        "stocks": stocks
    }

@router.get("/stocks/freedom/test")
async def test_freedom():
    return test_freedom_connection()

@router.get("/stocks/freedom")
async def freedom_positions():
    positions = get_freedom_positions()

    return {
        "count": len(positions),
        "positions": positions
    }


@router.get("/stocks/freedom/trades")
async def freedom_trades():
    trades = get_freedom_trades()

    return {
        "count": len(trades),
        "trades": trades
    }

from datetime import datetime


from datetime import datetime


def get_weighted_purchase_date(symbol, current_quantity, trades):
    """
    Υπολογίζει προσωρινά τη σταθμισμένη ημερομηνία αγοράς
    από τις διαθέσιμες συναλλαγές.

    ΔΕΝ κάνει νέο API request.
    """

    # Συναλλαγές μόνο της συγκεκριμένης μετοχής
    symbol_trades = [
        trade
        for trade in trades
        if trade.get("instr_nm") == symbol
    ]

    # Κρατάμε μόνο αγορές
    buys = [
        trade
        for trade in symbol_trades
        if str(trade.get("type")) == "1"
    ]

    if not buys:
        return None

    # Πιο πρόσφατες αγορές πρώτα
    buys.sort(
        key=lambda x: x.get("date", ""),
        reverse=True
    )

    remaining_quantity = current_quantity
    selected = []

    for trade in buys:

        if remaining_quantity <= 0:
            break

        trade_quantity = abs(
            float(trade.get("q", 0))
        )

        if trade_quantity <= 0:
            continue

        used_quantity = min(
            trade_quantity,
            remaining_quantity
        )

        date_string = trade.get("date")

        if date_string:
            trade_date = datetime.fromisoformat(
                date_string
            )

            selected.append(
                (trade_date, used_quantity)
            )

        remaining_quantity -= used_quantity

    if not selected:
        return None

    total_quantity = sum(
        quantity
        for _, quantity in selected
    )

    weighted_timestamp = sum(
        date.timestamp() * quantity
        for date, quantity in selected
    ) / total_quantity

    weighted_date = datetime.fromtimestamp(
        weighted_timestamp
    )

    return weighted_date.date().isoformat()


def get_clean_freedom_positions():
    """
    Καθαρίζει τις θέσεις Freedom24.

    Τα σημερινά χρηματικά μεγέθη μετατρέπονται σε EUR
    χρησιμοποιώντας τα currval που επιστρέφει η Freedom24.
    """

    connection = get_freedom_connection()

    response = connection.authorized_request(
        "getPositionJson"
    )

    result = response.get("result", {})
    portfolio = result.get("ps", {})

    positions = portfolio.get("pos", [])
    accounts = portfolio.get("acc", [])

    # --------------------------------------------------
    # 1. Βρίσκουμε τα currval ανά νόμισμα
    # --------------------------------------------------

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
    trades = get_freedom_trades()
    clean_positions = []

    # --------------------------------------------------
    # 2. Επεξεργασία κάθε ανοικτής θέσης
    # --------------------------------------------------

    for p in positions:

        symbol = p.get("i")
        name = p.get("name")
        currency = p.get("curr")

        quantity = float(p.get("q", 0))

        # Ημερομηνία αγοράς από το ιστορικό συναλλαγών
        purchase_date = get_weighted_purchase_date(
            symbol,
            quantity,
            trades
        )
        purchase_price_native = float(
            p.get("price_a", 0)
        )

        current_price_native = float(
            p.get("profit_price", 0)
        )

        market_value_native = float(
            p.get("market_value", 0)
        )

        profit_native = float(
            p.get("profit_close", 0)
        )

        # --------------------------------------------------
        # 3. Συντελεστής μετατροπής προς EUR
        # --------------------------------------------------

        if currency == "EUR":
            fx_to_eur = 1.0

        else:
            currency_currval = currency_rates.get(
                currency
            )

            if not currency_currval:
                fx_to_eur = None
            else:
                fx_to_eur = (
                    currency_currval /
                    eur_currval
                )

        # --------------------------------------------------
        # 4. Μετατροπή σημερινών ποσών σε EUR
        # --------------------------------------------------

        if fx_to_eur is not None:

            current_price_eur = (
                current_price_native *
                fx_to_eur
            )

            market_value_eur = (
                market_value_native *
                fx_to_eur
            )

            profit_eur = (
                profit_native *
                fx_to_eur
            )

        else:
            current_price_eur = None
            market_value_eur = None
            profit_eur = None

        # --------------------------------------------------
        # 5. Απόδοση θέσης
        # --------------------------------------------------

        total_cost_native = (
            purchase_price_native *
            quantity
        )

        if total_cost_native != 0:
            percent_change = (
                profit_native /
                total_cost_native *
                100
            )
        else:
            percent_change = None

        # --------------------------------------------------
        # 6. Τελικό αποτέλεσμα
        # --------------------------------------------------

        clean_positions.append({

            "symbol": symbol,

            "name": name,

            "platform": "Freedom24",

            "purchase_date": purchase_date,

            # Προς το παρόν η τιμή αγοράς
            # παραμένει στο αρχικό νόμισμα
            "purchase_price": round(
                purchase_price_native,
                2
            ),

            "quantity": quantity,

            # Τρέχουσα τιμή σε EUR
            "current_price": (
                round(current_price_eur, 2)
                if current_price_eur is not None
                else None
            ),

            # Τρέχουσα αξία θέσης σε EUR
            "market_value": (
                round(market_value_eur, 2)
                if market_value_eur is not None
                else None
            ),

            "percent_change": (
                round(percent_change, 2)
                if percent_change is not None
                else None
            ),

            # Κέρδος / ζημία σε EUR
            "profit": (
                round(profit_eur, 2)
                if profit_eur is not None
                else None
            ),

            "original_currency": currency,

            "fx_to_eur": (
                round(fx_to_eur, 6)
                if fx_to_eur is not None
                else None
            ),

            "status": (
                "OK"
                if fx_to_eur is not None
                else "FX_NOT_FOUND"
            )
        })

    return clean_positions

@router.get("/stocks/freedom/clean")
async def clean_freedom_positions():
    stocks = get_clean_freedom_positions()

    return {
        "count": len(stocks),
        "stocks": stocks
    }

@router.get("/stocks/freedom/debug")
async def freedom_debug():
    connection = get_freedom_connection()
    response = connection.authorized_request("getPositionJson")

    portfolio = response["result"]["ps"]
    accounts = portfolio.get("acc", [])

    return {
        "accounts_count": len(accounts),
        "account_keys": (
            list(accounts[0].keys())
            if accounts else []
        ),
        "currencies": [
            {
                "curr": a.get("curr"),
                "currval": a.get("currval")
            }
            for a in accounts
        ]
    }