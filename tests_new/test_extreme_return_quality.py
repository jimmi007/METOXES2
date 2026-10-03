from datetime import date

from metoxes.services.data_quality_service import (
    check_stock_quality,
)


def _issue_by_code(issues, code):
    return next(
        issue
        for issue in issues
        if issue["code"] == code
    )


def test_consistent_extreme_positive_return_is_info():
    stock = {
        "symbol": "MOH.GR",
        "platform": "Freedom24",
        "purchase_date": "2025-01-01",
        "purchase_price": 20.44,
        "quantity": 15,
        "current_price": 66.65,
        "market_value": 999.75,
        "percent_change": 226.08,
        "monthly_percent_change": 5,
        "fcf_yield": 1,
        "fcf_growth": 1,
        "roic": 1,
        "final_score": 50,
    }

    issues = check_stock_quality(
        stock,
        today=date(2026, 9, 28),
    )

    extreme = _issue_by_code(
        issues,
        "extreme_return",
    )

    assert extreme["severity"] == "info"


def test_inconsistent_extreme_return_remains_warning():
    stock = {
        "symbol": "BAD",
        "platform": "Test",
        "purchase_date": "2025-01-01",
        "purchase_price": 100,
        "quantity": 1,
        "current_price": 120,
        "market_value": 120,
        "percent_change": 180,
        "monthly_percent_change": 5,
        "fcf_yield": 1,
        "fcf_growth": 1,
        "roic": 1,
        "final_score": 50,
    }

    issues = check_stock_quality(
        stock,
        today=date(2026, 9, 28),
    )

    extreme = _issue_by_code(
        issues,
        "extreme_return",
    )

    assert extreme["severity"] == "warning"
