from pathlib import Path
from metoxes.services.dashboard_service import generate_portfolio_dashboard


def test_dashboard_has_collapsible_stock_score_analysis(tmp_path):
    stocks = [{
        "symbol": "ADBE",
        "name": "Adobe",
        "market_value": 1000,
        "purchase_price": 200,
        "quantity": 5,
        "final_score": 86.86,
        "score_rationale_headline": "Υψηλό score",
        "score_rationale_text": "Ισχυρό FCF Yield και ROIC.",
        "score_drivers": ["FCF Yield 10.43%: ισχυρό θετικό."],
        "score_weaknesses": ["Forward revenue 9.18%: ουδέτερο."],
        "score_metric_details": [{"metric":"FCF Yield","value":10.43,"impact":"ισχυρό θετικό"}],
        "secondary_source": "FMP",
        "fundamental_crosscheck_status": "consistent",
        "score_crosscheck_text": "Δεύτερη πηγή: FMP.",
        "news_headlines": [],
        "earnings_date": "2026-12-09",
        "ai_commentary": "Αναλυτικό σχόλιο.",
        "ai_commentary_source": "rules_fallback",
    }]
    out = generate_portfolio_dashboard(
        stocks,
        quality_report={},
        candidates=[],
        json_path=tmp_path / "d.json",
        html_path=tmp_path / "d.html",
    )
    html = Path(out["html_file"]).read_text(encoding="utf-8")
    assert 'id="portfolioAccordion"' in html
    assert '<details class="stock-details">' in html
    assert 'Γιατί πήρε αυτό το Final Score' in html
    assert 'FMP / SEC ανεξάρτητος έλεγχος' in html
