from __future__ import annotations


def _normalize(value):
    return str(
        value or ""
    ).strip().upper()


def _position_key(row):
    return (
        _normalize(
            row.get("symbol")
        ),
        _normalize(
            row.get("platform")
        ),
    )


def enrich_sector_country_from_saved_positions(
    stocks,
    saved_stocks,
):
    """
    Συμπληρώνει sector/country μόνο όταν λείπουν
    από τα τρέχοντα broker δεδομένα.

    Πηγή fallback:
        οι ήδη αποθηκευμένες γραμμές του portfolio.xlsx

    Κλειδί:
        (symbol, platform)

    Δεν αντικαθιστούμε ποτέ μη κενό sector/country
    που έρχεται ήδη από broker/service.
    """
    if not stocks:
        return []

    saved_lookup = {}

    for saved in saved_stocks or []:
        key = _position_key(
            saved
        )

        if not key[0]:
            continue

        saved_lookup[key] = {
            "sector": saved.get(
                "sector"
            ),
            "country": saved.get(
                "country"
            ),
        }

    result = []

    for stock in stocks:
        row = dict(stock)
        key = _position_key(row)

        saved = saved_lookup.get(
            key,
            {},
        )

        if not row.get("sector"):
            saved_sector = saved.get(
                "sector"
            )

            if saved_sector:
                row["sector"] = (
                    saved_sector
                )

        if not row.get("country"):
            saved_country = saved.get(
                "country"
            )

            if saved_country:
                row["country"] = (
                    saved_country
                )

        result.append(row)

    return result
