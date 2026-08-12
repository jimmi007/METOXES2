from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict


class Platform(str, Enum):
    trading212 = "Trading212"
    capital = "Capital"
    freedom24 = "Freedom24"


class Sector(str, Enum):
    technology = "Technology"
    energy = "Energy"
    healthcare = "Healthcare"
    financials = "Financials"
    industrials = "Industrials"
    consumer = "Consumer"
    communication = "Communication"
    utilities = "Utilities"
    real_estate = "Real Estate"
    diafora="Diafora"


class StockIn(BaseModel):
    purchase_date: date
    sector: Sector
    symbol: str
    platform: Platform
    purchase_price: float
    quantity: float


class Stock(StockIn):
    model_config = ConfigDict(
        from_attributes=True
    )

    id: int
    current_price: float | None = None
    profit_loss: float | None = None

class StockUpdate(BaseModel):
    purchase_date: date | None = None
    sector: Sector | None = None
    symbol: str | None = None
    platform: Platform | None = None
    purchase_price: float | None = None
    quantity: float | None = None
