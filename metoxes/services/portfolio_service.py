from __future__ import annotations

from datetime import date, datetime


def _to_float(value):
    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_datetime(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, date):
        return datetime.combine(
            value,
            datetime.min.time(),
        )

    text = str(value).strip()

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).replace(tzinfo=None)
    except ValueError:
        pass

    for fmt in (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y/%m/%d",
    ):
        try:
            return datetime.strptime(
                text,
                fmt,
            )
        except ValueError:
            continue

    return None


def _weighted_average(
    rows,
    field,
    quantity_field="quantity",
):
    weighted_total = 0.0
    total_weight = 0.0

    for row in rows:
        value = _to_float(
            row.get(field)
        )
        quantity = _to_float(
            row.get(quantity_field)
        )

        if (
            value is None
            or quantity is None
            or quantity == 0
        ):
            continue

        weight = abs(quantity)

        weighted_total += (
            value * weight
        )
        total_weight += weight

    if total_weight == 0:
        return None

    return weighted_total / total_weight


def _sum_field(rows, field):
    values = [
        _to_float(row.get(field))
        for row in rows
    ]

    values = [
        value
        for value in values
        if value is not None
    ]

    if not values:
        return None

    return sum(values)


def _weighted_purchase_date(rows):
    weighted_timestamp = 0.0
    total_weight = 0.0

    for row in rows:
        dt = _to_datetime(
            row.get("purchase_date")
        )
        quantity = _to_float(
            row.get("quantity")
        )

        if (
            dt is None
            or quantity is None
            or quantity == 0
        ):
            continue

        weight = abs(quantity)

        weighted_timestamp += (
            dt.timestamp()
            * weight
        )
        total_weight += weight

    if total_weight == 0:
        return None

    dt = datetime.fromtimestamp(
        weighted_timestamp
        / total_weight
    )

    return dt.date().isoformat()


def _first_non_empty(rows, field):
    for row in rows:
        value = row.get(field)

        if value not in (None, ""):
            return value

    return None


def aggregate_positions(stocks):
    """
    Ενώνει θέσεις με ίδιο symbol + ίδιο platform.

    Το συνολικό percent_change υπολογίζεται από:

        aggregated current_price
        -------------------------  - 1
        weighted purchase_price

    και όχι ως μέσος όρος των percent_change των lots.
    """

    if not stocks:
        return []

    groups = {}
    order = []

    for stock in stocks:
        symbol = str(
            stock.get("symbol")
            or ""
        ).strip()

        platform = str(
            stock.get("platform")
            or ""
        ).strip()

        if not symbol:
            continue

        key = (
            symbol.upper(),
            platform.upper(),
        )

        if key not in groups:
            groups[key] = []
            order.append(key)

        groups[key].append(
            dict(stock)
        )

    result = []

    for key in order:
        rows = groups[key]
        aggregated = dict(
            rows[0]
        )

        total_quantity = sum(
            _to_float(
                row.get("quantity")
            ) or 0.0
            for row in rows
        )

        purchase_price = _weighted_average(
            rows,
            "purchase_price",
        )

        current_price = _weighted_average(
            rows,
            "current_price",
        )

        purchase_date = _weighted_purchase_date(
            rows
        )

        aggregated["quantity"] = round(
            total_quantity,
            10
        )

        aggregated["purchase_price"] = (
            round(
                purchase_price,
                2
            )
            if purchase_price is not None
            else None
        )

        aggregated["current_price"] = (
            round(
                current_price,
                2
            )
            if current_price is not None
            else None
        )

        if purchase_date is not None:
            aggregated[
                "purchase_date"
            ] = purchase_date

        # Market value από current_price × quantity.
        if (
            current_price is not None
            and total_quantity != 0
        ):
            market_value = (
                current_price
                * total_quantity
            )
        else:
            market_value = _sum_field(
                rows,
                "market_value",
            )

        aggregated["market_value"] = (
            round(
                market_value,
                2
            )
            if market_value is not None
            else None
        )

        # Σωστό aggregated total return.
        if (
            purchase_price is not None
            and current_price is not None
            and purchase_price != 0
        ):
            percent_change = (
                current_price
                / purchase_price
                - 1
            ) * 100
        else:
            percent_change = None

        aggregated["percent_change"] = (
            round(
                percent_change,
                2
            )
            if percent_change is not None
            else None
        )

        for field in (
            "monthly_percent_change",
            "vuaa_return",
            "avg_monthly_change",
            "fx_to_eur",
            "historical_fx_to_eur",
        ):
            value = _weighted_average(
                rows,
                field,
            )

            if value is not None:
                aggregated[field] = round(
                    value,
                    6
                    if "fx_to_eur" in field
                    else 2
                )

        vuaa_return = _to_float(
            aggregated.get(
                "vuaa_return"
            )
        )

        if (
            percent_change is not None
            and vuaa_return is not None
        ):
            aggregated[
                "excess_return"
            ] = round(
                percent_change
                - vuaa_return,
                2
            )

        for field in (
            "profit",
            "upl",
        ):
            value = _sum_field(
                rows,
                field,
            )

            if value is not None:
                aggregated[field] = round(
                    value,
                    2
                )

        for field in (
            "name",
            "sector",
            "country",
            "original_currency",
            "direction",
            "status",
        ):
            value = _first_non_empty(
                rows,
                field,
            )

            if value is not None:
                aggregated[field] = value

        result.append(
            aggregated
        )

    return result
