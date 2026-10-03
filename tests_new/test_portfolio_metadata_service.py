from metoxes.services.portfolio_metadata_service import (
    enrich_sector_country_from_saved_positions,
)


def test_freedom_missing_metadata_is_restored():
    current = [
        {
            "symbol": "BELA.GR",
            "platform": "Freedom24",
            "sector": None,
            "country": None,
        }
    ]

    saved = [
        {
            "symbol": "BELA.GR",
            "platform": "Freedom24",
            "sector": "Consumer Cyclical",
            "country": "Greece",
        }
    ]

    result = (
        enrich_sector_country_from_saved_positions(
            current,
            saved,
        )
    )

    assert (
        result[0]["sector"]
        == "Consumer Cyclical"
    )
    assert (
        result[0]["country"]
        == "Greece"
    )


def test_existing_broker_metadata_has_priority():
    current = [
        {
            "symbol": "TEST",
            "platform": "Capital",
            "sector": "Technology",
            "country": "United States",
        }
    ]

    saved = [
        {
            "symbol": "TEST",
            "platform": "Capital",
            "sector": "Industrials",
            "country": "Germany",
        }
    ]

    result = (
        enrich_sector_country_from_saved_positions(
            current,
            saved,
        )
    )

    assert (
        result[0]["sector"]
        == "Technology"
    )
    assert (
        result[0]["country"]
        == "United States"
    )


def test_same_symbol_different_platform_does_not_mix():
    current = [
        {
            "symbol": "ABC",
            "platform": "Freedom24",
            "sector": None,
            "country": None,
        }
    ]

    saved = [
        {
            "symbol": "ABC",
            "platform": "Trading212",
            "sector": "Technology",
            "country": "United States",
        }
    ]

    result = (
        enrich_sector_country_from_saved_positions(
            current,
            saved,
        )
    )

    assert result[0]["sector"] is None
    assert result[0]["country"] is None
