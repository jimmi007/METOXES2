from metoxes.services.ai_commentary_service import (
    build_rule_commentary,
    enrich_ai_commentary,
)


def test_rule_commentary_explains_score_news_earnings_and_anomaly(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    row = {
        "symbol": "ABC",
        "name": "ABC Corp",
        "sector": "Technology",
        "final_score": 82.5,
        "fcf_yield": 7,
        "roic": 18,
        "fcf_growth": 12,
        "forward_revenue_growth": 10,
        "forward_eps_growth": 14,
        "secondary_source": "FMP",
        "fundamental_crosscheck_status": "consistent",
        "news_headlines": [{"title": "ABC raises guidance"}],
        "earnings_date": "2026-10-20",
        "anomaly_summary": "FCF growth requires review.",
    }

    text = build_rule_commentary(row)
    assert "82.50/100" in text
    assert "FMP" in text
    assert "ABC raises guidance" in text
    assert "2026-10-20" in text

    enriched = enrich_ai_commentary([row])
    assert enriched[0]["ai_commentary_source"] == "rules_fallback"
    assert enriched[0]["ai_commentary"]
