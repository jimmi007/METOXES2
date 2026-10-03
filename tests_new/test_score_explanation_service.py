from metoxes.services.score_explanation_service import build_score_explanation


def test_general_score_explanation_has_drivers_and_hides_internal_scores():
    row = {
        "final_score": 86.86,
        "fcf_yield": 10.43,
        "fcf_yield_score": 90,
        "roic": 39.85,
        "roic_score": 95,
        "fcf_growth": 25.14,
        "fcf_growth_score": 80,
        "forward_revenue_growth": 9.18,
        "forward_revenue_growth_score": 60,
        "forward_eps_growth": 13.04,
        "forward_eps_growth_score": 70,
        "secondary_source": "FMP",
        "secondary_fcf_yield": 11.58,
        "secondary_roic": 36.79,
        "fundamental_crosscheck_status": "consistent",
        "fundamental_discrepancy_pct": 9.91,
    }
    payload = build_score_explanation(row)
    assert "FCF Yield" in payload["score_rationale_text"]
    assert "FMP" in payload["score_crosscheck_text"]
    assert payload["score_model_label"] == "General Fundamentals"
    assert "relative_score" not in payload["score_rationale_text"]


def test_financial_score_explanation_uses_financial_metrics():
    row = {
        "final_score": 62.74,
        "financial_model": "bank",
        "financial_roe": 16.68,
        "financial_price_to_book": 1.60,
        "financial_profit_margin": 36.02,
        "financial_revenue_growth": 56.0,
        "financial_forward_eps_growth": 10.2,
    }
    payload = build_score_explanation(row)
    assert payload["score_model_label"] == "Financial Services"
    assert "ROE" in payload["score_rationale_text"]
    assert "Price/Book" in payload["score_rationale_text"]

from metoxes.services.score_explanation_service import reconcile_financial_crosschecks


def test_financial_crosscheck_uses_roe_instead_of_generic_fcf_roic():
    rows = [{
        "financial_model": "bank",
        "secondary_source": "FMP",
        "financial_roe": 11.20,
        "secondary_roe": 11.13,
        "financial_price_to_book": 1.36,
        "secondary_price_to_book": None,
        "fundamental_crosscheck_status": "large_difference",
        "fundamental_discrepancy_pct": 86.47,
    }]
    result = reconcile_financial_crosschecks(rows)[0]
    assert result["fundamental_crosscheck_status"] == "consistent"
    assert result["fundamental_discrepancy_pct"] < 1
    assert result["financial_crosscheck_metrics"] == "ROE/P-B"
