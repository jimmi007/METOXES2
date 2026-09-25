from collections import defaultdict


def percentile_score(value, values):

    # Κρατάμε μόνο πραγματικούς αριθμούς
    valid_values = [
        v for v in values
        if v is not None
    ]

    if value is None:
        return None

    if len(valid_values) <= 1:
        return 50.0

    # Πόσες τιμές είναι μικρότερες
    lower = sum(
        1 for v in valid_values
        if v < value
    )

    # Πόσες είναι ίσες
    equal = sum(
        1 for v in valid_values
        if v == value
    )

    # Percentile 0 - 100
    score = (
        lower + (equal - 1) / 2
    ) / (len(valid_values) - 1) * 100

    return round(score, 2)


def score_stocks_by_sector(stocks):

    # ------------------------------------------------------
    # ΟΜΑΔΟΠΟΙΗΣΗ ΑΝΑ SECTOR
    # ------------------------------------------------------

    sectors = defaultdict(list)

    for stock in stocks:

        sector = stock.get("sector") or "Unknown"

        sectors[sector].append(stock)

    results = []

    # ------------------------------------------------------
    # ΒΑΘΜΟΛΟΓΗΣΗ
    # ------------------------------------------------------

    for sector, sector_stocks in sectors.items():

        fcf_yields = [
            s.get("fcf_yield")
            for s in sector_stocks
        ]

        fcf_growths = [
            s.get("fcf_growth")
            for s in sector_stocks
        ]

        roics = [
            s.get("roic")
            for s in sector_stocks
        ]

        for stock in sector_stocks:

            fcf_yield_score = percentile_score(
                stock.get("fcf_yield"),
                fcf_yields
            )

            fcf_growth_score = percentile_score(
                stock.get("fcf_growth"),
                fcf_growths
            )

            roic_score = percentile_score(
                stock.get("roic"),
                roics
            )

            # ----------------------------------------------
            # ΤΕΛΙΚΟ SCORE
            # Ίσο βάρος στα διαθέσιμα κριτήρια
            # ----------------------------------------------

            available_scores = [
                score
                for score in [
                    fcf_yield_score,
                    fcf_growth_score,
                    roic_score
                ]
                if score is not None
            ]

            if available_scores:

                final_score = round(
                    sum(available_scores)
                    / len(available_scores),
                    2
                )

            else:
                final_score = None

            results.append({

                "symbol": stock.get("symbol"),
                "name": stock.get("name"),
                "sector": sector,
                "country": stock.get("country"),
                "platform": stock.get("platform"),

                "fcf_yield": stock.get(
                    "fcf_yield"
                ),

                "fcf_yield_score": (
                    fcf_yield_score
                ),

                "fcf_growth": stock.get(
                    "fcf_growth"
                ),

                "fcf_growth_score": (
                    fcf_growth_score
                ),

                "roic": stock.get(
                    "roic"
                ),

                "roic_score": roic_score,

                "final_score": final_score,
            })

    # Μεγαλύτερο score πρώτο.
    # Τα None πάνε στο τέλος.
    results.sort(
        key=lambda x: (
            x["final_score"] is not None,
            x["final_score"]
            if x["final_score"] is not None
            else -1
        ),
        reverse=True
    )

    return results