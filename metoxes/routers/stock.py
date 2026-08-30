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
from fastapi import APIRouter, HTTPException
from metoxes.services.price_service import get_current_price
from metoxes.database import database, stock_table
from metoxes.models.stock import Stock, StockIn, StockUpdate
from fastapi import UploadFile, File, HTTPException
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

@router.post("/stock/import-excel")
async def import_excel(file: UploadFile = File(...)):

    if not file.filename.endswith(".xlsx"):
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
            detail=f"Δεν υπάρχει φύλλο merged. Υπάρχουν: {workbook.sheetnames}",
        )

    sheet = workbook[sheet_name]

    print("MAX:", sheet.max_row, sheet.max_column)

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

    print("HEADERS:", headers)

    inserted = 0
    updated = 0
    skipped_incomplete = 0

    required_fields = [
        "purchase_date",
        "sector",
        "symbol",
        "company_name",
        "platform",
        "purchase_price",
        "quantity",
    ]

    for values in sheet.iter_rows(
        min_row=2,
        values_only=True,
    ):
        row = dict(zip(headers, values))

        missing = [
            field
            for field in required_fields
            if row.get(field) is None
            or row.get(field) == ""
        ]

        if missing:
            skipped_incomplete += 1
            continue

        symbol = str(
            row["symbol"]
        ).strip()

        platform = str(
            row["platform"]
        ).strip()

        purchase_price = float(
            str(row["purchase_price"])
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )

        quantity = float(
            str(row["quantity"])
            .replace(" ", "")
            .replace(",", ".")
            .strip()
        )

        existing_stock = await database.fetch_one(
            stock_table.select().where(
                (
                    stock_table.c.symbol == symbol
                )
                &
                (
                    stock_table.c.platform == platform
                )
            )
        )

        # ΥΠΑΡΧΕΙ → UPDATE
        if existing_stock:

            update_data = {
                "purchase_date": row["purchase_date"],
                "sector": str(
                    row["sector"]
                ).strip(),
                "name": str(
                    row["company_name"]
                ).strip(),
                "purchase_price": purchase_price,
                "quantity": quantity,
            }

            await database.execute(
                stock_table.update()
                .where(
                    stock_table.c.id
                    == existing_stock["id"]
                )
                .values(**update_data)
            )

            updated += 1
            continue

        # ΔΕΝ ΥΠΑΡΧΕΙ → INSERT
        data = {
            "purchase_date": row["purchase_date"],
            "sector": str(
                row["sector"]
            ).strip(),
            "symbol": symbol,
            "name": str(
                row["company_name"]
            ).strip(),
            "platform": platform,
            "purchase_price": purchase_price,
            "quantity": quantity,
            "current_price": None,
            "profit_loss": None,
            "vusa_return": None,
            "excess_return": None,
            "currency": None,
            "purchase_value_eur": None,
        }

        await database.execute(
            stock_table.insert().values(**data)
        )

        inserted += 1

    logger.info(
        "Excel import completed | inserted=%s | updated=%s | incomplete=%s",
        inserted,
        updated,
        skipped_incomplete,
    )

    return {
        "message": "Excel import completed",
        "inserted": inserted,
        "updated": updated,
        "skipped_incomplete": skipped_incomplete,
    }

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

    for stock in stocks:
        try:
            current_price = get_current_price(
                stock.symbol
            )

            profit_loss = (
                current_price - stock.purchase_price
            ) * stock.quantity

            stock_return = (
                (
                    current_price - stock.purchase_price
                )
                / stock.purchase_price
                * 100
            )

            vusa_return = get_benchmark_return(
                stock.purchase_date
            )

            excess_return = (
                stock_return - vusa_return
                if vusa_return is not None
                else None
            )

            currency, eur_rate = get_currency_and_eur_rate(
                stock.symbol
            )
            purchase_value_eur = (
                stock.purchase_price
                * stock.quantity
                * eur_rate
            )

            query = (
                stock_table.update()
                .where(
                    stock_table.c.id == stock.id
                )
                .values(
                    current_price=current_price,
                    profit_loss=profit_loss,
                    vusa_return=(
                        round(vusa_return, 2)
                        if vusa_return is not None
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
                "Updated | %s | currency=%s | purchase_value_eur=%.2f",
                stock.symbol,
                currency,
                purchase_value_eur,
            )

        except Exception as exc:
            logger.exception(
                "Update failed for %s",
                stock.symbol,
            )

            errors.append({
                "symbol": stock.symbol,
                "error": str(exc),
            })

    return {
        "updated": updated,
        "errors": errors,
    }
from sqlalchemy import text


from sqlalchemy import text


@router.delete("/stocks/delete-all", status_code=200)
async def delete_all_stocks():

    await database.execute(
        text("TRUNCATE TABLE public.stocks RESTART IDENTITY")
    )

    return {
        "message": "All stocks deleted and ID reset"
    }




@router.delete(
    "/stock/{stock_id}",
    status_code=200,
)
async def delete_stock(stock_id: int):

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

    return {
        "message": "Stock deleted successfully",
        "id": stock_id,
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
