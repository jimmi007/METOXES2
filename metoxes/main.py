from fastapi import FastAPI
from metoxes.routers.stock import router as stock_router


app = FastAPI(
    title="METOXES2 API",
    version="1.0"
)


app.include_router(stock_router)


@app.get("/")
async def root():
    return {
        "message": "METOXES2 is running"
    }