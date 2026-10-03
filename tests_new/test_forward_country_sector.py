from metoxes.services import (
    forward_growth_service as fgs,
)


def _by_symbol(rows, symbol):
    return next(
        row
        for row in rows
        if row["symbol"] == symbol
    )


def test_forward_growth_uses_global_sector_fallback_for_small_peer_groups(monkeypatch):
    fake_forward = {
        "GR1": {
            "forward_revenue_growth": 5,
            "forward_eps_growth": 5,
        },
        "GR2": {
            "forward_revenue_growth": 10,
            "forward_eps_growth": 10,
        },
        "US1": {
            "forward_revenue_growth": 20,
            "forward_eps_growth": 20,
        },
        "US2": {
            "forward_revenue_growth": 30,
            "forward_eps_growth": 30,
        },
        "DE1": {
            "forward_revenue_growth": 40,
            "forward_eps_growth": 40,
        },
    }

    def fake_get_forward_growth(
        symbol,
        platform=None,
    ):
        data = dict(
            fake_forward[symbol]
        )
        data["yahoo_symbol"] = symbol
        return data

    monkeypatch.setattr(
        fgs,
        "get_forward_growth",
        fake_get_forward_growth,
    )

    rows = []

    country_by_symbol = {
        "GR1": "Greece",
        "GR2": "Greece",
        "US1": "United States",
        "US2": "United States",
        "DE1": "Germany",
    }

    for symbol in fake_forward:
        rows.append({
            "symbol": symbol,
            "platform": "Test",
            "country": (
                country_by_symbol[
                    symbol
                ]
            ),
            "sector": "Industrials",
            "fcf_yield_score": 50,
            "fcf_growth_score": 50,
            "roic_score": 50,
            "final_score": 50,
        })

    result = (
        fgs.add_forward_growth_scores(
            rows
        )
    )

    assert _by_symbol(
        result,
        "GR1",
    )["forward_revenue_growth_score"] == 0

    assert _by_symbol(
        result,
        "GR2",
    )["forward_revenue_growth_score"] == 25

    assert _by_symbol(
        result,
        "DE1",
    )["forward_revenue_growth_score"] == 100
