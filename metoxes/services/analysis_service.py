from collections import defaultdict


# ==========================================================
# ΑΝΑΛΥΣΗ PORTFOLIO
# ==========================================================

def analyze_portfolio(stocks):

    # ------------------------------------------------------
    # ΣΥΝΟΛΙΚΗ ΑΞΙΑ PORTFOLIO
    # ------------------------------------------------------

    total_value = sum(
        stock.get("market_value") or 0
        for stock in stocks
    )

    # ------------------------------------------------------
    # ΟΜΑΔΟΠΟΙΗΣΕΙΣ
    # ------------------------------------------------------

    platforms = defaultdict(float)
    sectors = defaultdict(float)
    countries = defaultdict(float)

    for stock in stocks:

        market_value = (
            stock.get("market_value") or 0
        )

        platform = (
            stock.get("platform") or "Unknown"
        )

        sector = (
            stock.get("sector") or "Unknown"
        )

        country = (
            stock.get("country") or "Unknown"
        )

        platforms[platform] += market_value
        sectors[sector] += market_value
        countries[country] += market_value

    # ------------------------------------------------------
    # ΔΗΜΙΟΥΡΓΙΑ SUMMARY
    # ------------------------------------------------------

    def create_summary(data):

        result = []

        for name, market_value in data.items():

            if total_value > 0:

                weight = (
                    market_value
                    / total_value
                    * 100
                )

            else:

                weight = 0

            result.append({
                "name": name,

                # Μέχρι 2 δεκαδικά
                "market_value": round(
                    market_value,
                    2
                ),

                # Μέχρι 2 δεκαδικά
                "weight": round(
                    weight,
                    2
                )
            })

        # Μεγαλύτερη αξία πρώτη
        result.sort(
            key=lambda x: x["market_value"],
            reverse=True
        )

        return result

    # ------------------------------------------------------
    # ΤΕΛΙΚΟ ΑΠΟΤΕΛΕΣΜΑ
    # ------------------------------------------------------

    return {

        "total_positions": len(stocks),

        "total_portfolio_value": round(
            total_value,
            2
        ),

        "by_platform": create_summary(
            platforms
        ),

        "by_sector": create_summary(
            sectors
        ),

        "by_country": create_summary(
            countries
        ),
    }