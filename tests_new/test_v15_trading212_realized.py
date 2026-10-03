
from metoxes.services.sold_history_service import (
    build_realized_lookup,
    merge_realized_history_results,
    normalize_trading212_symbol,
    summarize_trading212_realized_orders,
)


def test_trading212_realized_uses_broker_wallet_pnl_and_ignores_cancelled():
    items = [
        {
            "order": {
                "id": 58107878506,
                "ticker": "GASS_US_EQ",
                "side": "SELL",
                "status": "FILLED",
                "filledQuantity": -40.45804,
                "currency": "EUR",
            },
            "fill": {
                "id": 58156298992,
                "quantity": -40.45804,
                "price": 9.02,
                "type": "TRADE",
                "filledAt": "2026-09-30T13:39:59.000Z",
                "walletImpact": {
                    "currency": "EUR",
                    "netValue": 320.87,
                    "realisedProfitLoss": 94.34,
                    "fxRate": 1.1356201,
                    "taxes": [{
                        "name": "CURRENCY_CONVERSION_FEE",
                        "quantity": -0.48,
                        "currency": "EUR",
                    }],
                },
            },
        },
        {
            "order": {
                "id": 58058257819,
                "ticker": "GASS_US_EQ",
                "side": "SELL",
                "status": "CANCELLED",
                "filledQuantity": 0,
            },
            "fill": {},
        },
    ]

    result = summarize_trading212_realized_orders(items)

    assert len(result) == 1
    item = result[0]
    assert item["symbol"] == "GASS"
    assert item["platform"] == "Trading212"
    assert item["sell_trades"] == 1
    assert item["sold_quantity"] == 40.45804
    assert item["sale_proceeds_eur"] == 320.87
    assert item["cost_basis_eur"] == 226.53
    assert item["net_profit_loss_eur"] == 94.34
    assert item["commissions_eur"] == 0.48
    assert item["realized_return_pct"] == 41.65
    assert item["pnl_verified"] is True
    assert item["fill_ids"] == ["58156298992"]


def test_trading212_realized_keeps_negative_broker_pnl():
    items = [{
        "order": {
            "ticker": "CELH_US_EQ",
            "side": "SELL",
            "status": "FILLED",
        },
        "fill": {
            "id": 58153143946,
            "quantity": -13.996531,
            "price": 28.02,
            "type": "TRADE",
            "filledAt": "2026-09-30T13:04:47.000Z",
            "walletImpact": {
                "currency": "EUR",
                "netValue": 344.68,
                "realisedProfitLoss": -34.23,
                "taxes": [],
            },
        },
    }]

    result = summarize_trading212_realized_orders(items)
    assert result[0]["symbol"] == "CELH"
    assert result[0]["net_profit_loss_eur"] == -34.23


def test_trading212_fill_id_is_deduplicated():
    row = {
        "order": {
            "ticker": "CRDO_US_EQ",
            "side": "SELL",
            "status": "FILLED",
        },
        "fill": {
            "id": 58257698893,
            "quantity": -9.4,
            "price": 218.02,
            "type": "TRADE",
            "filledAt": "2026-10-02T13:39:06.000Z",
            "walletImpact": {
                "currency": "EUR",
                "netValue": 1818.46,
                "realisedProfitLoss": 450.75,
                "taxes": [],
            },
        },
    }

    result = summarize_trading212_realized_orders([row, dict(row)])
    assert result[0]["sell_trades"] == 1
    assert result[0]["net_profit_loss_eur"] == 450.75


def test_trading212_symbol_normalization():
    assert normalize_trading212_symbol("GASS_US_EQ") == "GASS"
    assert normalize_trading212_symbol("VUSAl_EQ") == "VUSA.L"
    assert normalize_trading212_symbol("RAREd_EQ") == "RARE.DE"
    assert normalize_trading212_symbol("FOODm_EQ") == "FOOD.MI"


def test_three_broker_merge_reports_trading212_enabled():
    result = merge_realized_history_results(
        {"lookup": {}, "summaries": [], "meta": {"broker": "Freedom24", "source": "F", "status": "OK"}},
        {"lookup": {}, "summaries": [], "meta": {"broker": "Capital", "source": "C", "status": "OK"}},
        {
            "lookup": {("GASS", "TRADING212"): {"symbol": "GASS", "platform": "Trading212", "net_profit_loss_eur": 94.34}},
            "summaries": [{"symbol": "GASS", "platform": "Trading212", "net_profit_loss_eur": 94.34}],
            "meta": {"broker": "Trading212", "source": "T", "status": "OK"},
        },
    )
    assert result["meta"]["trading212_status"] == "OK"
    assert result["meta"]["realized_symbol_platform_pairs"] == 1
    assert result["lookup"][("GASS", "TRADING212")]["net_profit_loss_eur"] == 94.34
