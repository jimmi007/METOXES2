from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import math


# ==========================================================
# GLOBAL RESEARCH CONFIGURATION
# ==========================================================

RESEARCH_REGIONS = (
    # Candidate research is intentionally restricted to
    # the United States and European markets.
    "us",
    "gb",
    "ie",
    "de",
    "fr",
    "nl",
    "es",
    "it",
    "ch",
    "se",
    "dk",
    "fi",
    "no",
    "be",
    "at",
    "pt",
    "gr",
)

ALLOWED_CANDIDATE_COUNTRIES = {
    "United States",
    "United Kingdom",
    "Ireland",
    "Germany",
    "France",
    "Netherlands",
    "Spain",
    "Italy",
    "Switzerland",
    "Sweden",
    "Denmark",
    "Finland",
    "Norway",
    "Belgium",
    "Austria",
    "Portugal",
    "Greece",
    "Luxembourg",
    "Poland",
    "Czech Republic",
    "Czechia",
    "Hungary",
    "Romania",
    "Bulgaria",
    "Croatia",
    "Slovenia",
    "Slovakia",
    "Estonia",
    "Latvia",
    "Lithuania",
    "Cyprus",
    "Malta",
    "Iceland",
}


RESEARCH_SECTORS = (
    "Basic Materials",
    "Communication Services",
    "Consumer Cyclical",
    "Consumer Defensive",
    "Energy",
    "Financial Services",
    "Healthcare",
    "Industrials",
    "Real Estate",
    "Technology",
    "Utilities",
)

DEFAULT_LIMIT = 20
DEFAULT_MIN_DISCOUNT_FROM_52W_HIGH = 25.0
DEFAULT_MIN_MARKET_CAP = 500_000_000
DEFAULT_MIN_AVG_VOLUME = 50_000
DEFAULT_MIN_PRICE = 1.0
DEFAULT_DISCOVERY_SIZE = 250
DEFAULT_DETAIL_PER_SECTOR = 20
DEFAULT_WORKERS = 8
DEFAULT_VALIDATION_WORKERS = 2
DEFAULT_MIN_ABSOLUTE_COVERAGE = 60.0
DEFAULT_VALIDATION_POOL_MULTIPLIER = 6
EXCLUDED_CANDIDATE_SECTORS = ()

EXCHANGE_COUNTRY = {
    "NYQ": "United States",
    "NMS": "United States",
    "NGM": "United States",
    "NCM": "United States",
    "ASE": "United States",
    "PCX": "United States",
    "TOR": "Canada",
    "VAN": "Canada",
    "LSE": "United Kingdom",
    "GER": "Germany",
    "FRA": "Germany",
    "MUN": "Germany",
    "STU": "Germany",
    "PAR": "France",
    "ENX": "France",
    "AMS": "Netherlands",
    "MAD": "Spain",
    "MCE": "Spain",
    "MIL": "Italy",
    "EBS": "Switzerland",
    "STO": "Sweden",
    "CPH": "Denmark",
    "HEL": "Finland",
    "OSL": "Norway",
    "BRU": "Belgium",
    "VIE": "Austria",
    "LIS": "Portugal",
    "ATH": "Greece",
    "ASX": "Australia",
    "NZE": "New Zealand",
    "JPX": "Japan",
    "TAI": "Taiwan",
    "TWO": "Taiwan",
    "SES": "Singapore",
    "HKG": "Hong Kong",
    "TLV": "Israel",
}


def _safe_float(value):
    if value in (None, ""):
        return None

    if isinstance(value, dict):
        value = value.get("raw")

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def is_allowed_candidate_country(country):
    """Return True only for United States / European company domiciles."""
    normalized = str(country or "").strip()
    return normalized in ALLOWED_CANDIDATE_COUNTRIES


def _fmt_metric(value, suffix="%"):
    number = _safe_float(value)
    if number is None:
        return "μη διαθέσιμο"
    return f"{number:.2f}{suffix}"


def build_candidate_dashboard_analysis(candidate):
    """
    Creates a compact ~80-word Greek screening note for the dashboard.

    The text is descriptive, based only on the candidate metrics already
    collected by the research pipeline; it is not a buy/sell recommendation.
    """
    name = str(
        candidate.get("name")
        or candidate.get("symbol")
        or "Η εταιρεία"
    ).strip()

    score = _safe_float(candidate.get("final_score"))
    discount = _safe_float(
        candidate.get("discount_from_52w_high_pct")
    )

    score_text = (
        f"{score:.2f}/100"
        if score is not None
        else "μη διαθέσιμο"
    )
    discount_text = (
        f"{discount:.2f}%"
        if discount is not None
        else "μη διαθέσιμη απόσταση"
    )

    text = (
        f"Η {name} ξεχωρίζει στο screening με συνολικό score {score_text} "
        f"και διαπραγματεύεται {discount_text} κάτω από το υψηλό 52 εβδομάδων. "
        f"Το FCF Yield είναι {_fmt_metric(candidate.get('fcf_yield'))}, το ROIC "
        f"{_fmt_metric(candidate.get('roic'))} και η μεταβολή FCF "
        f"{_fmt_metric(candidate.get('fcf_growth'))}. Οι εκτιμήσεις δείχνουν "
        f"Forward Revenue Growth {_fmt_metric(candidate.get('forward_revenue_growth'))} "
        f"και Forward EPS Growth {_fmt_metric(candidate.get('forward_eps_growth'))}. "
        "Η απόσταση από το υψηλό δημιουργεί πιθανό περιθώριο επανατιμολόγησης, "
        "αλλά μπορεί επίσης να αντανακλά ουσιαστικό επιχειρηματικό ή αποτιμητικό κίνδυνο. "
        "Πριν από απόφαση χρειάζεται έλεγχος κερδών, χρέους, αποτίμησης και πρόσφατων εταιρικών εξελίξεων."
    )

    return text


def calculate_52w_levels(current_price, high_52w):
    """
    Ο χρήστης ζήτησε ως hard condition η μετοχή να είναι
    τουλάχιστον 25% κάτω από το υψηλό 52 εβδομάδων.

    Επιστρέφουμε και το επίπεδο τιμής που αντιστοιχεί ακριβώς
    σε -25% από το 52-week high:

        25% below high = high_52w * 0.75
    """
    current = _safe_float(current_price)
    high = _safe_float(high_52w)

    if current is None or high is None or high <= 0:
        return {
            "current_price": current,
            "high_52w": high,
            "price_25pct_below_high": None,
            "drop_from_52w_high_amount": None,
            "discount_from_52w_high_pct": None,
        }

    threshold = high * 0.75
    drop_amount = high - current
    discount_pct = (
        (high - current)
        / high
        * 100
    )

    return {
        "current_price": round(current, 4),
        "high_52w": round(high, 4),
        "price_25pct_below_high": round(threshold, 4),
        "drop_from_52w_high_amount": round(drop_amount, 4),
        "discount_from_52w_high_pct": round(discount_pct, 2),
    }


def meets_52w_discount_condition(
    current_price,
    high_52w,
    min_discount_pct=DEFAULT_MIN_DISCOUNT_FROM_52W_HIGH,
):
    levels = calculate_52w_levels(
        current_price,
        high_52w,
    )

    discount = levels[
        "discount_from_52w_high_pct"
    ]

    if discount is None:
        return False

    return discount >= float(
        min_discount_pct
    )


def _rank_score(rank, count):
    if count <= 1:
        return 100.0

    return max(
        0.0,
        100.0
        - (rank - 1)
        / (count - 1)
        * 100.0,
    )


def _source_url(symbol):
    return (
        "https://finance.yahoo.com/quote/"
        + str(symbol).strip()
    )


def _discovery_query(yf, sector):
    EquityQuery = yf.EquityQuery

    return EquityQuery(
        "and",
        [
            EquityQuery(
                "is-in",
                [
                    "region",
                    *RESEARCH_REGIONS,
                ],
            ),
            EquityQuery(
                "eq",
                ["sector", sector],
            ),
            EquityQuery(
                "gte",
                [
                    "intradaymarketcap",
                    DEFAULT_MIN_MARKET_CAP,
                ],
            ),
            EquityQuery(
                "gte",
                [
                    "intradayprice",
                    DEFAULT_MIN_PRICE,
                ],
            ),
            EquityQuery(
                "gte",
                [
                    "avgdailyvol3m",
                    DEFAULT_MIN_AVG_VOLUME,
                ],
            ),
            EquityQuery(
                "gt",
                [
                    "lastclose52weekhigh.lasttwelvemonths",
                    0,
                ],
            ),
        ],
    )


def _merge_discovery_quote(
    bucket,
    quote,
    sector,
    rank,
    count,
    pass_name,
    min_discount_pct,
):
    symbol = str(
        quote.get("symbol") or ""
    ).strip()

    if not symbol:
        return False

    current_price = (
        quote.get("regularMarketPrice")
        or quote.get("regularMarketPreviousClose")
    )
    high_52w = quote.get(
        "fiftyTwoWeekHigh"
    )

    levels = calculate_52w_levels(
        current_price,
        high_52w,
    )

    discount = levels[
        "discount_from_52w_high_pct"
    ]

    if (
        discount is None
        or discount < min_discount_pct
    ):
        return False

    key = symbol.upper()

    row = bucket.setdefault(
        key,
        {
            "symbol": symbol,
            "name": (
                quote.get("longName")
                or quote.get("shortName")
                or symbol
            ),
            "sector": sector,
            "country": None,
            "exchange": quote.get("exchange"),
            "currency": quote.get("currency"),
            "market_cap": _safe_float(
                quote.get("marketCap")
            ),
            "source_url": _source_url(
                symbol
            ),
            **levels,
            "fcf_discovery_score": 0.0,
            "market_cap_discovery_score": 0.0,
        },
    )

    # Refresh price/high from the newest pass if present.
    for field, value in levels.items():
        if value is not None:
            row[field] = value

    row["market_cap"] = (
        _safe_float(
            quote.get("marketCap")
        )
        or row.get("market_cap")
    )

    score = _rank_score(
        rank,
        count,
    )

    if pass_name == "fcf_growth":
        row["fcf_discovery_score"] = max(
            row.get("fcf_discovery_score") or 0,
            score,
        )
    elif pass_name == "market_cap":
        row[
            "market_cap_discovery_score"
        ] = max(
            row.get(
                "market_cap_discovery_score"
            ) or 0,
            score,
        )

    row["preliminary_score"] = round(
        0.70
        * (row.get("fcf_discovery_score") or 0)
        + 0.30
        * (
            row.get(
                "market_cap_discovery_score"
            )
            or 0
        ),
        2,
    )

    return True


def discover_market_candidates(
    min_discount_pct=DEFAULT_MIN_DISCOUNT_FROM_52W_HIGH,
    detail_per_sector=DEFAULT_DETAIL_PER_SECTOR,
):
    """
    Broad internet market discovery through Yahoo Finance / yfinance.

    For every sector we make two passes:
      1) high FCF-growth screen
      2) large-market-cap screen

    Then we keep only stocks at least `min_discount_pct`
    below their 52-week high.
    """
    try:
        import yfinance as yf
    except ImportError as error:
        raise RuntimeError(
            "Δεν είναι εγκατεστημένο το yfinance."
        ) from error

    if (
        not hasattr(yf, "screen")
        or not hasattr(yf, "EquityQuery")
    ):
        raise RuntimeError(
            "Η έκδοση yfinance δεν υποστηρίζει "
            "screen / EquityQuery. Κάνε update το yfinance."
        )

    discovered = {}
    errors = []
    quotes_seen = 0

    passes = (
        (
            "fcf_growth",
            "leveredfreecashflow1yrgrowth.lasttwelvemonths",
            False,
        ),
        (
            "market_cap",
            "lastclosemarketcap.lasttwelvemonths",
            False,
        ),
    )

    for sector in RESEARCH_SECTORS:
        if sector in EXCLUDED_CANDIDATE_SECTORS:
            continue

        query = _discovery_query(
            yf,
            sector,
        )

        sector_bucket = {}

        for (
            pass_name,
            sort_field,
            sort_asc,
        ) in passes:
            try:
                response = yf.screen(
                    query,
                    size=DEFAULT_DISCOVERY_SIZE,
                    sortField=sort_field,
                    sortAsc=sort_asc,
                )
            except Exception as error:
                errors.append(
                    {
                        "sector": sector,
                        "pass": pass_name,
                        "error": str(error),
                    }
                )
                continue

            quotes = response.get(
                "quotes",
                [],
            ) or []

            quotes_seen += len(quotes)
            count = len(quotes)

            for rank, quote in enumerate(
                quotes,
                start=1,
            ):
                _merge_discovery_quote(
                    sector_bucket,
                    quote,
                    sector,
                    rank,
                    count,
                    pass_name,
                    min_discount_pct,
                )

        sector_rows = sorted(
            sector_bucket.values(),
            key=lambda row: (
                row.get(
                    "preliminary_score"
                ) or 0,
                row.get("market_cap") or 0,
            ),
            reverse=True,
        )

        for row in sector_rows[
            :detail_per_sector
        ]:
            discovered[
                row["symbol"].upper()
            ] = row

    rows = list(
        discovered.values()
    )

    rows.sort(
        key=lambda row: (
            row.get("preliminary_score") or 0,
            row.get("market_cap") or 0,
        ),
        reverse=True,
    )

    return {
        "rows": rows,
        "quotes_seen": quotes_seen,
        "qualified_for_detail": len(rows),
        "errors": errors,
    }


def _country_from_exchange(exchange):
    if not exchange:
        return None

    return EXCHANGE_COUNTRY.get(
        str(exchange).strip().upper()
    )


def _normalize_existing_symbols(symbols):
    result = set()

    for symbol in symbols or []:
        text = str(
            symbol or ""
        ).strip().upper()

        if not text:
            continue

        result.add(text)
        result.add(
            text.split(".")[0]
        )

    return result


def _build_detailed_candidate(
    discovered,
    existing_symbols,
):
    symbol = discovered["symbol"]

    # Delayed imports keep the pure helper functions testable
    # without network/data dependencies.
    import yfinance as yf

    from metoxes.services.fundamentals_service import (
        get_stock_fundamentals,
    )
    from metoxes.services.forward_growth_service import (
        get_forward_growth,
    )

    info = {}

    try:
        info = (
            yf.Ticker(symbol).get_info()
            or {}
        )
    except Exception:
        info = {}

    try:
        fundamentals = (
            get_stock_fundamentals(
                symbol
            )
            or {}
        )
    except Exception:
        fundamentals = {}

    try:
        forward = (
            get_forward_growth(
                symbol,
                platform=None,
            )
            or {}
        )
    except Exception:
        forward = {}

    country = (
        info.get("country")
        or discovered.get("country")
        or _country_from_exchange(
            discovered.get("exchange")
        )
        or "Unknown"
    )

    sector = (
        info.get("sector")
        or discovered.get("sector")
        or "Unknown"
    )

    name = (
        info.get("longName")
        or info.get("shortName")
        or discovered.get("name")
        or symbol
    )

    existing_key = symbol.upper()
    existing_base = (
        existing_key.split(".")[0]
    )

    return {
        **discovered,
        "name": name,
        "sector": sector,
        "country": country,
        "exchange_country": _country_from_exchange(
            discovered.get("exchange")
        ),
        "company_website": info.get("website"),
        "company_uuid": info.get("uuid"),
        "platform": "Research",
        "already_in_portfolio": (
            existing_key in existing_symbols
            or existing_base
            in existing_symbols
        ),
        "fcf_yield": fundamentals.get(
            "fcf_yield"
        ),
        "fcf_growth": fundamentals.get(
            "fcf_growth"
        ),
        "roic": fundamentals.get(
            "roic"
        ),
        "forward_revenue_growth": (
            forward.get(
                "forward_revenue_growth"
            )
        ),
        "forward_eps_growth": (
            forward.get(
                "forward_eps_growth"
            )
        ),
        "researched_at": datetime.now().isoformat(
            timespec="seconds"
        ),
    }


def _group_key(row):
    return (
        str(
            row.get("country")
            or "Unknown"
        ).strip(),
        str(
            row.get("sector")
            or "Unknown"
        ).strip(),
    )


def _rank_percentile(value, peers):
    number = _safe_float(value)

    valid = sorted(
        _safe_float(peer)
        for peer in peers
        if _safe_float(peer) is not None
    )

    if number is None or not valid:
        return None

    if len(valid) == 1:
        return 50.0

    lower = sum(
        1 for peer in valid
        if peer < number
    )
    equal = sum(
        1 for peer in valid
        if peer == number
    )

    average_index = (
        lower
        + (equal - 1) / 2
    )

    return round(
        average_index
        / (len(valid) - 1)
        * 100,
        2,
    )


def _assign_country_sector_rank_scores(
    rows,
    value_field,
    score_field,
):
    min_peers = 5
    country_sector = {}
    sector_groups = {}

    for row in rows:
        country = str(
            row.get("country")
            or "Unknown"
        ).strip()
        sector = str(
            row.get("sector")
            or "Unknown"
        ).strip()

        country_sector.setdefault(
            (country, sector),
            [],
        ).append(row)

        sector_groups.setdefault(
            sector,
            [],
        ).append(row)

    for row in rows:
        row[score_field] = None

        value = _safe_float(
            row.get(value_field)
        )
        if value is None:
            continue

        country = str(
            row.get("country")
            or "Unknown"
        ).strip()
        sector = str(
            row.get("sector")
            or "Unknown"
        ).strip()

        cs_values = [
            peer.get(value_field)
            for peer in country_sector.get(
                (country, sector),
                [],
            )
            if _safe_float(
                peer.get(value_field)
            ) is not None
        ]

        if len(cs_values) >= min_peers:
            peers = cs_values
            scope = "country_sector"
        else:
            peers = [
                peer.get(value_field)
                for peer in sector_groups.get(
                    sector,
                    [],
                )
                if _safe_float(
                    peer.get(value_field)
                ) is not None
            ]
            scope = "global_sector"

        row[score_field] = (
            _rank_percentile(
                value,
                peers,
            )
        )

        row[
            f"{score_field}_peer_scope"
        ] = scope

        row[
            f"{score_field}_peer_count"
        ] = len(peers)

def _apply_forward_scores(rows):
    from metoxes.services.forward_growth_service import (
        FINAL_SCORE_WEIGHTS,
    )

    _assign_country_sector_rank_scores(
        rows,
        "forward_revenue_growth",
        "forward_revenue_growth_score",
    )
    _assign_country_sector_rank_scores(
        rows,
        "forward_eps_growth",
        "forward_eps_growth_score",
    )

    for row in rows:
        old_final_score = _safe_float(
            row.get("final_score")
        )

        available_base_scores = [
            _safe_float(
                row.get(
                    "fcf_yield_score"
                )
            ),
            _safe_float(
                row.get(
                    "fcf_growth_score"
                )
            ),
            _safe_float(
                row.get(
                    "roic_score"
                )
            ),
        ]

        available_base_scores = [
            score
            for score
            in available_base_scores
            if score is not None
        ]

        if (
            old_final_score is None
            and available_base_scores
        ):
            old_final_score = (
                sum(
                    available_base_scores
                )
                / len(
                    available_base_scores
                )
            )

        if old_final_score is None:
            row["final_score"] = None
            continue

        total = 0.0

        for score_field, weight in (
            FINAL_SCORE_WEIGHTS.items()
        ):
            score = _safe_float(
                row.get(score_field)
            )

            if score is None:
                score = old_final_score

            total += score * weight

        row["final_score"] = round(
            total,
            2,
        )

    return rows


_COMPANY_SUFFIXES = (
    "inc",
    "incorporated",
    "corp",
    "corporation",
    "limited",
    "ltd",
    "plc",
    "ag",
    "sa",
    "se",
    "nv",
    "ab",
    "asa",
    "oyj",
    "spa",
    "co",
    "company",
    "holdings",
    "holding",
    "group",
    "publ",
)


def _normalized_company_name(name):
    import re

    text = str(
        name or ""
    ).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    parts = [
        part
        for part in text.split()
        if part
    ]

    while (
        parts
        and parts[-1]
        in _COMPANY_SUFFIXES
    ):
        parts.pop()

    return " ".join(parts)


def _company_key(row):
    # Cross-listings often have different quote UUIDs.
    # The normalized legal/company name is therefore
    # the primary deduplication key.
    normalized_name = (
        _normalized_company_name(
            row.get("name")
        )
    )

    if normalized_name:
        return (
            "name:",
            normalized_name,
        )

    uuid = str(
        row.get("company_uuid")
        or ""
    ).strip().lower()

    if uuid:
        return (
            "uuid:",
            uuid,
        )

    return (
        "symbol:",
        str(
            row.get("symbol")
            or ""
        ).upper(),
    )


def _data_completeness(row):
    fields = (
        "fcf_yield",
        "fcf_growth",
        "roic",
        "forward_revenue_growth",
        "forward_eps_growth",
    )

    return sum(
        1
        for field in fields
        if _safe_float(
            row.get(field)
        ) is not None
    )


def _listing_preference(row):
    domestic = (
        str(
            row.get("exchange_country")
            or ""
        ).strip().lower()
        == str(
            row.get("country")
            or ""
        ).strip().lower()
    )

    return (
        1 if domestic else 0,
        _data_completeness(row),
        _safe_float(
            row.get("preliminary_score")
        ) or 0,
    )


def deduplicate_companies(rows):
    best = {}

    for row in rows or []:
        key = _company_key(row)
        current = best.get(key)

        if (
            current is None
            or _listing_preference(row)
            > _listing_preference(current)
        ):
            best[key] = dict(row)

    return list(
        best.values()
    )


def _apply_discovery_market_data_fallback(
    result,
    min_discount_pct,
    reason=None,
):
    """
    Fallback όταν το Yahoo 1Y history αποτύχει.

    Δεν πετάμε αυτόματα μια κατά τα άλλα έγκυρη υποψήφια.
    Χρησιμοποιούμε τα current_price / high_52w που έχουν ήδη
    ληφθεί στο discovery/detail στάδιο και ξαναελέγχουμε τον
    κανόνα του >=25% κάτω από το 52-week high.
    """
    current_price = _safe_float(
        result.get("current_price")
    )
    high_52w = _safe_float(
        result.get("high_52w")
    )

    if (
        current_price is None
        or high_52w is None
        or high_52w <= 0
    ):
        result["validation_status"] = (
            "failed_history_final"
        )
        result["validation_source"] = (
            "Yahoo Finance history failed; "
            "discovery fallback unavailable"
        )
        if reason:
            result["validation_error"] = str(reason)
        return result

    result.update(
        calculate_52w_levels(
            current_price,
            high_52w,
        )
    )
    result["validation_points"] = 0
    result["validation_source"] = (
        "Yahoo Finance discovery/detail 52W fields "
        "(history fallback)"
    )
    if reason:
        result["validation_error"] = str(reason)

    if meets_52w_discount_condition(
        current_price,
        high_52w,
        min_discount_pct=min_discount_pct,
    ):
        result["validation_status"] = (
            "validated_fallback"
        )
    else:
        result["validation_status"] = (
            "failed_discount"
        )

    return result


def _validate_candidate_market_data(
    row,
    min_discount_pct,
):
    import yfinance as yf

    result = dict(row)
    symbol = result.get("symbol")

    result["validation_status"] = "failed"
    result["validation_source"] = (
        "Yahoo Finance 1Y daily history"
    )

    if not symbol:
        result["validation_status"] = (
            "failed_no_symbol"
        )
        return result

    try:
        history = yf.Ticker(symbol).history(
            period="1y",
            interval="1d",
            auto_adjust=False,
        )
    except Exception as error:
        return _apply_discovery_market_data_fallback(
            result,
            min_discount_pct,
            reason=error,
        )

    if (
        history is None
        or getattr(history, "empty", True)
        or "High" not in history
        or "Close" not in history
    ):
        return _apply_discovery_market_data_fallback(
            result,
            min_discount_pct,
            reason="No usable 1Y history returned",
        )

    high_series = history["High"].dropna()
    close_series = history["Close"].dropna()

    if high_series.empty or close_series.empty:
        return _apply_discovery_market_data_fallback(
            result,
            min_discount_pct,
            reason="1Y history contains no usable High/Close values",
        )

    validated_high = _safe_float(
        high_series.max()
    )
    validated_current = _safe_float(
        close_series.iloc[-1]
    )

    if (
        validated_high is None
        or validated_current is None
        or validated_high <= 0
    ):
        return _apply_discovery_market_data_fallback(
            result,
            min_discount_pct,
            reason="Invalid values in 1Y history",
        )

    result.update(
        calculate_52w_levels(
            validated_current,
            validated_high,
        )
    )
    result["validation_points"] = int(len(history))

    if meets_52w_discount_condition(
        validated_current,
        validated_high,
        min_discount_pct=min_discount_pct,
    ):
        result["validation_status"] = "validated"
    else:
        result["validation_status"] = "failed_discount"

    return result


def validate_candidate_pool(
    rows,
    min_discount_pct,
    workers=DEFAULT_WORKERS,
):
    validated = []

    with ThreadPoolExecutor(
        max_workers=max(
            1,
            int(workers),
        )
    ) as executor:
        future_map = {
            executor.submit(
                _validate_candidate_market_data,
                row,
                min_discount_pct,
            ): row
            for row in rows or []
        }

        for future in as_completed(
            future_map
        ):
            original = (
                future_map[future]
            )
            try:
                validated.append(
                    future.result()
                )
            except Exception as error:
                failed = dict(
                    original
                )
                failed[
                    "validation_status"
                ] = "failed_exception"
                failed[
                    "validation_error"
                ] = str(error)
                validated.append(
                    failed
                )

    return validated


def _passes_candidate_quality_gate(
    row,
    min_absolute_coverage,
):
    if (
        row.get("sector")
        in EXCLUDED_CANDIDATE_SECTORS
    ):
        return False

    valid_modes = {
        "relative_60_absolute_40",
        "financial_60_40",
    }

    if row.get("score_mode") not in valid_modes:
        return False

    coverage = _safe_float(
        row.get(
            "absolute_coverage"
        )
    )

    if (
        coverage is None
        or coverage
        < float(
            min_absolute_coverage
        )
    ):
        return False

    return True


def select_top_candidates(
    rows,
    limit=DEFAULT_LIMIT,
    min_discount_pct=DEFAULT_MIN_DISCOUNT_FROM_52W_HIGH,
    min_absolute_coverage=DEFAULT_MIN_ABSOLUTE_COVERAGE,
    require_validation=True,
):
    eligible = []

    for row in rows or []:
        final_score = _safe_float(
            row.get("final_score")
        )
        discount = _safe_float(
            row.get(
                "discount_from_52w_high_pct"
            )
        )

        if final_score is None:
            continue

        if (
            discount is None
            or discount
            < min_discount_pct
        ):
            continue

        if not _passes_candidate_quality_gate(
            row,
            min_absolute_coverage,
        ):
            continue

        if require_validation:
            validation_status = str(
                row.get("validation_status")
                or ""
            )
            if not validation_status.startswith(
                "validated"
            ):
                continue

        eligible.append(
            dict(row)
        )

    eligible.sort(
        key=lambda row: (
            _safe_float(
                row.get("final_score")
            )
            or -math.inf,
            _safe_float(
                row.get(
                    "discount_from_52w_high_pct"
                )
            )
            or -math.inf,
            _data_completeness(row),
        ),
        reverse=True,
    )

    selected = eligible[
        : int(limit)
    ]

    for rank, row in enumerate(
        selected,
        start=1,
    ):
        row["rank"] = rank
        row[
            "meets_25pct_discount"
        ] = True

    return selected

def research_top_candidates(
    limit=DEFAULT_LIMIT,
    min_discount_pct=DEFAULT_MIN_DISCOUNT_FROM_52W_HIGH,
    existing_symbols=None,
    detail_per_sector=DEFAULT_DETAIL_PER_SECTOR,
    workers=DEFAULT_WORKERS,
    min_absolute_coverage=DEFAULT_MIN_ABSOLUTE_COVERAGE,
):
    from metoxes.services.scoring_services import (
        score_stocks_by_sector,
    )
    from metoxes.services.absolute_quality_service import (
        add_absolute_quality_scores,
    )

    discovery = discover_market_candidates(
        min_discount_pct=min_discount_pct,
        detail_per_sector=detail_per_sector,
    )

    discovered_rows = discovery[
        "rows"
    ]

    normalized_existing = (
        _normalize_existing_symbols(
            existing_symbols
        )
    )

    detailed = []
    detail_errors = []

    with ThreadPoolExecutor(
        max_workers=max(
            1,
            int(workers),
        )
    ) as executor:
        future_map = {
            executor.submit(
                _build_detailed_candidate,
                row,
                normalized_existing,
            ): row
            for row in discovered_rows
        }

        for future in as_completed(
            future_map
        ):
            row = future_map[future]

            try:
                detailed.append(
                    future.result()
                )
            except Exception as error:
                detail_errors.append(
                    {
                        "symbol": row.get(
                            "symbol"
                        ),
                        "error": str(error),
                    }
                )

    geography_filtered = [
        row
        for row in detailed
        if is_allowed_candidate_country(
            row.get("country")
        )
    ]

    deduplicated = (
        deduplicate_companies(
            geography_filtered
        )
    )

    scored = score_stocks_by_sector(
        deduplicated
    )

    scored = _apply_forward_scores(
        scored
    )

    scored = add_absolute_quality_scores(
        scored
    )

    # Financial Services / banks use a dedicated ROE/P-B/growth model
    # instead of the generic FCF/ROIC framework.
    from metoxes.services.financial_sector_scoring_service import (
        apply_financial_sector_model,
    )

    scored = apply_financial_sector_model(
        scored,
        workers=min(4, max(1, int(workers))),
    )

    validation_pool_size = max(
        int(limit)
        * DEFAULT_VALIDATION_POOL_MULTIPLIER,
        60,
    )

    prevalidated = select_top_candidates(
        scored,
        limit=validation_pool_size,
        min_discount_pct=min_discount_pct,
        min_absolute_coverage=min_absolute_coverage,
        require_validation=False,
    )

    # History validation is intentionally conservative.
    # Using many parallel Yahoo requests can trigger rate limiting;
    # two workers are enough and the discovery/detail 52W values are
    # used as a fallback if history is temporarily unavailable.
    validated = validate_candidate_pool(
        prevalidated,
        min_discount_pct=min_discount_pct,
        workers=min(
            DEFAULT_VALIDATION_WORKERS,
            max(1, int(workers)),
        ),
    )

    top = select_top_candidates(
        validated,
        limit=limit,
        min_discount_pct=min_discount_pct,
        min_absolute_coverage=min_absolute_coverage,
        require_validation=True,
    )

    # The final 20 receive independent fundamentals validation,
    # anomaly detection, recent news/earnings context and AI commentary.
    from metoxes.services.secondary_fundamentals_service import (
        enrich_with_secondary_fundamentals,
    )
    from metoxes.services.anomaly_detection_service import (
        detect_portfolio_anomalies,
    )
    from metoxes.services.market_context_service import (
        enrich_market_context,
    )
    from metoxes.services.ai_commentary_service import (
        enrich_ai_commentary,
    )
    from metoxes.services.peer_intelligence_service import (
        enrich_peer_intelligence,
    )
    from metoxes.services.event_impact_service import (
        enrich_event_impact,
    )
    from metoxes.services.scenario_analysis_service import (
        enrich_standard_scenarios,
    )
    from metoxes.services.model_backtest_service import (
        record_model_snapshots,
    )
    from metoxes.services.score_explanation_service import (
        enrich_score_explanations,
        reconcile_financial_crosschecks,
    )

    top = enrich_with_secondary_fundamentals(
        top,
        workers=min(5, max(1, int(workers))),
    )
    top = reconcile_financial_crosschecks(
        top
    )
    anomaly_result = detect_portfolio_anomalies(
        top
    )
    top = anomaly_result["stocks"]
    top = enrich_score_explanations(
        top
    )
    top = enrich_market_context(
        top,
        workers=min(5, max(1, int(workers))),
        max_news=3,
    )

    # V20: real competitor intelligence (FMP peer list when available),
    # explicit news/earnings impact, and transparent what-if stress tests.
    top = enrich_peer_intelligence(
        top,
        workers=min(4, max(1, int(workers))),
        max_network_rows=len(top),
        max_peers=5,
    )
    top = enrich_event_impact(
        top
    )
    top = enrich_standard_scenarios(
        top
    )
    top = enrich_ai_commentary(
        top
    )

    # Point-in-time snapshots are the basis for a future no-look-ahead
    # backtest. Re-running on the same day replaces that day's snapshot.
    try:
        snapshot_result = record_model_snapshots(
            top,
            source="candidates",
        )
    except Exception as error:
        snapshot_result = {
            "status": "error",
            "error": str(error)[:300],
        }

    for row in top:
        row["dashboard_analysis"] = (
            row.get("ai_commentary")
            or build_candidate_dashboard_analysis(row)
        )

    validation_counts = {}

    for row in validated:
        status = str(
            row.get(
                "validation_status"
            )
            or "unknown"
        )
        validation_counts[
            status
        ] = (
            validation_counts.get(
                status,
                0,
            )
            + 1
        )

    return {
        "stocks": top,
        "meta": {
            "source": (
                "Yahoo Finance via yfinance"
            ),
            "fundamentals_crosscheck": (
                "FMP when FMP_API_KEY is configured; SEC EDGAR fallback for US issuers"
            ),
            "financial_services_model": (
                "ROE + price-to-book + profit margin + revenue growth + forward EPS growth"
            ),
            "ai_commentary": (
                "OpenAI Responses API when OPENAI_API_KEY is configured; rules fallback otherwise"
            ),
            "peer_intelligence": (
                "FMP stock peers + Yahoo comparable metrics; industry/sector fallback"
            ),
            "news_earnings_impact": (
                "separate -100..+100 event-impact layer; does not overwrite Final Score"
            ),
            "scenario_analysis": (
                "EPS -15pp, growth slowdown and bear-case shadow scores"
            ),
            "model_history": snapshot_result,
            "secondary_validation": (
                "Yahoo Finance 1Y daily history with "
                "discovery/detail 52W fallback"
            ),
            "regions": list(
                RESEARCH_REGIONS
            ),
            "geographic_scope": (
                "United States and Europe only"
            ),
            "company_country_filter": True,
            "sectors": [
                sector
                for sector
                in RESEARCH_SECTORS
                if sector
                not in EXCLUDED_CANDIDATE_SECTORS
            ],
            "excluded_sectors": list(
                EXCLUDED_CANDIDATE_SECTORS
            ),
            "quotes_seen": discovery.get(
                "quotes_seen",
                0,
            ),
            "qualified_for_detail": (
                discovery.get(
                    "qualified_for_detail",
                    0,
                )
            ),
            "detailed_analyzed": len(
                detailed
            ),
            "geography_qualified": len(
                geography_filtered
            ),
            "geography_rejected": (
                len(detailed)
                - len(geography_filtered)
            ),
            "unique_companies": len(
                deduplicated
            ),
            "duplicate_listings_removed": (
                len(geography_filtered)
                - len(deduplicated)
            ),
            "scored": sum(
                1
                for row in scored
                if row.get(
                    "final_score"
                ) is not None
            ),
            "validation_pool": len(
                prevalidated
            ),
            "validation_counts": (
                validation_counts
            ),
            "returned": len(top),
            "min_discount_from_52w_high_pct": float(
                min_discount_pct
            ),
            "min_absolute_coverage_pct": float(
                min_absolute_coverage
            ),
            "peer_fallback_rule": (
                "same country + same sector; "
                "if fewer than 5 valid peers, "
                "use global same-sector peers"
            ),
            "discovery_errors": discovery.get(
                "errors",
                [],
            ),
            "detail_errors": detail_errors,
        },
    }

