from __future__ import annotations

import math

METRICS = (
    ("fcf_yield", "fcf_yield_score"),
    ("fcf_growth", "fcf_growth_score"),
    ("roic", "roic_score"),
)

MIN_COUNTRY_SECTOR_PEERS = 5


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


def _country(row):
    return str(
        row.get("country") or "Unknown"
    ).strip()


def _sector(row):
    return str(
        row.get("sector") or "Unknown"
    ).strip()


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


def _assign_rank_scores(
    rows,
    value_field,
    score_field,
):
    """
    Default peer group:
        same country + same sector.

    Stability fallback:
        if fewer than 5 valid peers exist for that metric,
        compare against all available companies in the same sector.
    """
    country_sector = {}
    sector_groups = {}

    for row in rows:
        cs_key = (
            _country(row),
            _sector(row),
        )
        sector_key = _sector(row)

        country_sector.setdefault(
            cs_key,
            [],
        ).append(row)

        sector_groups.setdefault(
            sector_key,
            [],
        ).append(row)

    for row in rows:
        row[score_field] = None

        value = _safe_float(
            row.get(value_field)
        )
        if value is None:
            continue

        cs_key = (
            _country(row),
            _sector(row),
        )
        sector_key = _sector(row)

        cs_values = [
            peer.get(value_field)
            for peer in country_sector.get(
                cs_key,
                [],
            )
            if _safe_float(
                peer.get(value_field)
            ) is not None
        ]

        if len(cs_values) >= MIN_COUNTRY_SECTOR_PEERS:
            peers = cs_values
            scope = "country_sector"
        else:
            peers = [
                peer.get(value_field)
                for peer in sector_groups.get(
                    sector_key,
                    [],
                )
                if _safe_float(
                    peer.get(value_field)
                ) is not None
            ]
            scope = "global_sector"

        row[score_field] = _rank_percentile(
            value,
            peers,
        )

        row[
            f"{score_field}_peer_scope"
        ] = scope

        row[
            f"{score_field}_peer_count"
        ] = len(peers)


def _calculate_final_score(row):
    available_scores = []

    for _, score_field in METRICS:
        score = _safe_float(
            row.get(score_field)
        )
        if score is not None:
            available_scores.append(
                score
            )

    if not available_scores:
        return None

    return round(
        sum(available_scores)
        / len(available_scores),
        2,
    )


def score_stocks_by_sector(stocks):
    """
    Compatibility name.

    Preferred peer group:
        same country + same sector.

    Fallback:
        if a metric has <5 valid country+sector peers,
        use the global same-sector universe.
    """
    if not stocks:
        return []

    result = [
        dict(stock)
        for stock in stocks
    ]

    for (
        value_field,
        score_field,
    ) in METRICS:
        _assign_rank_scores(
            result,
            value_field=value_field,
            score_field=score_field,
        )

    for row in result:
        country = _country(row)
        sector = _sector(row)

        scopes = [
            row.get(
                f"{score_field}_peer_scope"
            )
            for _, score_field
            in METRICS
            if row.get(
                f"{score_field}_peer_scope"
            )
        ]

        counts = [
            row.get(
                f"{score_field}_peer_count"
            )
            for _, score_field
            in METRICS
            if row.get(
                f"{score_field}_peer_count"
            ) is not None
        ]

        row["score_peer_country"] = country
        row["score_peer_sector"] = sector
        row["score_peer_scope"] = (
            "global_sector"
            if "global_sector" in scopes
            else "country_sector"
        )
        row["score_peer_count"] = (
            min(counts)
            if counts
            else 0
        )
        row["final_score"] = (
            _calculate_final_score(
                row
            )
        )

    return result


score_stocks_by_country_sector = (
    score_stocks_by_sector
)
