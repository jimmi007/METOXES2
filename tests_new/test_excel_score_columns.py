from metoxes.services.excel_service import (
    get_active_headers,
    stock_to_excel_row,
)


def test_portfolio_excel_exposes_only_final_score():
    stock = {
        "symbol": "TEST",
        "relative_score": 80,
        "absolute_score": 60,
        "absolute_coverage": 100,
        "score_mode": "relative_60_absolute_40",
        "final_score": 72,
    }

    headers = get_active_headers(
        stocks=[stock]
    )

    assert "final_score" in headers
    assert "relative_score" not in headers
    assert "absolute_score" not in headers
    assert "absolute_coverage" not in headers
    assert "score_mode" not in headers

    row = stock_to_excel_row(
        stock,
        headers
    )

    values = dict(
        zip(
            headers,
            row,
        )
    )

    assert values["final_score"] == 72
