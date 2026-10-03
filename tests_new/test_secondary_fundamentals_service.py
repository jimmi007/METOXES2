import metoxes.services.secondary_fundamentals_service as service


def test_secondary_crosscheck_flags_large_difference(monkeypatch):
    monkeypatch.setattr(
        service,
        "_fetch_fmp",
        lambda symbol: {
            "secondary_source": "FMP",
            "secondary_status": "ok",
            "secondary_fcf_yield": 2,
            "secondary_roic": 5,
        },
    )

    result = service.fetch_secondary_fundamentals({
        "symbol": "TEST",
        "country": "United States",
        "fcf_yield": 10,
        "roic": 25,
    })

    assert result["secondary_source"] == "FMP"
    assert result["fundamental_crosscheck_status"] == "large_difference"
    assert result["fundamental_discrepancy_pct"] >= 50
