from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI
from fastapi.responses import FileResponse

from metoxes.database import database, engine, metadata
from metoxes.routers.stock import router as stock_router
from metoxes.logging_conf import configure_logging


configure_logging()
logger = logging.getLogger("metoxes")


@asynccontextmanager
async def lifespan(app: FastAPI):

    logger.info("Starting Stocks API")

    metadata.create_all(engine)

    await database.connect()
    logger.info("Database connected")

    yield

    await database.disconnect()


app = FastAPI(lifespan=lifespan)

app.include_router(stock_router)


@app.get("/")
async def root():
    return {"message": "Stocks API is running"}


@app.get("/chart")
async def chart():
    return FileResponse(
        "metoxes/templates/chart.html"
    )