
from datetime import date

from metoxes.services.data_quality_service import (
    check_stock_quality,
    run_portfolio_quality_checks,
)


def stock(**changes):
    base = {
        "symbol": "TEST",
        "platform": "Trading212",
        "purchase_date": "01/01/2026",
        "purchase_price": 100.0,
        "quantity": 10.0,
        "current_price": 120.0,
        "market_value": 1200.0,
        "percent_change": 20.0,
        "monthly_percent_change": 5.0,
        "fcf_yield": 5.0,
        "fcf_growth": 10.0,
        "roic": 15.0,
        "final_score": 70.0,
    }
    base.update(changes)
    return base


def test_clean_stock_has_no_error_or_warning():
    issues = check_stock_quality(
        stock(),
        today=date(2026, 4, 1),
    )

    bad = [
        x for x in issues
        if x["severity"] in ("error", "warning")
    ]

    assert bad == []


def test_market_value_mismatch_is_detected():
    issues = check_stock_quality(
        stock(market_value=500),
        today=date(2026, 4, 1),
    )

    codes = {x["code"] for x in issues}

    assert "market_value_mismatch" in codes


def test_percent_change_mismatch_is_detected():
    issues = check_stock_quality(
        stock(percent_change=80),
        today=date(2026, 4, 1),
    )

    codes = {x["code"] for x in issues}

    assert "percent_change_mismatch" in codes


def test_missing_required_number_is_error():
    report = run_portfolio_quality_checks(
        [
            stock(
                current_price=None,
            )
        ],
        today=date(2026, 4, 1),
    )

    assert report["status"] == "ERROR"
    assert report["errors"] >= 1


def test_recent_return_anomaly_is_flagged():
    issues = check_stock_quality(
        stock(
            purchase_date="15/03/2026",
            percent_change=80,
            monthly_percent_change=2,
            current_price=180,
            market_value=1800,
        ),
        today=date(2026, 4, 1),
    )

    codes = {x["code"] for x in issues}

    assert "recent_return_anomaly" in codes
