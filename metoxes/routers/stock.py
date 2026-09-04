import logging


from metoxes.services.price_service import (
    get_current_price,
    get_benchmark_return,
)
from metoxes.services.price_service import (
    get_current_price,
    get_benchmark_return,
    get_currency_and_eur_rate,
)
from fastapi.responses import StreamingResponse
from fastapi import APIRouter, HTTPException, UploadFile, File
from openpyxl import load_workbook
from io import BytesIO
from datetime import date

from metoxes.services.price_service import get_current_price
from metoxes.database import database, stock_table
from metoxes.models.stock import Stock, StockIn, StockUpdate

from io import BytesIO
from openpyxl import load_workbook
from metoxes.services.price_service import get_benchmark_return
# TEST: δείχνει ποιο stock.py φορτώνεται
print("STOCK FILE LOADED:", __file__, flush=True)


router = APIRouter()

logger = logging.getLogger("metoxes.stock")
logger.setLevel(logging.INFO)


@router.post(
    "/stock",
    response_model=Stock,
    status_code=201,
)
async def create_stock(stock: StockIn):

    logger.info(
        "POST ξεκίνησε | symbol=%s",
        stock.symbol,
    )

    data = {
        **stock.model_dump(),
        "current_price": None,
        "profit_loss": None,
    }

    query = stock_table.insert().values(data)

    stock_id = await database.execute(query)

    logger.info(
        "Stock inserted | id=%s | symbol=%s",
        stock_id,
        stock.symbol,
    )

    return {
        **data,
        "id": stock_id,
    }
@router.post("/stock/import-excel")

async def import_excel(file: UploadFile = File(...)):

    # ---------------------------------------------------------
    # 1. ΕΛΕΓΧΟΣ ΑΡΧΕΙΟΥ
    # ---------------------------------------------------------

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(
            status_code=400,
            detail="Το αρχείο πρέπει να είναι .xlsx",
        )

    contents = await file.read()

    workbook = load_workbook(
        BytesIO(contents),
        data_only=True,
    )

    print("SHEETS:", workbook.sheetnames)

    # ---------------------------------------------------------
    # 2. ΒΡΙΣΚΟΥΜΕ ΤΟ ΦΥΛΛΟ merged
    # ---------------------------------------------------------

    sheet_name = next(
        (
            name
            for name in workbook.sheetnames
            if name.strip().lower() == "merged"
        ),
        None,
    )

    if sheet_name is None:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Δεν υπάρχει φύλλο merged. "
                f"Υπάρχουν: {workbook.sheetnames}"
            ),
        )

    sheet = workbook[sheet_name]

    print(
        "MAX:",
        sheet.max_row,
        sheet.max_column,
    )

    # ---------------------------------------------------------
    # 3. HEADERS
    # ---------------------------------------------------------

    import re

    headers = [
        re.sub(
            r"[\s_]+",
            "_",
            str(cell.value).strip().lower(),
        )
        if cell.value is not None
        else None
        for cell in sheet[1]
    ]

    print(
        "HEADERS:",
        headers,
    )

    # ---------------------------------------------------------
    # 4. ΥΠΟΧΡΕΩΤΙΚΕΣ ΣΤΗΛΕΣ
    # ---------------------------------------------------------

    required_fields = [
        "purchase_date",
        "symbol",
        "platform",
        "purchase_price",
        "quantity",
    ]

    missing_headers = [
        field
        for field in required_fields
        if field not in headers
    ]

    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=(
                "Λείπουν οι στήλες: "
                + ", ".join(missing_headers)
            ),
        )

    # ---------------------------------------------------------
    # 5. ΜΕΤΡΗΤΕΣ
    # ---------------------------------------------------------

    inserted = 0
    updated = 0
    deleted = 0
    skipped_incomplete = 0

    excel_keys = set()

    # ---------------------------------------------------------
    # 6. ΔΙΑΒΑΖΟΥΜΕ ΤΟ EXCEL
    # ---------------------------------------------------------

    for values in sheet.iter_rows(
        min_row=2,
        values_only=True,
    ):

        row = dict(
            zip(
                headers,
                values,
            )
        )

        # -----------------------------------------------------
        # ΕΛΕΓΧΟΣ ΑΠΑΡΑΙΤΗΤΩΝ ΠΕΔΙΩΝ
        # -----------------------------------------------------

        missing = [
            field
            for field in required_fields
            if row.get(field) is None
            or row.get(field) == ""
        ]

        if missing:
            skipped_incomplete += 1
            continue

        # -----------------------------------------------------
        # SYMBOL
        # -----------------------------------------------------

        symbol = str(
            row["symbol"]
        ).strip()

        # -----------------------------------------------------
        # PLATFORM
        # -----------------------------------------------------

        platform = str(
            row["platform"]
        ).strip()

        # -----------------------------------------------------
        # ΚΡΑΤΑΜΕ ΤΟ KEY
        # -----------------------------------------------------

        excel_keys.add(
            (
                symbol,
                platform,
            )
        )

        # -----------------------------------------------------
        # PURCHASE PRICE
        # -----------------------------------------------------

        purchase_price = float(
            str(
                row["purchase_price"]
            )
            .replace(
                " ",
                "",
            )
            .replace(
                ",",
                ".",
            )
            .strip()
        )

        # -----------------------------------------------------
        # QUANTITY
        # -----------------------------------------------------

        quantity = float(
            str(
                row["quantity"]
            )
            .replace(
                " ",
                "",
            )
            .replace(
                ",",
                ".",
            )
            .strip()
        )

        # -----------------------------------------------------
        # ΕΛΕΓΧΟΣ ΑΝ ΥΠΑΡΧΕΙ Η ΜΕΤΟΧΗ
        # -----------------------------------------------------

        existing_stock = (
            await database.fetch_one(
                stock_table.select().where(
                    (
                        stock_table.c.symbol
                        == symbol
                    )
                    &
                    (
                        stock_table.c.platform
                        == platform
                    )
                )
            )
        )

        # =====================================================
        # ΥΠΑΡΧΕΙ → UPDATE
        # =====================================================

        if existing_stock:

            update_data = {
                "purchase_date":
                    row["purchase_date"],

                "purchase_price":
                    purchase_price,

                "quantity":
                    quantity,
            }

            await database.execute(
                stock_table
                .update()
                .where(
                    stock_table.c.id
                    == existing_stock["id"]
                )
                .values(
                    **update_data
                )
            )

            updated += 1
            continue

        # =====================================================
        # ΔΕΝ ΥΠΑΡΧΕΙ → INSERT
        # =====================================================

        # -----------------------------------------------------
        # SECTOR
        # -----------------------------------------------------

        sector = "Unknown"

        if "sector" in headers:

            sector_value = row.get(
                "sector"
            )

            if (
                sector_value is not None
                and str(sector_value).strip() != ""
            ):
                sector = str(
                    sector_value
                ).strip()

        # -----------------------------------------------------
        # COMPANY NAME / NAME
        #
        # Αν δεν υπάρχει όνομα στο Excel,
        # χρησιμοποιούμε το SYMBOL.
        #
        # Έτσι η PostgreSQL δεν παίρνει NULL στο name.
        # -----------------------------------------------------

        company_name = None

        if "company_name" in headers:

            company_name_value = row.get(
                "company_name"
            )

            if (
                company_name_value is not None
                and str(company_name_value).strip() != ""
            ):
                company_name = str(
                    company_name_value
                ).strip()

        # Αν το Excel έχει στήλη "name",
        # τη χρησιμοποιούμε επίσης.
        if company_name is None and "name" in headers:

            name_value = row.get(
                "name"
            )

            if (
                name_value is not None
                and str(name_value).strip() != ""
            ):
                company_name = str(
                    name_value
                ).strip()

        # Τελικό fallback:
        # αν δεν έχουμε καθόλου όνομα → SYMBOL
        if company_name is None:
            company_name = symbol

        # -----------------------------------------------------
        # DATA ΓΙΑ INSERT
        # -----------------------------------------------------

        data = {

            "purchase_date":
                row["purchase_date"],

            "sector":
                sector,

            "symbol":
                symbol,

            "name":
                company_name,

            "platform":
                platform,

            "purchase_price":
                purchase_price,

            "quantity":
                quantity,

            "current_price":
                None,

            "profit_loss":
                None,

            "vusa_return":
                None,

            "excess_return":
                None,

            "currency":
                None,

            "purchase_value_eur":
                None,
        }

        await database.execute(
            stock_table
            .insert()
            .values(
                **data
            )
        )

        inserted += 1

    # ---------------------------------------------------------
    # 7. ΔΙΑΓΡΑΦΕΣ
    # ---------------------------------------------------------

    database_stocks = (
        await database.fetch_all(
            stock_table.select()
        )
    )

    deleted_stocks = []

    for stock in database_stocks:

        db_key = (
            str(
                stock["symbol"]
            ).strip(),

            str(
                stock["platform"]
            ).strip(),
        )

        if db_key not in excel_keys:

            await database.execute(
                stock_table
                .delete()
                .where(
                    stock_table.c.id
                    == stock["id"]
                )
            )

            deleted += 1

            deleted_stocks.append(
                {
                    "id":
                        stock["id"],

                    "symbol":
                        stock["symbol"],

                    "platform":
                        stock["platform"],
                }
            )

    # ---------------------------------------------------------
    # 8. LOG
    # ---------------------------------------------------------

    logger.info(
        "Excel sync completed | "
        "inserted=%s | "
        "updated=%s | "
        "deleted=%s | "
        "incomplete=%s",
        inserted,
        updated,
        deleted,
        skipped_incomplete,
    )

    # ---------------------------------------------------------
    # 9. RESPONSE
    # ---------------------------------------------------------

    return {

        "message":
            "Excel sync completed",

        "inserted":
            inserted,

        "updated":
            updated,

        "deleted":
            deleted,

        "skipped_incomplete":
            skipped_incomplete,

        "deleted_stocks":
            deleted_stocks,
    }


@router.get(
    "/stock",
    response_model=list[Stock],
)
async def get_all_stocks():

    query = stock_table.select().order_by(
        stock_table.c.id.asc()
    )

    stocks = await database.fetch_all(query)

    result = []

    for stock in stocks:
        result.append({
            "purchase_date": stock.purchase_date,
            "sector": stock.sector,
            "symbol": stock.symbol,
             "name":stock.name,
            "platform": stock.platform,
            "purchase_price": round(stock.purchase_price, 2),
            "quantity": stock.quantity,
            "id": stock.id,
            "current_price": (
                round(stock.current_price, 2)
                if stock.current_price is not None
                else None
            ),
            "profit_loss": (
                round(stock.profit_loss, 2)
                if stock.profit_loss is not None
                else None
            ),
        })

    return result


@router.patch(
    "/stock/{stock_id}",
    response_model=Stock,
)
async def update_stock(
    stock_id: int,
    stock: StockUpdate,
):

    print(
        f"PATCH FUNCTION EXECUTED | id={stock_id}",
        flush=True,
    )

    existing_stock = await database.fetch_one(
        stock_table.select().where(
            stock_table.c.id == stock_id
        )
    )

    if not existing_stock:
        raise HTTPException(
            status_code=404,
            detail="Stock not found",
        )

    changes = stock.model_dump(
        exclude_unset=True
    )

    if changes:
        await database.execute(
            stock_table.update()
            .where(stock_table.c.id == stock_id)
            .values(**changes)
        )

    updated_stock = await database.fetch_one(
        stock_table.select().where(
            stock_table.c.id == stock_id
        )
    )

    logger.info(
        "Stock updated | id=%s | changes=%s",
        stock_id,
        changes,
    )

    return updated_stock


@router.delete(
    "/stock/{stock_id}",
    status_code=200,
)
async def delete_stock(stock_id: int):

    print(
        f"DELETE FUNCTION EXECUTED | id={stock_id}",
        flush=True,
    )

    existing_stock = await database.fetch_one(
        stock_table.select().where(
            stock_table.c.id == stock_id
        )
    )

    if not existing_stock:
        raise HTTPException(
            status_code=404,
            detail="Stock not found",
        )

    await database.execute(
        stock_table.delete().where(
            stock_table.c.id == stock_id
        )
    )

    logger.info(
        "Stock deleted | id=%s | symbol=%s",
        stock_id,
        existing_stock.symbol,
    )

    return {
        "message": "Stock deleted successfully",
        "id": stock_id,
    }

@router.get("/stock/summary")
async def get_stock_summary():

    query = text("""
        SELECT
            symbol,
            monthly_percent_change
        FROM public.stock_summary
        ORDER BY symbol
    """)

    rows = await database.fetch_all(query)

    return [
        {
            "symbol": row["symbol"],
            "monthly_percent_change": float(row["monthly_percent_change"])
        }
        for row in rows
    ]

@router.post("/stock/update-prices")
async def update_all_prices():

    stocks = await database.fetch_all(
        stock_table.select()
    )

    updated = 0
    errors = []
    converted_stocks = []

    for stock in stocks:

        try:

            # -------------------------------------------------
            # 1. CURRENT PRICE ΣΤΟ ΑΡΧΙΚΟ ΝΟΜΙΣΜΑ
            # -------------------------------------------------

            original_current_price = get_current_price(
                stock.symbol
            )

            # -------------------------------------------------
            # 2. ΝΟΜΙΣΜΑ + ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
            # -------------------------------------------------

            currency, eur_rate = get_currency_and_eur_rate(
                stock.symbol
            )

            # -------------------------------------------------
            # 3. ΜΕΤΑΤΡΟΠΗ CURRENT PRICE ΣΕ EUR
            # -------------------------------------------------

            current_price_eur = round(
                original_current_price * eur_rate,
                4,
            )

            # -------------------------------------------------
            # 4. STOCK RETURN %
            #
            # purchase_price = EUR
            # current_price_eur = EUR
            # Άρα συγκρίνουμε EUR με EUR
            # -------------------------------------------------

            stock_return = (
                (
                    current_price_eur
                    - stock.purchase_price
                )
                / stock.purchase_price
                * 100
            )

            # -------------------------------------------------
            # 5. PROFIT / LOSS ΣΕ EUR
            # -------------------------------------------------

            profit_loss = (
                current_price_eur
                - stock.purchase_price
            ) * stock.quantity

            # -------------------------------------------------
            # 6. VUAA RETURN
            # -------------------------------------------------

            vuaa_return = get_benchmark_return(
                stock.purchase_date
            )

            # -------------------------------------------------
            # 7. EXCESS RETURN
            # -------------------------------------------------

            excess_return = (
                stock_return - vuaa_return
                if vuaa_return is not None
                else None
            )

            # -------------------------------------------------
            # 8. PURCHASE VALUE ΣΕ EUR
            #
            # purchase_price είναι ήδη EUR
            # Άρα ΔΕΝ ξαναπολλαπλασιάζουμε με eur_rate
            # -------------------------------------------------

            purchase_value_eur = (
                stock.purchase_price
                * stock.quantity
            )

            # -------------------------------------------------
            # 9. ΚΡΑΤΑΜΕ ΠΟΙΕΣ ΜΕΤΟΧΕΣ ΜΕΤΑΤΡΑΠΗΚΑΝ
            # -------------------------------------------------

            if currency != "EUR":

                converted_stocks.append(
                    {
                        "symbol": stock.symbol,
                        "original_currency": currency,
                        "eur_rate": round(
                            eur_rate,
                            6,
                        ),
                        "original_current_price": round(
                            original_current_price,
                            4,
                        ),
                        "current_price_eur": current_price_eur,
                    }
                )

            # -------------------------------------------------
            # 10. UPDATE DATABASE
            # -------------------------------------------------

            query = (
                stock_table.update()
                .where(
                    stock_table.c.id == stock.id
                )
                .values(
                    current_price=current_price_eur,

                    profit_loss=round(
                        profit_loss,
                        2,
                    ),

                    vusa_return=(
                        round(vuaa_return, 2)
                        if vuaa_return is not None
                        else None
                    ),

                    excess_return=(
                        round(excess_return, 2)
                        if excess_return is not None
                        else None
                    ),

                    currency=currency,

                    purchase_value_eur=round(
                        purchase_value_eur,
                        2,
                    ),
                )
            )

            await database.execute(query)

            updated += 1

            logger.info(
                "Updated | %s | %s | "
                "Original=%.4f | "
                "EUR=%.4f | "
                "Return=%.2f%% | "
                "Rate=%.6f",
                stock.symbol,
                currency,
                original_current_price,
                current_price_eur,
                stock_return,
                eur_rate,
            )

        except Exception as exc:

            logger.exception(
                "Update failed for %s",
                stock.symbol,
            )

            errors.append(
                {
                    "symbol": stock.symbol,
                    "error": str(exc),
                }
            )

    return {
        "updated": updated,
        "errors": errors,
        "converted_to_eur": converted_stocks,
    }




@router.get("/stock/benchmark")
async def get_stocks_with_benchmark():

    stocks = await database.fetch_all(
        stock_table.select().order_by(
            stock_table.c.id.asc()
        )
    )

    result = []

    for stock in stocks:

        if stock.current_price is None:
            stock_return = None
        else:
            stock_return = (
                (
                    stock.current_price
                    - stock.purchase_price
                )
                / stock.purchase_price
                * 100
            )

        benchmark_return = get_benchmark_return(
            stock.purchase_date
        )

        if (
            stock_return is not None
            and benchmark_return is not None
        ):
            excess_return = (
                stock_return
                - benchmark_return
            )
        else:
            excess_return = None

        result.append(
            {
                "symbol": stock.symbol,
                "name": stock.name,
                "platform": stock.platform,
                "purchase_date": stock.purchase_date,
                "purchase_price": round(
                    stock.purchase_price,
                    2,
                ),
                "current_price": (
                    round(
                        stock.current_price,
                        2,
                    )
                    if stock.current_price is not None
                    else None
                ),
                "stock_return": (
                    round(stock_return, 2)
                    if stock_return is not None
                    else None
                ),
                "vusa_return": benchmark_return,
                "excess_return": (
                    round(excess_return, 2)
                    if excess_return is not None
                    else None
                ),
            }
        )

    return result
@router.post("/stock/update-excel")
async def update_excel(file: UploadFile = File(...)):

    # ---------------------------------------------------------
    # 1. ΕΛΕΓΧΟΣ ΑΡΧΕΙΟΥ
    # ---------------------------------------------------------

    filename = file.filename or ""

    if not filename.lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(
            status_code=400,
            detail="Το αρχείο πρέπει να είναι .xlsx ή .xlsm",
        )

    contents = await file.read()

    is_xlsm = filename.lower().endswith(".xlsm")

    workbook = load_workbook(
        BytesIO(contents),
        keep_vba=is_xlsm,
        data_only=False,
    )

    # Χρησιμοποιούμε το πρώτο φύλλο
    sheet = workbook.worksheets[0]

    # ---------------------------------------------------------
    # 2. HEADERS
    # ---------------------------------------------------------

    headers = {}

    for cell in sheet[1]:
        if cell.value is not None:
            header = str(cell.value).strip().lower()
            headers[header] = cell.column

    required_headers = [
        "symbol",
        "purchase_date",
        "purchase_price",
        "quantity",
    ]

    missing_headers = [
        header
        for header in required_headers
        if header not in headers
    ]

    if missing_headers:
        raise HTTPException(
            status_code=400,
            detail=(
                "Λείπουν οι στήλες: "
                + ", ".join(missing_headers)
            ),
        )

    # ---------------------------------------------------------
    # 3. ΣΤΗΛΕΣ ΠΟΥ ΕΝΗΜΕΡΩΝΟΥΜΕ
    # ---------------------------------------------------------

    COL_PORTFOLIO_WEIGHT = 6   # F
    COL_CURRENT_PRICE = 8      # H
    COL_PERCENT_CHANGE = 9     # I
    COL_MONTHLY_PERCENT = 10   # J
    COL_VUAA_RETURN = 11       # K
    COL_EXCESS_RETURN = 12     # L

    # Όνομα στήλης K
    sheet.cell(
        row=1,
        column=COL_VUAA_RETURN,
    ).value = "vuaa_return"

    # ---------------------------------------------------------
    # 4. ΠΡΩΤΟ ΠΕΡΑΣΜΑ
    # ---------------------------------------------------------

    row_data = []
    errors = []

    total_current_value = 0

    today = date.today()

    for row_number in range(
        2,
        sheet.max_row + 1,
    ):

        symbol = sheet.cell(
            row=row_number,
            column=headers["symbol"],
        ).value

        purchase_date = sheet.cell(
            row=row_number,
            column=headers["purchase_date"],
        ).value

        purchase_price = sheet.cell(
            row=row_number,
            column=headers["purchase_price"],
        ).value

        quantity = sheet.cell(
            row=row_number,
            column=headers["quantity"],
        ).value

        # Αν δεν υπάρχει symbol, είναι κενή/dashboard γραμμή
        if symbol is None or str(symbol).strip() == "":
            continue

        symbol = str(symbol).strip()

        try:

            # ---------------------------------------------
            # PURCHASE PRICE
            # ---------------------------------------------

            purchase_price = float(
                str(purchase_price)
                .replace(" ", "")
                .replace(",", ".")
                .strip()
            )

            # ---------------------------------------------
            # QUANTITY
            # ---------------------------------------------

            quantity = float(
                str(quantity)
                .replace(" ", "")
                .replace(",", ".")
                .strip()
            )

            # ---------------------------------------------
            # CURRENT PRICE ΣΤΟ ΑΡΧΙΚΟ ΝΟΜΙΣΜΑ
            # ---------------------------------------------

            original_current_price = get_current_price(
                symbol
            )

            # ---------------------------------------------
            # ΝΟΜΙΣΜΑ + ΙΣΟΤΙΜΙΑ ΠΡΟΣ EUR
            # ---------------------------------------------

            currency, eur_rate = get_currency_and_eur_rate(
                symbol
            )

            # ---------------------------------------------
            # CURRENT PRICE ΣΕ EUR
            # ---------------------------------------------

            current_price_eur = (
                original_current_price
                * eur_rate
            )

            # ---------------------------------------------
            # I - TOTAL RETURN %
            #
            # EUR με EUR
            # ---------------------------------------------

            percent_change = (
                (
                    current_price_eur
                    - purchase_price
                )
                / purchase_price
                * 100
            )

            # ---------------------------------------------
            # J - MONTHLY RETURN %
            # ---------------------------------------------

            months = (
                (today.year - purchase_date.year)
                * 12
                +
                (
                    today.month
                    - purchase_date.month
                )
                + 1
            )

            if months < 1:
                months = 1

            monthly_percent_change = (
                percent_change
                / months
            )

            # ---------------------------------------------
            # K - VUAA RETURN
            # ---------------------------------------------

            vuaa_return = get_benchmark_return(
                purchase_date
            )

            # ---------------------------------------------
            # L - EXCESS RETURN
            # ---------------------------------------------

            if vuaa_return is not None:
                excess_return = (
                    percent_change
                    - vuaa_return
                )
            else:
                excess_return = None

            # ---------------------------------------------
            # CURRENT VALUE ΣΕ EUR
            # ---------------------------------------------

            current_value_eur = (
                current_price_eur
                * quantity
            )

            total_current_value += (
                current_value_eur
            )

            # ---------------------------------------------
            # ΚΡΑΤΑΜΕ ΤΑ ΔΕΔΟΜΕΝΑ
            # ---------------------------------------------

            row_data.append(
                {
                    "row": row_number,
                    "symbol": symbol,
                    "currency": currency,
                    "eur_rate": eur_rate,
                    "original_current_price":
                        original_current_price,
                    "current_price":
                        current_price_eur,
                    "percent_change":
                        percent_change,
                    "monthly_percent_change":
                        monthly_percent_change,
                    "vuaa_return":
                        vuaa_return,
                    "excess_return":
                        excess_return,
                    "current_value_eur":
                        current_value_eur,
                }
            )

            logger.info(
                "Excel | %s | currency=%s | "
                "original=%.4f | "
                "EUR=%.4f | "
                "return=%.2f%% | "
                "rate=%.6f",
                symbol,
                currency,
                original_current_price,
                current_price_eur,
                percent_change,
                eur_rate,
            )

        except Exception as exc:

            logger.exception(
                "Excel update failed | %s",
                symbol,
            )

            errors.append(
                {
                    "symbol": symbol,
                    "error": str(exc),
                }
            )

    # ---------------------------------------------------------
    # 5. ΔΕΥΤΕΡΟ ΠΕΡΑΣΜΑ
    # ---------------------------------------------------------

    for item in row_data:

        row_number = item["row"]

        # ---------------------------------------------
        # F - PORTFOLIO WEIGHT
        # ---------------------------------------------

        if total_current_value > 0:
            portfolio_weight = (
                item["current_value_eur"]
                / total_current_value
                * 100
            )
        else:
            portfolio_weight = None

        sheet.cell(
            row=row_number,
            column=COL_PORTFOLIO_WEIGHT,
        ).value = (
            round(portfolio_weight, 2)
            if portfolio_weight is not None
            else None
        )

        # ---------------------------------------------
        # H - CURRENT PRICE EUR
        # ---------------------------------------------

        sheet.cell(
            row=row_number,
            column=COL_CURRENT_PRICE,
        ).value = round(
            item["current_price"],
            2,
        )

        # ---------------------------------------------
        # I - TOTAL RETURN %
        # ---------------------------------------------

        sheet.cell(
            row=row_number,
            column=COL_PERCENT_CHANGE,
        ).value = round(
            item["percent_change"],
            2,
        )

        # ---------------------------------------------
        # J - MONTHLY RETURN %
        # ---------------------------------------------

        sheet.cell(
            row=row_number,
            column=COL_MONTHLY_PERCENT,
        ).value = round(
            item["monthly_percent_change"],
            2,
        )

        # ---------------------------------------------
        # K - VUAA RETURN
        # ---------------------------------------------

        sheet.cell(
            row=row_number,
            column=COL_VUAA_RETURN,
        ).value = (
            round(
                item["vuaa_return"],
                2,
            )
            if item["vuaa_return"] is not None
            else None
        )

        # ---------------------------------------------
        # L - EXCESS RETURN
        # ---------------------------------------------

        sheet.cell(
            row=row_number,
            column=COL_EXCESS_RETURN,
        ).value = (
            round(
                item["excess_return"],
                2,
            )
            if item["excess_return"] is not None
            else None
        )

    # ---------------------------------------------------------
    # 6. ΜΟΡΦΟΠΟΙΗΣΗ
    #
    # ΜΟΝΟ ΣΤΙΣ ΓΡΑΜΜΕΣ ΤΩΝ ΜΕΤΟΧΩΝ
    # ΔΕΝ ΠΕΙΡΑΖΟΥΜΕ ΤΑ DASHBOARD CELLS
    # ---------------------------------------------------------

    for row_number in range(
        2,
        sheet.max_row + 1,
    ):

        symbol_value = sheet.cell(
            row=row_number,
            column=headers["symbol"],
        ).value

        # Αν δεν υπάρχει symbol,
        # δεν πειράζουμε καθόλου αυτή τη γραμμή
        if (
            symbol_value is None
            or str(symbol_value).strip() == ""
        ):
            continue

        # F - Portfolio Weight
        sheet.cell(
            row=row_number,
            column=COL_PORTFOLIO_WEIGHT,
        ).number_format = '0.00"%"'

        # H - Current Price EUR
        sheet.cell(
            row=row_number,
            column=COL_CURRENT_PRICE,
        ).number_format = '€ #,##0.00'

        # I, J, K, L
        for column in [
            COL_PERCENT_CHANGE,
            COL_MONTHLY_PERCENT,
            COL_VUAA_RETURN,
            COL_EXCESS_RETURN,
        ]:

            sheet.cell(
                row=row_number,
                column=column,
            ).number_format = '0.00"%"'

    # ---------------------------------------------------------
    # 7. ΑΠΟΘΗΚΕΥΣΗ
    # ---------------------------------------------------------

    output = BytesIO()

    workbook.save(output)

    output.seek(0)

    if is_xlsm:

        output_filename = (
            "stock_summary_updated.xlsm"
        )

        media_type = (
            "application/vnd.ms-excel."
            "sheet.macroEnabled.12"
        )

    else:

        output_filename = (
            "stock_summary_updated.xlsx"
        )

        media_type = (
            "application/"
            "vnd.openxmlformats-officedocument."
            "spreadsheetml.sheet"
        )

    logger.info(
        "Excel updated | rows=%s | errors=%s",
        len(row_data),
        len(errors),
    )

    return StreamingResponse(
        output,
        media_type=media_type,
        headers={
            "Content-Disposition":
                f'attachment; filename="{output_filename}"',

            "X-Updated-Rows":
                str(len(row_data)),

            "X-Errors":
                str(len(errors)),
        },
    )