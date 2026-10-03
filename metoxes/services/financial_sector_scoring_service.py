from __future__ import annotations

"""Dedicated scoring model for banks and other Financial Services companies.

FCF/ROIC are not used as the deciding metrics for these rows.  The model uses
ROE, price-to-book, profit margin, revenue growth and forward EPS growth.
Only the final score is intended for user-facing Excel/dashboard display.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import math


FINANCIAL_SECTOR = "Financial Services"
RELATIVE_WEIGHT = 0.60
ABSOLUTE_WEIGHT = 0.40
MIN_COVERAGE = 0.50

METRIC_WEIGHTS = {
    "financial_roe": 0.30,
    "financial_price_to_book": 0.20,
    "financial_profit_margin": 0.15,
    "financial_revenue_growth": 0.15,
    "financial_forward_eps_growth": 0.20,
}


def _safe_float(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _pct(value):
    number = _safe_float(value)
    if number is None:
        return None
    if -2 <= number <= 2:
        return number * 100
    return number


def _piecewise(value, points):
    number = _safe_float(value)
    if number is None:
        return None
    if number <= points[0][0]:
        return float(points[0][1])
    if number >= points[-1][0]:
        return float(points[-1][1])
    for (x1, s1), (x2, s2) in zip(points, points[1:]):
        if x1 <= number <= x2:
            ratio = (number - x1) / (x2 - x1)
            return round(s1 + ratio * (s2 - s1), 2)
    return None


def _score_roe(value):
    return _piecewise(value, [(0, 0), (5, 25), (10, 50), (15, 75), (20, 90), (25, 100)])


def _score_pb(value):
    number = _safe_float(value)
    if number is None or number <= 0:
        return None
    # Lower P/B receives a higher valuation score. Extremely low values are
    # capped rather than treated as infinitely attractive.
    return _piecewise(number, [(0.4, 100), (0.8, 90), (1.2, 78), (1.8, 62), (2.5, 45), (4, 25), (7, 5)])


def _score_margin(value):
    return _piecewise(value, [(-10, 0), (0, 20), (10, 45), (20, 70), (30, 88), (40, 100)])


def _score_growth(value):
    return _piecewise(value, [(-15, 0), (0, 25), (5, 50), (10, 70), (20, 90), (30, 100)])


def _score_eps_growth(value):
    return _piecewise(value, [(-20, 0), (0, 20), (5, 40), (10, 60), (20, 80), (30, 100)])


SCORERS = {
    "financial_roe": _score_roe,
    "financial_price_to_book": _score_pb,
    "financial_profit_margin": _score_margin,
    "financial_revenue_growth": _score_growth,
    "financial_forward_eps_growth": _score_eps_growth,
}


def _is_financial(row):
    return str(row.get("sector") or "").strip() == FINANCIAL_SECTOR


def _is_bank_industry(industry):
    text = str(industry or "").lower()
    return "bank" in text or "thrift" in text or "savings" in text


def _fetch_metrics(row):
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        return {}

    market_symbol = symbol
    if str(row.get("platform") or "").strip().lower() == "freedom24":
        try:
            from metoxes.services.freedom_service import FREEDOM_TICKER_MAP
            market_symbol = FREEDOM_TICKER_MAP.get(symbol, symbol)
        except Exception:
            market_symbol = symbol

    import yfinance as yf

    info = yf.Ticker(market_symbol).get_info() or {}
    industry = info.get("industry") or row.get("industry")

    return {
        "financial_industry": industry,
        "financial_model": "bank" if _is_bank_industry(industry) else "financial_services",
        "financial_roe": _pct(info.get("returnOnEquity")) or _safe_float(row.get("secondary_roe")),
        "financial_price_to_book": _safe_float(info.get("priceToBook")) or _safe_float(row.get("secondary_price_to_book")),
        "financial_profit_margin": _pct(info.get("profitMargins")),
        "financial_revenue_growth": _pct(info.get("revenueGrowth")),
        "financial_forward_eps_growth": _safe_float(row.get("forward_eps_growth")) or _pct(info.get("earningsGrowth")),
    }


def _rank_percentile(value, peers, higher_is_better=True):
    number = _safe_float(value)
    valid = sorted(_safe_float(x) for x in peers if _safe_float(x) is not None)
    if number is None or not valid:
        return None
    if len(valid) == 1:
        return 50.0
    if higher_is_better:
        lower = sum(1 for x in valid if x < number)
        equal = sum(1 for x in valid if x == number)
    else:
        # Reverse ranking for P/B.
        lower = sum(1 for x in valid if x > number)
        equal = sum(1 for x in valid if x == number)
    average_index = lower + (equal - 1) / 2
    return round(average_index / (len(valid) - 1) * 100, 2)


def _absolute_score(row):
    weighted = 0.0
    available = 0.0
    for field, weight in METRIC_WEIGHTS.items():
        score = SCORERS[field](row.get(field))
        row[f"{field}_absolute_score"] = score
        if score is None:
            continue
        weighted += score * weight
        available += weight
    if available <= 0:
        return None, 0.0
    return round(weighted / available, 2), available / sum(METRIC_WEIGHTS.values())


def apply_financial_sector_model(rows, workers=4, fetch_missing=True):
    result = [dict(row) for row in rows or []]
    financial_indexes = [i for i, row in enumerate(result) if _is_financial(row)]
    if not financial_indexes:
        return result

    if fetch_missing:
        with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
            future_map = {executor.submit(_fetch_metrics, result[i]): i for i in financial_indexes}
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    result[index].update(future.result())
                except Exception as error:
                    result[index]["financial_model_error"] = str(error)[:300]
                    result[index].setdefault("financial_model", "financial_services")

    # Use all Financial Services rows as the peer set.  Country-only financial
    # peer groups are often too small in a personal portfolio/candidate set.
    peers = [result[i] for i in financial_indexes]
    for field in METRIC_WEIGHTS:
        values = [row.get(field) for row in peers]
        higher = field != "financial_price_to_book"
        for row in peers:
            row[f"{field}_relative_score"] = _rank_percentile(row.get(field), values, higher_is_better=higher)

    for row in peers:
        relative_parts = [
            _safe_float(row.get(f"{field}_relative_score"))
            for field in METRIC_WEIGHTS
        ]
        relative_parts = [x for x in relative_parts if x is not None]
        relative = round(sum(relative_parts) / len(relative_parts), 2) if relative_parts else None
        absolute, coverage = _absolute_score(row)

        row["financial_relative_score"] = relative
        row["financial_absolute_score"] = absolute
        row["financial_model_coverage"] = round(coverage * 100, 2)
        row["financial_score_mode"] = "financial_60_40"

        if relative is None:
            row["final_score"] = absolute
            row["financial_score_mode"] = "financial_absolute_only"
        elif absolute is None or coverage < MIN_COVERAGE:
            row["final_score"] = relative
            row["financial_score_mode"] = "financial_relative_only"
        else:
            row["final_score"] = round(relative * RELATIVE_WEIGHT + absolute * ABSOLUTE_WEIGHT, 2)

        # Keep the generic hidden diagnostics coherent for existing gates.
        row["relative_score"] = relative
        row["absolute_score"] = absolute
        row["absolute_coverage"] = round(coverage * 100, 2)
        row["score_mode"] = row["financial_score_mode"]

    return result
