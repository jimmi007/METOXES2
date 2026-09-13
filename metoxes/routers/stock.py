from io import BytesIO

from fastapi import APIRouter, UploadFile, File, HTTPException
from openpyxl import load_workbook

from metoxes.services.trading212_service import get_positions


router = APIRouter()


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