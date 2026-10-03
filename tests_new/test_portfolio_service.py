import pytest

from metoxes.services.portfolio_service import (
    aggregate_positions,
)


def test_rhm_uses_weighted_purchase_price_for_return():
    rows = [
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2025-05-23",
            "purchase_price": 1772.78,
            "quantity": 0.10,
            "current_price": 966.42,
        },
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2024-12-17",
            "purchase_price": 611.02,
            "quantity": 0.40,
            "current_price": 966.42,
        },
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2025-03-03",
            "purchase_price": 1185.19,
            "quantity": 0.30,
            "current_price": 966.42,
        },
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2025-03-12",
            "purchase_price": 1275.78,
            "quantity": 0.21,
            "current_price": 966.42,
        },
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2026-06-25",
            "purchase_price": 931.65,
            "quantity": 2.00,
            "current_price": 966.42,
        },
        {
            "symbol": "RHM.DE",
            "platform": "Capital",
            "purchase_date": "2026-05-04",
            "purchase_price": 1392.41,
            "quantity": 0.08,
            "current_price": 966.42,
        },
    ]

    rhm = aggregate_positions(rows)[0]

    assert rhm["quantity"] == pytest.approx(
        3.09
    )

    assert rhm["purchase_price"] == pytest.approx(
        977.30,
        abs=0.02,
    )

    expected_return = (
        966.42 / rhm["purchase_price"] - 1
    ) * 100

    assert rhm["percent_change"] == pytest.approx(
        expected_return,
        abs=0.02,
    )


def test_ldo_uses_weighted_purchase_price_for_return():
    rows = [
        {
            "symbol": "LDO.MI",
            "platform": "Capital",
            "purchase_date": "2024-12-06",
            "purchase_price": 26.62,
            "quantity": 15,
            "current_price": 49.11,
        },
        {
            "symbol": "LDO.MI",
            "platform": "Capital",
            "purchase_date": "2025-03-03",
            "purchase_price": 45.35,
            "quantity": 5,
            "current_price": 49.11,
        },
        {
            "symbol": "LDO.MI",
            "platform": "Capital",
            "purchase_date": "2025-03-05",
            "purchase_price": 45.19,
            "quantity": 5,
            "current_price": 49.11,
        },
        {
            "symbol": "LDO.MI",
            "platform": "Capital",
            "purchase_date": "2025-03-05",
            "purchase_price": 45.28,
            "quantity": 10,
            "current_price": 49.11,
        },
    ]

    ldo = aggregate_positions(rows)[0]

    assert ldo["quantity"] == pytest.approx(
        35
    )

    assert ldo["purchase_price"] == pytest.approx(
        37.28,
        abs=0.02,
    )

    assert ldo["percent_change"] == pytest.approx(
        31.73,
        abs=0.10,
    )
