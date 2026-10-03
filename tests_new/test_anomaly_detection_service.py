from datetime import date

from metoxes.services.anomaly_detection_service import (
    detect_portfolio_anomalies,
    detect_row_anomalies,
)


def test_detects_return_sign_and_secondary_source_mismatch():
    result = detect_row_anomalies(
        {
            "percent_change": 25,
            "avg_monthly_change": -2,
            "fundamental_crosscheck_status": "large_difference",
            "fundamental_discrepancy_pct": 70,
            "final_score": 75,
            "purchase_date": "2026-01-01",
        },
        today=date(2026, 10, 3),
    )

    codes = {flag["code"] for flag in result["anomaly_flags"]}
    assert "return_sign_mismatch" in codes
    assert "fundamental_source_mismatch" in codes
    assert result["anomaly_count"] == 2
    assert result["anomaly_severity"] == "error"


def test_portfolio_anomaly_report_counts_positions():
    result = detect_portfolio_anomalies([
        {"symbol": "OK", "percent_change": 5, "avg_monthly_change": 1, "final_score": 60},
        {"symbol": "BAD", "percent_change": 5, "avg_monthly_change": -1, "final_score": 60},
    ])
    assert result["report"]["positions_with_anomalies"] == 1
    assert result["report"]["total_flags"] >= 1
