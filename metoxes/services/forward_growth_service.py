import math
from functools import lru_cache

import yfinance as yf

from metoxes.services.freedom_service import FREEDOM_TICKER_MAP


FINAL_SCORE_WEIGHTS = {
    "fcf_yield_score": 0.25,
    "fcf_growth_score": 0.25,
    "roic_score": 0.25,
    "forward_revenue_growth_score": 0.125,
    "forward_eps_growth_score": 0.125,
}


def _safe_float(value):
    if value is None:
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if math.isnan(number) or math.isinf(number):
        return None

    return number


def _growth_to_percent(value):
    number = _safe_float(value)

    if number is None:
        return None

    if -5 <= number <= 5:
        number *= 100

    return round(number, 2)


def _get_growth_from_estimate_table(table, period="+1y"):
    if table is None:
        return None

    try:
        if getattr(table, "empty", True):
            return None

        if period not in table.index:
            return None

        if "growth" not in table.columns:
            return None

        return _growth_to_percent(
            table.loc[period, "growth"]
        )

    except Exception:
        return None


def get_yahoo_symbol(symbol, platform=None):
    if not symbol:
        return None

    symbol = str(symbol).strip()

    if platform == "Freedom24":
        return FREEDOM_TICKER_MAP.get(
            symbol,
            symbol
        )

    return symbol


@lru_cache(maxsize=256)
def _get_forward_growth_cached(yahoo_symbol):
    result = {
        "forward_revenue_growth": None,
        "forward_eps_growth": None,
    }

    if not yahoo_symbol:
        return result

    try:
        ticker = yf.Ticker(yahoo_symbol)

        try:
            revenue_estimate = ticker.get_revenue_estimate()

            result["forward_revenue_growth"] = (
                _get_growth_from_estimate_table(
                    revenue_estimate,
                    "+1y"
                )
            )
        except Exception:
            pass

        try:
            earnings_estimate = ticker.get_earnings_estimate()

            result["forward_eps_growth"] = (
                _get_growth_from_estimate_table(
                    earnings_estimate,
                    "+1y"
                )
            )
        except Exception:
            pass

    except Exception:
        pass

    return result


def get_forward_growth(symbol, platform=None):
    yahoo_symbol = get_yahoo_symbol(
        symbol,
        platform
    )

    data = dict(
        _get_forward_growth_cached(
            yahoo_symbol
        )
    )

    data["yahoo_symbol"] = yahoo_symbol

    return data


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

def _recalculate_final_score(row):
    old_final_score = _safe_float(
        row.get("final_score")
    )

    available_base_scores = [
        _safe_float(row.get("fcf_yield_score")),
        _safe_float(row.get("fcf_growth_score")),
        _safe_float(row.get("roic_score")),
    ]

    available_base_scores = [
        score
        for score in available_base_scores
        if score is not None
    ]

    if old_final_score is None and available_base_scores:
        old_final_score = (
            sum(available_base_scores)
            / len(available_base_scores)
        )

    if old_final_score is None:
        return None

    weighted_total = 0.0

    for score_field, weight in FINAL_SCORE_WEIGHTS.items():
        score = _safe_float(
            row.get(score_field)
        )

        if score is None:
            score = old_final_score

        weighted_total += score * weight

    return round(weighted_total, 2)


def add_forward_growth_scores(scores):
    if not scores:
        return scores

    result = [
        dict(row)
        for row in scores
    ]

    for row in result:
        forward = get_forward_growth(
            symbol=row.get("symbol"),
            platform=row.get("platform"),
        )

        row["forward_revenue_growth"] = (
            forward.get("forward_revenue_growth")
        )

        row["forward_eps_growth"] = (
            forward.get("forward_eps_growth")
        )

    _assign_country_sector_rank_scores(
        result,
        value_field="forward_revenue_growth",
        score_field="forward_revenue_growth_score",
    )

    _assign_country_sector_rank_scores(
        result,
        value_field="forward_eps_growth",
        score_field="forward_eps_growth_score",
    )

    for row in result:
        row["final_score"] = (
            _recalculate_final_score(row)
        )

    return result
