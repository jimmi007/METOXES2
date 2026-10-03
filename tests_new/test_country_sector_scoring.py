import pytest

from metoxes.services.scoring_services import (
    score_stocks_by_sector,
)


def _by_symbol(rows, symbol):
    return next(
        row
        for row in rows
        if row["symbol"] == symbol
    )


def test_small_country_sector_group_falls_back_to_global_sector():
    rows = [
        {
            "symbol": "GR_LOW",
            "country": "Greece",
            "sector": "Industrials",
            "fcf_yield": 5,
            "fcf_growth": 5,
            "roic": 5,
        },
        {
            "symbol": "GR_HIGH",
            "country": "Greece",
            "sector": "Industrials",
            "fcf_yield": 10,
            "fcf_growth": 10,
            "roic": 10,
        },
        {
            "symbol": "US1",
            "country": "United States",
            "sector": "Industrials",
            "fcf_yield": 20,
            "fcf_growth": 20,
            "roic": 20,
        },
        {
            "symbol": "US2",
            "country": "United States",
            "sector": "Industrials",
            "fcf_yield": 30,
            "fcf_growth": 30,
            "roic": 30,
        },
        {
            "symbol": "DE1",
            "country": "Germany",
            "sector": "Industrials",
            "fcf_yield": 40,
            "fcf_growth": 40,
            "roic": 40,
        },
        {
            "symbol": "FR1",
            "country": "France",
            "sector": "Industrials",
            "fcf_yield": 50,
            "fcf_growth": 50,
            "roic": 50,
        },
    ]

    scored = score_stocks_by_sector(
        rows
    )

    low = _by_symbol(
        scored,
        "GR_LOW",
    )
    high = _by_symbol(
        scored,
        "GR_HIGH",
    )

    assert (
        low["score_peer_scope"]
        == "global_sector"
    )
    assert (
        high["score_peer_scope"]
        == "global_sector"
    )
    assert low["fcf_yield_score"] == 0
    assert high["fcf_yield_score"] == 20


def test_five_or_more_country_sector_peers_stay_local():
    rows = []

    for index, value in enumerate(
        [1, 2, 3, 4, 5],
        start=1,
    ):
        rows.append({
            "symbol": f"GR{index}",
            "country": "Greece",
            "sector": "Utilities",
            "fcf_yield": value,
            "fcf_growth": value,
            "roic": value,
        })

    rows.append({
        "symbol": "US_BIG",
        "country": "United States",
        "sector": "Utilities",
        "fcf_yield": 100,
        "fcf_growth": 100,
        "roic": 100,
    })

    scored = score_stocks_by_sector(
        rows
    )

    gr5 = _by_symbol(
        scored,
        "GR5",
    )

    assert (
        gr5["score_peer_scope"]
        == "country_sector"
    )
    assert gr5["fcf_yield_score"] == 100


def test_missing_metric_uses_available_scores_only():
    rows = [
        {
            "symbol": "A",
            "country": "Greece",
            "sector": "Utilities",
            "fcf_yield": 1,
            "fcf_growth": None,
            "roic": 1,
        },
        {
            "symbol": "B",
            "country": "United States",
            "sector": "Utilities",
            "fcf_yield": 2,
            "fcf_growth": None,
            "roic": 2,
        },
    ]

    scored = score_stocks_by_sector(
        rows
    )

    a = _by_symbol(scored, "A")
    b = _by_symbol(scored, "B")

    assert a["fcf_growth_score"] is None
    assert b["fcf_growth_score"] is None
    assert a["final_score"] == pytest.approx(0)
    assert b["final_score"] == pytest.approx(100)
