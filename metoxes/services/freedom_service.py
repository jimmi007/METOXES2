import os

from dotenv import load_dotenv
from tradernet import Tradernet as tn


load_dotenv()

FREEDOM_PUBLIC_KEY = os.getenv("FREEDOM_PUBLIC_KEY")
FREEDOM_PRIVATE_KEY = os.getenv("FREEDOM_PRIVATE_KEY")


def get_freedom_connection():
    """
    Δημιουργεί σύνδεση με το Freedom24 / Tradernet API.
    """

    if not FREEDOM_PUBLIC_KEY or not FREEDOM_PRIVATE_KEY:
        raise ValueError(
            "Δεν βρέθηκαν τα Freedom24 API keys στο .env"
        )

    return tn(
        FREEDOM_PUBLIC_KEY,
        FREEDOM_PRIVATE_KEY
    )


def test_freedom_connection():
    """
    Απλός έλεγχος ότι τα API keys λειτουργούν.
    Δεν επιστρέφουμε πλέον προσωπικά στοιχεία.
    """

    try:
        connection = get_freedom_connection()

        # Έλεγχος ότι μπορούμε να κάνουμε authenticated request
        connection.authorized_request("getPositionJson")

        return {
            "status": "OK"
        }

    except Exception as e:
        return {
            "status": "ERROR",
            "message": str(e)
        }


def get_freedom_positions():
    """
    Επιστρέφει τις ανοικτές θέσεις του Freedom24.
    """

    connection = get_freedom_connection()

    response = connection.authorized_request(
        "getPositionJson"
    )

    try:
        positions = response["result"]["ps"]["pos"]
    except (KeyError, TypeError):
        return []

    return positions


def get_freedom_trades(
    begin_date="2020-01-01T00:00:00",
    end_date="2030-12-31T23:59:59",
    ticker=None
):
    """
    Επιστρέφει το ιστορικό συναλλαγών Freedom24.

    type = 1 -> αγορά
    type = 2 -> πώληση
    """

    connection = get_freedom_connection()

    params = {
        "beginDate": begin_date,
        "endDate": end_date,
        "max": 100,
        "sort": 1,
    }

    if ticker:
        params["nt_ticker"] = ticker

    response = connection.authorized_request(
        "getTradesHistory",
        params
    )

    try:
        trades = response["trades"]["trade"]
    except (KeyError, TypeError):
        return []

    # Σε ορισμένες αποκρίσεις μπορεί να έρθει
    # μία μόνο συναλλαγή ως dict αντί για list.
    if isinstance(trades, dict):
        trades = [trades]

    return trades


def get_clean_freedom_positions():
    """
    Μετατρέπει τις raw θέσεις Freedom24
    σε κοινή μορφή με Trading212 / Capital.
    """

    positions = get_freedom_positions()

    clean_positions = []

    for p in positions:

        symbol = p.get("i")
        name = p.get("name")

        quantity = float(p.get("q", 0))
        purchase_price = float(p.get("price_a", 0))
        current_price = float(p.get("profit_price", 0))

        currency = p.get("curr")

        market_value = float(p.get("market_value", 0))
        profit = float(p.get("profit_close", 0))

        total_cost = purchase_price * quantity

        if total_cost != 0:
            percent_change = (profit / total_cost) * 100
        else:
            percent_change = None

        clean_positions.append({
            "symbol": symbol,
            "name": name,
            "platform": "Freedom24",

            "purchase_price": round(purchase_price, 2),
            "quantity": quantity,
            "current_price": round(current_price, 2),

            "market_value": round(market_value, 2),

            "percent_change": (
                round(percent_change, 2)
                if percent_change is not None
                else None
            ),

            "profit": round(profit, 2),
            "currency": currency,

            "status": "OK"
        })

    return clean_positions