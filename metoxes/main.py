import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from metoxes.config import config
from metoxes.database import database, engine, metadata
from metoxes.logging_conf import configure_logging
from metoxes.routers.stock import router as stock_router


# Ενεργοποίηση logging
configure_logging()

logger = logging.getLogger("metoxes")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Stocks API")
    logger.info("Environment: %s", config.ENV_STATE)

    metadata.create_all(engine)

    await database.connect()
    logger.info("Database connected")

    yield

    await database.disconnect()
    logger.info("Database disconnected")


app = FastAPI(lifespan=lifespan)

app.include_router(stock_router)


@app.get("/")
async def root():
    return {
        "message": "Stocks API is running"
    }