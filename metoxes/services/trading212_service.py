import os

import httpx
from dotenv import load_dotenv


load_dotenv()

API_KEY = os.getenv("TRADING212_API_KEY")
API_SECRET = os.getenv("TRADING212_API_SECRET")

BASE_URL = "https://live.trading212.com/api/v0"


async def get_positions():

    if not API_KEY or not API_SECRET:
        raise ValueError("Λείπει το Trading212 API Key ή API Secret από το .env")

    url = f"{BASE_URL}/equity/positions"

    async with httpx.AsyncClient() as client:
        response = await client.get(
            url,
            auth=(API_KEY, API_SECRET),
            timeout=30
        )

        response.raise_for_status()

        return response.json()