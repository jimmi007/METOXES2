from metoxes.services.candidate_research_service import (
    ALLOWED_CANDIDATE_COUNTRIES,
    RESEARCH_REGIONS,
    build_candidate_dashboard_analysis,
    calculate_52w_levels,
    deduplicate_companies,
    is_allowed_candidate_country,
    meets_52w_discount_condition,
    select_top_candidates,
)


def test_25_percent_52w_level():
    result = calculate_52w_levels(
        70,
        100,
    )

    assert result["high_52w"] == 100
    assert result["price_25pct_below_high"] == 75
    assert result["drop_from_52w_high_amount"] == 30
    assert result["discount_from_52w_high_pct"] == 30
    assert meets_52w_discount_condition(70, 100)
    assert not meets_52w_discount_condition(80, 100)


def test_top_candidates_require_quality_gate_validation_and_discount():
    rows = [
        {
            "symbol": "A",
            "sector": "Technology",
            "final_score": 95,
            "absolute_coverage": 100,
            "score_mode": "relative_60_absolute_40",
            "discount_from_52w_high_pct": 20,
            "validation_status": "validated",
        },
        {
            "symbol": "B",
            "sector": "Technology",
            "final_score": 80,
            "absolute_coverage": 55,
            "score_mode": "relative_60_absolute_40",
            "discount_from_52w_high_pct": 30,
            "validation_status": "validated",
        },
        {
            "symbol": "C",
            "sector": "Technology",
            "final_score": 85,
            "absolute_coverage": 80,
            "score_mode": "relative_60_absolute_40",
            "discount_from_52w_high_pct": 26,
            "validation_status": "validated",
        },
        {
            "symbol": "D",
            "sector": "Technology",
            "final_score": 90,
            "absolute_coverage": 80,
            "score_mode": "relative_only",
            "discount_from_52w_high_pct": 30,
            "validation_status": "validated",
        },
        {
            "symbol": "E",
            "sector": "Technology",
            "final_score": 88,
            "absolute_coverage": 80,
            "score_mode": "relative_60_absolute_40",
            "discount_from_52w_high_pct": 30,
            "validation_status": "failed_discount",
        },
        {
            "symbol": "F",
            "sector": "Financial Services",
            "final_score": 99,
            "absolute_coverage": 100,
            "score_mode": "financial_60_40",
            "discount_from_52w_high_pct": 40,
            "validation_status": "validated",
        },
    ]

    result = select_top_candidates(
        rows,
        limit=20,
        min_discount_pct=25,
        min_absolute_coverage=60,
        require_validation=True,
    )

    assert [x["symbol"] for x in result] == ["F", "C"]
    assert result[0]["rank"] == 1


def test_dual_listing_is_deduplicated_and_domestic_listing_is_preferred():
    rows = [
        {
            "symbol": "AAUC",
            "name": "Allied Gold Corporation",
            "country": "Canada",
            "exchange_country": "United States",
            "preliminary_score": 90,
            "fcf_yield": 10,
            "roic": 15,
        },
        {
            "symbol": "AAUC.TO",
            "name": "Allied Gold Corporation",
            "country": "Canada",
            "exchange_country": "Canada",
            "preliminary_score": 80,
            "fcf_yield": 10,
            "roic": 15,
        },
    ]

    result = deduplicate_companies(rows)

    assert len(result) == 1
    assert result[0]["symbol"] == "AAUC.TO"


def test_candidate_geography_is_us_and_europe_only():
    assert "us" in RESEARCH_REGIONS
    assert "de" in RESEARCH_REGIONS
    assert "gr" in RESEARCH_REGIONS
    assert "ca" not in RESEARCH_REGIONS
    assert "au" not in RESEARCH_REGIONS
    assert "jp" not in RESEARCH_REGIONS
    assert "hk" not in RESEARCH_REGIONS

    assert is_allowed_candidate_country("United States")
    assert is_allowed_candidate_country("Greece")
    assert is_allowed_candidate_country("Germany")
    assert is_allowed_candidate_country("Sweden")
    assert not is_allowed_candidate_country("Canada")
    assert not is_allowed_candidate_country("China")
    assert not is_allowed_candidate_country("Japan")
    assert not is_allowed_candidate_country("South Africa")


def test_dashboard_analysis_is_roughly_80_words_and_uses_candidate_metrics():
    candidate = {
        "symbol": "TEST",
        "name": "Test Company",
        "final_score": 82.5,
        "discount_from_52w_high_pct": 34.2,
        "fcf_yield": 8.4,
        "fcf_growth": 22.0,
        "roic": 18.5,
        "forward_revenue_growth": 12.0,
        "forward_eps_growth": 15.0,
    }

    text = build_candidate_dashboard_analysis(candidate)
    words = text.split()

    assert 70 <= len(words) <= 100
    assert "82.50/100" in text
    assert "34.20%" in text
    assert "FCF Yield" in text
    assert "ROIC" in text


def test_validated_fallback_is_accepted_by_final_selection():
    rows = [
        {
            "symbol": "FALLBACK",
            "sector": "Technology",
            "final_score": 84,
            "absolute_coverage": 100,
            "score_mode": "relative_60_absolute_40",
            "discount_from_52w_high_pct": 30,
            "validation_status": "validated_fallback",
        }
    ]

    result = select_top_candidates(
        rows,
        limit=20,
        min_discount_pct=25,
        min_absolute_coverage=60,
        require_validation=True,
    )

    assert [x["symbol"] for x in result] == ["FALLBACK"]


def test_history_failure_falls_back_to_discovery_52w_values(monkeypatch):
    import sys
    import types

    from metoxes.services.candidate_research_service import (
        _validate_candidate_market_data,
    )

    class FakeTicker:
        def __init__(self, symbol):
            self.symbol = symbol

        def history(self, **kwargs):
            raise RuntimeError("simulated Yahoo history failure")

    fake_yf = types.SimpleNamespace(Ticker=FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    result = _validate_candidate_market_data(
        {
            "symbol": "TEST",
            "current_price": 70,
            "high_52w": 100,
        },
        25,
    )

    assert result["validation_status"] == "validated_fallback"
    assert result["discount_from_52w_high_pct"] == 30
    assert result["validation_points"] == 0
    assert "fallback" in result["validation_source"].lower()
