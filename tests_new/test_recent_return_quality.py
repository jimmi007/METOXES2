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


def test_iesc_recent_return_anomaly_is_info_when_return_is_consistent():
    stock = {
        "symbol": "IESC",
        "platform": "Capital",
        "purchase_date": "2026-08-24",
        "purchase_price": 99.09,
        "quantity": 2,
        "current_price": 282.45,
        "market_value": 564.90,
        "percent_change": 185.05,
        "monthly_percent_change": 6.28,
        "fcf_yield": 1,
        "fcf_growth": 1,
        "roic": 1,
        "final_score": 50,
    }

    issues = check_stock_quality(
        stock,
        today=date(2026, 9, 28),
    )

    recent = _issue_by_code(
        issues,
        "recent_return_anomaly",
    )

    assert recent["severity"] == "info"


def test_recent_return_anomaly_stays_warning_if_total_return_is_wrong():
    stock = {
        "symbol": "BAD",
        "platform": "Test",
        "purchase_date": "2026-09-01",
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

    recent = _issue_by_code(
        issues,
        "recent_return_anomaly",
    )

    assert recent["severity"] == "warning"
