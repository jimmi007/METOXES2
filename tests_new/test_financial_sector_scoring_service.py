from metoxes.services.financial_sector_scoring_service import (
    apply_financial_sector_model,
)


def test_financial_services_use_dedicated_model_and_total_score_only():
    rows = [
        {
            "symbol": "BANKA",
            "sector": "Financial Services",
            "financial_model": "bank",
            "financial_roe": 18,
            "financial_price_to_book": 1.1,
            "financial_profit_margin": 28,
            "financial_revenue_growth": 9,
            "financial_forward_eps_growth": 12,
            "final_score": 10,
        },
        {
            "symbol": "BANKB",
            "sector": "Financial Services",
            "financial_model": "bank",
            "financial_roe": 10,
            "financial_price_to_book": 1.8,
            "financial_profit_margin": 18,
            "financial_revenue_growth": 4,
            "financial_forward_eps_growth": 5,
            "final_score": 10,
        },
        {
            "symbol": "BANKC",
            "sector": "Financial Services",
            "financial_model": "bank",
            "financial_roe": 6,
            "financial_price_to_book": 3.0,
            "financial_profit_margin": 8,
            "financial_revenue_growth": 0,
            "financial_forward_eps_growth": 0,
            "final_score": 10,
        },
    ]

    result = apply_financial_sector_model(rows, fetch_missing=False)

    assert result[0]["score_mode"] == "financial_60_40"
    assert result[0]["financial_model_coverage"] == 100
    assert result[0]["final_score"] > result[1]["final_score"] > result[2]["final_score"]
    assert 0 <= result[0]["final_score"] <= 100
