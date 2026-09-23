from datetime import datetime, timedelta
from metoxes.services.price_service import get_vuaa_return
def aggregate_positions(stocks):

    grouped = {}

    # ==================================================
    # 1. ΟΜΑΔΟΠΟΙΗΣΗ
    # ίδια μετοχή + ίδιος broker
    # ==================================================

    for stock in stocks:

        key = (
            stock.get("symbol"),
            stock.get("platform")
        )

        if key not in grouped:
            grouped[key] = []

        grouped[key].append(stock)


    aggregated_stocks = []

    # ==================================================
    # 2. ΕΝΩΣΗ ΚΑΘΕ ΟΜΑΔΑΣ
    # ==================================================

    for (symbol, platform), positions in grouped.items():

        # Συνολική ποσότητα
        total_quantity = sum(
            position.get("quantity", 0) or 0
            for position in positions
        )
        # ==================================================
        # ΣΤΑΘΜΙΣΜΕΝΗ ΜΕΣΗ ΤΙΜΗ ΑΓΟΡΑΣ
        #
        # π.χ.
        # 5 μετοχές x 40 €
        # 15 μετοχές x 20 €
        # μέση τιμή = 25 €, όχι 30 €
        # ==================================================

        total_purchase_cost = sum(
            (position.get("purchase_price") or 0)
            * (position.get("quantity") or 0)
            for position in positions
        )

        if total_quantity > 0:
            weighted_purchase_price = (
                    total_purchase_cost
                    / total_quantity
            )
        else:
            weighted_purchase_price = None
        # ==================================================
        # ΣΥΝΟΛΙΚΗ ΠΟΣΟΣΤΙΑΙΑ ΑΠΟΔΟΣΗ
        # ==================================================


        # ==================================================
        # ΣΤΑΘΜΙΣΜΕΝΗ ΗΜΕΡΟΜΗΝΙΑ ΑΓΟΡΑΣ
        # ==================================================

        dated_positions = [
            position
            for position in positions
            if position.get("purchase_date")
               and (position.get("quantity") or 0) > 0
        ]

        if dated_positions:

            total_dated_quantity = sum(
                position.get("quantity") or 0
                for position in dated_positions
            )

            weighted_timestamp = sum(
                datetime.fromisoformat(
                    str(position["purchase_date"])[:10]
                ).timestamp()
                * (position.get("quantity") or 0)
                for position in dated_positions
            ) / total_dated_quantity

            weighted_purchase_date = datetime.fromtimestamp(
                weighted_timestamp
            ).date().isoformat()

        else:
            weighted_purchase_date = None

        # Συνολική τρέχουσα αξία
        total_market_value = sum(
            position.get("market_value", 0) or 0
            for position in positions
        )
        # ==================================================
        # ΣΤΑΘΜΙΣΜΕΝΟ PERCENT CHANGE
        # ==================================================

        valid_percent_positions = [
            position
            for position in positions
            if position.get("percent_change") is not None
               and position.get("market_value") is not None
        ]

        total_weight_value = sum(
            position["market_value"]
            for position in valid_percent_positions
        )

        if total_weight_value > 0:

            weighted_percent_change = sum(
                position["percent_change"]
                * position["market_value"]
                for position in valid_percent_positions
            ) / total_weight_value

        else:
            weighted_percent_change = None

        # Παίρνουμε τα κοινά στοιχεία
        first = positions[0]
        # ==================================================
        # VUAA RETURN / EXCESS RETURN
        # ==================================================

        if weighted_purchase_date:

            vuaa_return = get_vuaa_return(
                weighted_purchase_date
            )

        else:
            vuaa_return = None

        if (
                weighted_percent_change is not None
                and vuaa_return is not None
        ):
            excess_return = (
                    weighted_percent_change
                    - vuaa_return
            )
        else:
            excess_return = None
        aggregated_stock = {
            "symbol": symbol,
            "name": first.get("name"),
            "platform": platform,

            "quantity": round(
                total_quantity,
                8
            ),

            "current_price": first.get(
                "current_price"
            ),

            "market_value": round(
                total_market_value,
                2
            ),

            # Προς το παρόν τα αφήνουμε.
            # Θα τα υπολογίσουμε σωστά στο επόμενο βήμα.
            "purchase_date": weighted_purchase_date,
            "purchase_price": (
                round(weighted_purchase_price, 2)
                if weighted_purchase_price is not None
                else None
            ),
            "percent_change": (
                round(weighted_percent_change, 2)
                if weighted_percent_change is not None
                else None
            ),
            "monthly_percent_change": first.get(
                "monthly_percent_change"
            ),
            "vuaa_return": (
                round(vuaa_return, 2)
                if vuaa_return is not None
                else None
            ),

            "excess_return": (
                round(excess_return, 2)
                if excess_return is not None
                else None
            )
        }

        aggregated_stocks.append(
            aggregated_stock
        )

    return aggregated_stocks