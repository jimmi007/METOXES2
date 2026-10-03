from datetime import date

from metoxes.services.data_quality_service import (
    check_stock_quality,
)


def _codes(issues):
    return {
        issue["code"]
        for issue in issues
    }


def test_price_doubling_alone_is_not_split_warning():
    stock = {
        "symbol": "RWE.DE",
        "platform": "Capital",
        "purchase_date": "2025-01-06",
        "purchase_price": 30.41,
        "quantity": 14,
        "current_price": 59.22,
        "market_value": 829.08,
        "percent_change": 94.74,
        "monthly_percent_change": 3.0,
        "fcf_yield": 1,
        "fcf_growth": 1,
        "roic": 1,
        "final_score": 50,
    }

    issues = check_stock_quality(
        stock,
        today=date(2026, 9, 28),
    )

    assert "possible_stock_split" not in _codes(
        issues
    )


def test_split_like_ratio_with_return_mismatch_warns():
    stock = {
        "symbol": "TEST",
        "platform": "Test",
        "purchase_date": "2025-01-01",
        "purchase_price": 100,
        "quantity": 1,
        "current_price": 200,
        "market_value": 200,
        "percent_change": 50,
        "monthly_percent_change": 0,
        "fcf_yield": 1,
        "fcf_growth": 1,
        "roic": 1,
        "final_score": 50,
    }

    issues = check_stock_quality(
        stock,
        today=date(2026, 9, 28),
    )

    assert "possible_stock_split" in _codes(
        issues
    )
