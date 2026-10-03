
import json
from pathlib import Path

from metoxes.services.dashboard_service import generate_portfolio_dashboard


def test_dashboard_has_visible_arrow_and_candidate_detailed_accordion(tmp_path):
    stocks = [{
        "symbol": "ADBE",
        "name": "Adobe",
        "market_value": 1000,
        "purchase_price": 200,
        "quantity": 5,
        "final_score": 86.86,
        "score_rationale_headline": "Υψηλό score",
        "score_rationale_text": "Ισχυρό FCF Yield και ROIC.",
        "score_drivers": ["FCF Yield ισχυρό."],
        "score_weaknesses": [],
        "score_metric_details": [{"metric": "FCF Yield", "value": 10.43, "impact": "ισχυρό θετικό"}],
    }]
    candidates = [{
        "rank": 1,
        "symbol": "AAA",
        "name": "Alpha",
        "current_price": 70,
        "high_52w": 100,
        "discount_from_52w_high_pct": 30,
        "final_score": 81,
        "validation_status": "validated",
        "score_rationale_headline": "Ισχυρό score",
        "score_rationale_text": "Καλός συνδυασμός ποιότητας και ανάπτυξης.",
        "score_drivers": ["ROIC ισχυρό."],
        "score_weaknesses": ["Απόσταση από high μπορεί να δείχνει κίνδυνο."],
        "score_metric_details": [{"metric": "ROIC", "value": 25, "impact": "ισχυρό θετικό"}],
        "secondary_source": "FMP",
        "fundamental_crosscheck_status": "consistent",
        "score_crosscheck_text": "Η δεύτερη πηγή συμφωνεί.",
        "news_headlines": [{"title": "Recent update", "publisher": "Source"}],
        "earnings_date": "2026-11-01",
        "anomaly_count": 0,
        "ai_commentary": "Αναλυτικό AI commentary.",
        "ai_commentary_source": "rules_fallback",
    }]

    out = generate_portfolio_dashboard(
        stocks,
        quality_report={},
        candidates=candidates,
        json_path=tmp_path / "d.json",
        html_path=tmp_path / "d.html",
    )

    html = Path(out["html_file"]).read_text(encoding="utf-8")
    assert 'content:"▼"' in html
    assert 'id="candidateAccordion"' in html
    assert 'Συνολική αξιολόγηση υποψήφιας' in html
    assert 'Τιμή / 52W High / Validation' in html
    assert 'FMP / SEC ανεξάρτητος έλεγχος' in html
    assert 'AI Commentary / τελική επεξήγηση' in html


def test_portfolio_refresh_preserves_rich_candidate_enrichment(tmp_path):
    json_path = tmp_path / "d.json"
    html_path = tmp_path / "d.html"

    # First write an enriched candidate payload.
    generate_portfolio_dashboard(
        [{"symbol": "AAA", "market_value": 1, "purchase_price": 1, "quantity": 1}],
        quality_report={},
        candidates=[{
            "rank": 1,
            "symbol": "CAND",
            "name": "Candidate",
            "final_score": 80,
            "score_rationale_text": "Rich rationale",
            "ai_commentary": "Rich commentary",
        }],
        json_path=json_path,
        html_path=html_path,
    )

    # With no Excel file at this tmp location, the previous candidate payload
    # should still survive a normal dashboard refresh.
    generate_portfolio_dashboard(
        [{"symbol": "AAA", "market_value": 2, "purchase_price": 1, "quantity": 1}],
        quality_report={},
        candidates=None,
        json_path=json_path,
        html_path=html_path,
    )

    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["candidates"][0]["symbol"] == "CAND"
    assert payload["candidates"][0]["score_rationale_text"] == "Rich rationale"
    assert payload["candidates"][0]["ai_commentary"] == "Rich commentary"
