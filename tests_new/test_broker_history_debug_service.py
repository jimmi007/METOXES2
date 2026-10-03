from metoxes.services.broker_history_debug_service import (
    summarize_trading212_history_debug,
    summarize_capital_transactions_debug,
)


def test_trading212_debug_parses_nested_order_fill_payload():
    payload = {
        "items": [
            {
                "order": {
                    "id": 1,
                    "ticker": "AAA_US_EQ",
                    "side": "BUY",
                    "status": "FILLED",
                    "filledQuantity": 2,
                },
                "fill": {
                    "price": 10.25,
                    "quantity": 2,
                },
            },
            {
                "order": {
                    "id": 2,
                    "ticker": "AAA_US_EQ",
                    "side": "SELL",
                    "status": "FILLED",
                    "filledQuantity": 1,
                },
                "fill": {
                    "price": 12.50,
                    "quantity": 1,
                },
            },
        ],
        "nextPagePath": "/api/v0/equity/history/orders?limit=50&cursor=1",
    }

    result = summarize_trading212_history_debug(payload)

    assert result["count"] == 2
    assert result["keys"] == ["fill", "order"]
    assert "filledQuantity" in result["order_keys"]
    assert "price" in result["fill_keys"]
    assert result["status_counts"]["FILLED"] == 2
    assert result["side_counts"]["BUY"] == 1
    assert result["side_counts"]["SELL"] == 1
    assert len(result["buy_samples"]) == 1
    assert len(result["sell_samples"]) == 1
    assert result["buy_samples"][0]["order"]["ticker"] == "AAA_US_EQ"
    assert result["sell_samples"][0]["fill"]["price"] == 12.50
    assert result["nextPagePath"] is not None


def test_trading212_debug_keeps_flat_payload_compatibility():
    payload = {
        "items": [
            {
                "id": 1,
                "ticker": "AAA_US_EQ",
                "side": "BUY",
                "status": "FILLED",
                "filledQuantity": 2,
            },
            {
                "id": 2,
                "ticker": "AAA_US_EQ",
                "side": "SELL",
                "status": "FILLED",
                "filledQuantity": 1,
            },
        ]
    }

    result = summarize_trading212_history_debug(payload)

    assert result["status_counts"]["FILLED"] == 2
    assert len(result["buy_samples"]) == 1
    assert len(result["sell_samples"]) == 1
    assert result["buy_samples"][0]["order"]["ticker"] == "AAA_US_EQ"


def test_trading212_debug_infers_side_from_signed_quantity_when_needed():
    payload = {
        "items": [
            {"order": {"ticker": "AAA_US_EQ", "quantity": 2}},
            {"order": {"ticker": "AAA_US_EQ", "quantity": -1}},
        ]
    }

    result = summarize_trading212_history_debug(payload)

    assert result["side_counts"]["BUY"] == 1
    assert result["side_counts"]["SELL"] == 1


def test_capital_debug_extracts_closed_trade_and_commission():
    payload = {
        "transactions": [
            {
                "transactionType": "TRADE",
                "note": "Trade closed",
                "instrumentName": "IES Holdings Inc",
                "reference": "abc",
                "size": "120.50",
                "currency": "USD",
                "status": "PROCESSED",
            },
            {
                "transactionType": "TRADE_COMMISSION",
                "note": "Commission",
                "reference": "abc",
                "size": "-2.00",
                "currency": "USD",
                "status": "PROCESSED",
            },
        ]
    }

    result = summarize_capital_transactions_debug(payload)

    assert result["count"] == 2
    assert len(result["trade_closed_samples"]) == 1
    assert len(result["commission_samples"]) == 1
    assert result["transaction_type_counts"]["TRADE"] == 1
    assert result["transaction_type_counts"]["TRADE_COMMISSION"] == 1
    assert "reference" in result["keys"]
