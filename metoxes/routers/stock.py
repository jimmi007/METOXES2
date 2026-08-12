import logging

from fastapi import APIRouter, HTTPException
from metoxes.services.price_service import get_current_price
from metoxes.database import database, stock_table
from metoxes.models.stock import Stock, StockIn, StockUpdate


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

            query = (
                stock_table.update()
                .where(
                    stock_table.c.id == stock.id
                )
                .values(
                    current_price=current_price,
                    profit_loss=profit_loss,
                )
            )

            await database.execute(query)

            updated += 1

            logger.info(
                "Price updated | %s | %.2f",
                stock.symbol,
                current_price,
            )

        except Exception as exc:
            logger.exception(
                "Price update failed for %s",
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

@router.delete(
    "/stock",
    status_code=200,
)
async def delete_all_stocks():

    await database.execute(
        stock_table.delete()
    )

    logger.warning(
        "ALL stocks deleted"
    )

    return {
        "message": "All stocks deleted successfully"
    }