import json

from openpyxl import Workbook

import metoxes.services.dashboard_service as dashboard_service


def test_dashboard_shows_two_final_score_tables_and_hides_internal_scores(tmp_path):
    html_path = tmp_path / "dashboard.html"
    json_path = tmp_path / "dashboard.json"
    excel_path = tmp_path / "portfolio.xlsx"

    workbook = Workbook()
    portfolio = workbook.active
    portfolio.title = "Portfolio"

    candidates = workbook.create_sheet(
        "Candidates"
    )
    candidates.append([
        "rank",
        "symbol",
        "name",
        "discount_from_52w_high_pct",
        "final_score",
        "dashboard_analysis",
    ])
    candidates.append([
        1,
        "CAND",
        "Candidate Company",
        31.5,
        88,
        "Περίπου ογδόντα λέξεις ανάλυσης για την υποψήφια εταιρεία.",
    ])
    workbook.save(excel_path)
    workbook.close()

    dashboard_service.PORTFOLIO_EXCEL_FILE = (
        excel_path
    )

    stocks = [
        {
            "symbol": "TEST",
            "name": "Test Company",
            "sector": "Technology",
            "country": "United States",
            "platform": "Trading212",
            "market_value": 1000,
            "purchase_price": 10,
            "quantity": 100,
            "relative_score": 80,
            "absolute_score": 60,
            "absolute_coverage": 100,
            "score_mode": "relative_60_absolute_40",
            "final_score": 72,
        }
    ]

    dashboard_service.generate_portfolio_dashboard(
        stocks=stocks,
        quality_report={
            "errors": 0,
            "warnings": 0,
        },
        json_path=json_path,
        html_path=html_path,
    )

    html = html_path.read_text(
        encoding="utf-8"
    )

    assert "Υφιστάμενες Μετοχές — Final Score & Αναλυτική Αιτιολόγηση" in html
    assert "Υποψήφιες Μετοχές — Score" in html
    assert "% κάτω από 52W High" in html
    assert "AI Ανάλυση Υποψήφιων Μετοχών" in html
    assert "Γιατί πήρε αυτό το Final Score" in html
    assert "candidateAnalysisList" in html
    assert "<th>Relative</th>" not in html
    assert "<th>Absolute</th>" not in html
    assert "Avg Relative" not in html
    assert "Avg Absolute" not in html
    assert "Relative vs Absolute Score" not in html

    payload = json.loads(
        json_path.read_text(
            encoding="utf-8"
        )
    )

    assert payload["stocks"][0]["final_score"] == 72
    assert "relative_score" not in payload["stocks"][0]
    assert "absolute_score" not in payload["stocks"][0]
    assert payload["candidates"][0]["symbol"] == "CAND"
    assert payload["candidates"][0]["discount_from_52w_high_pct"] == 31.5
    assert "ογδόντα λέξεις" in payload["candidates"][0]["dashboard_analysis"]
