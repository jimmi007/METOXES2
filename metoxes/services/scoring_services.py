from collections import defaultdict


# ==========================================================
# SETTINGS
# ==========================================================

MIN_SECTOR_COMPANIES = 3


# ==========================================================
# BANKS
# ==========================================================

BANK_SYMBOLS = {
    "BAC",
    "OPHC",
    "ALPHA.GR",
    "ETE.GR",
    "EUROB.GR",
}


# ==========================================================
# BANK CHECK
# ==========================================================

def is_bank(stock):

    symbol = str(
        stock.get("symbol") or ""
    ).strip().upper()

    industry = str(
        stock.get("industry") or ""
    ).lower()

    return (
        symbol in BANK_SYMBOLS
        or "bank" in industry
    )


# ==========================================================
# UNIQUE METRIC VALUES
# ==========================================================

def get_unique_metric_values(
    stocks,
    metric
):

    unique = {}

    for stock in stocks:

        # Οι τράπεζες δεν συμμετέχουν
        # στο generic FCF / ROIC scoring
        if is_bank(stock):
            continue

        value = stock.get(metric)

        if value is None:
            continue

        # Ίδια εταιρεία σε διαφορετικό broker
        # μετράει μία φορά στο percentile.
        company_key = (
            stock.get("yahoo_symbol")
            or stock.get("symbol")
        )

        company_key = str(
            company_key
        ).strip().upper()

        if company_key not in unique:
            unique[company_key] = value

    return list(
        unique.values()
    )


# ==========================================================
# PERCENTILE SCORE
# ==========================================================

def percentile_score(
    value,
    values
):

    if value is None:
        return None

    valid_values = [
        v
        for v in values
        if v is not None
    ]

    # Δεν δίνουμε τεχνητό 0 / 50 / 100
    # σε sector με μόνο 1-2 εταιρείες.
    if (
        len(valid_values)
        < MIN_SECTOR_COMPANIES
    ):
        return None

    lower = sum(
        1
        for v in valid_values
        if v < value
    )

    equal = sum(
        1
        for v in valid_values
        if v == value
    )

    score = (
        lower
        + (equal - 1) / 2
    ) / (
        len(valid_values) - 1
    ) * 100

    return round(
        score,
        2
    )


# ==========================================================
# SCORE STOCKS BY SECTOR
# ==========================================================

def score_stocks_by_sector(stocks):

    sectors = defaultdict(list)

    # ------------------------------------------------------
    # GROUP BY SECTOR
    # ------------------------------------------------------

    for stock in stocks:

        sector = (
            stock.get("sector")
            or "Unknown"
        )

        sectors[sector].append(
            stock
        )

    results = []

    # ------------------------------------------------------
    # ΚΑΘΕ SECTOR
    # ------------------------------------------------------

    for sector, sector_stocks in sectors.items():

        fcf_yields = (
            get_unique_metric_values(
                sector_stocks,
                "fcf_yield"
            )
        )

        fcf_growths = (
            get_unique_metric_values(
                sector_stocks,
                "fcf_growth"
            )
        )

        roics = (
            get_unique_metric_values(
                sector_stocks,
                "roic"
            )
        )

        # --------------------------------------------------
        # ΚΑΘΕ ΜΕΤΟΧΗ
        # --------------------------------------------------

        for stock in sector_stocks:

            # ==============================================
            # BANK
            # ==============================================

            if is_bank(stock):

                results.append({
                    "symbol":
                        stock.get("symbol"),

                    "yahoo_symbol":
                        stock.get("yahoo_symbol"),

                    "name":
                        stock.get("name"),

                    "sector":
                        sector,

                    "industry":
                        stock.get("industry"),

                    "country":
                        stock.get("country"),

                    "platform":
                        stock.get("platform"),

                    "fcf_yield":
                        stock.get("fcf_yield"),

                    "fcf_yield_score":
                        None,

                    "fcf_growth":
                        stock.get("fcf_growth"),

                    "fcf_growth_score":
                        None,

                    "roic":
                        stock.get("roic"),

                    "roic_score":
                        None,

                    "final_score":
                        None,

                    "score_status":
                        "BANK",
                })

                continue

            # ==============================================
            # NORMAL COMPANY
            # ==============================================

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

            available_scores = [
                score
                for score in [
                    fcf_yield_score,
                    fcf_growth_score,
                    roic_score,
                ]
                if score is not None
            ]

            # ==============================================
            # FINAL SCORE
            # ==============================================

            if available_scores:

                final_score = round(
                    sum(available_scores)
                    / len(available_scores),
                    2
                )

                score_status = "OK"

            else:

                final_score = None
                score_status = "INSUFFICIENT_DATA"

            # ==============================================
            # RESULT
            # ==============================================

            results.append({
                "symbol":
                    stock.get("symbol"),

                "yahoo_symbol":
                    stock.get("yahoo_symbol"),

                "name":
                    stock.get("name"),

                "sector":
                    sector,

                "industry":
                    stock.get("industry"),

                "country":
                    stock.get("country"),

                "platform":
                    stock.get("platform"),

                "fcf_yield":
                    stock.get("fcf_yield"),

                "fcf_yield_score":
                    fcf_yield_score,

                "fcf_growth":
                    stock.get("fcf_growth"),

                "fcf_growth_score":
                    fcf_growth_score,

                "roic":
                    stock.get("roic"),

                "roic_score":
                    roic_score,

                "final_score":
                    final_score,

                "score_status":
                    score_status,
            })

    # ======================================================
    # SORT
    # ======================================================

    results.sort(
        key=lambda stock: (
            stock.get("final_score")
            is not None,

            stock.get("final_score")
            if stock.get("final_score")
            is not None
            else -1
        ),
        reverse=True
    )

    return results