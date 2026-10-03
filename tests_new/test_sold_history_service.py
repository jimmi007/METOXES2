from metoxes.services.sold_history_service import (
    build_realized_lookup,
    summarize_freedom_realized_trades,
)


def test_freedom_sample_uses_broker_profit_and_commission():
    trades = [
        {
            "id": "625986337",
            "p": "12.12000000",
            "q": "50.00000000",
            "v": 606,
            "date": "2026-03-03T13:31:01.163",
            "profit": -12.66,
            "instr_nm": "AEGN.GR",
            "curr_c": "EUR",
            "type": "2",
            "instr_type_c": "1",
            "commission": "3.62",
            "commission_currency": "EUR",
            "commiss_exchange": ".00000000",
        },
        {
            "id": "625986338",
            "p": "12.12000000",
            "q": "60.00000000",
            "v": 727.2,
            "date": "2026-03-03T13:31:01.163",
            "profit": -15.19,
            "instr_nm": "AEGN.GR",
            "curr_c": "EUR",
            "type": "2",
            "instr_type_c": "1",
            "commission": "2.90",
            "commission_currency": "EUR",
            "commiss_exchange": ".00000000",
        },
    ]

    result = summarize_freedom_realized_trades(trades)

    assert len(result) == 1
    item = result[0]
    assert item["symbol"] == "AEGN.GR"
    assert item["sold_quantity"] == 110.0
    assert item["gross_profit_eur"] == -27.85
    assert item["commissions_eur"] == 6.52
    assert item["net_profit_loss_eur"] == -34.37
    assert item["average_sale_price_eur"] == 12.12
    assert item["history_complete"] is True


def test_non_security_and_buy_trades_are_ignored():
    trades = [
        {
            "instr_nm": "AEGN.GR",
            "q": "10",
            "type": "1",
            "instr_type_c": "1",
        },
        {
            "instr_nm": "USD/EUR",
            "q": "1000",
            "type": "2",
            "instr_type_c": "6",
        },
    ]

    assert summarize_freedom_realized_trades(trades) == []


def test_realized_lookup_is_symbol_platform_keyed():
    summaries = [
        {
            "symbol": "AEGN.GR",
            "platform": "Freedom24",
            "net_profit_loss_eur": -34.37,
        }
    ]

    lookup = build_realized_lookup(summaries)

    assert lookup[("AEGN.GR", "FREEDOM24")]["net_profit_loss_eur"] == -34.37


def test_capital_realized_uses_signed_trade_closed_size():
    from metoxes.services.sold_history_service import summarize_capital_realized_transactions

    transactions = [
        {
            "dateUtc": "2026-09-29T17:50:26.989",
            "instrumentName": "IESC",
            "transactionType": "TRADE",
            "note": "Trade closed",
            "reference": "140257752509056",
            "size": "181.3",
            "currency": "EUR",
            "status": "PROCESSED",
            "dealId": "002454c3-0001-54c4-0000-0000834a0010",
        },
        {
            "dateUtc": "2026-09-28T17:12:31.530",
            "instrumentName": "IESC",
            "transactionType": "TRADE",
            "note": "Trade closed",
            "reference": "140164769923603",
            "size": "179.37",
            "currency": "EUR",
            "status": "PROCESSED",
            "dealId": "002454c3-0001-54c4-0000-0000834a0010",
        },
        {
            "dateUtc": "2026-08-28T14:54:56.106",
            "instrumentName": "LHA",
            "transactionType": "TRADE",
            "note": "Trade closed",
            "reference": "137347607956954",
            "size": "-24.48",
            "currency": "EUR",
            "status": "PROCESSED",
        },
        {
            "instrumentName": "IGNORED",
            "transactionType": "DEPOSIT",
            "note": "Deposit",
            "reference": "x",
            "size": "1000",
            "currency": "EUR",
            "status": "PROCESSED",
        },
    ]

    result = summarize_capital_realized_transactions(transactions)
    by_symbol = {item["symbol"]: item for item in result}

    assert by_symbol["IESC"]["net_profit_loss_eur"] == 360.67
    assert by_symbol["IESC"]["closed_transactions"] == 2
    assert by_symbol["IESC"]["pnl_verified"] is True
    assert by_symbol["IESC"]["sale_proceeds_eur"] is None
    assert by_symbol["LHA"]["net_profit_loss_eur"] == -24.48


def test_capital_reference_is_deduplicated():
    from metoxes.services.sold_history_service import summarize_capital_realized_transactions

    tx = {
        "dateUtc": "2026-09-29T17:50:26.989",
        "instrumentName": "IESC",
        "transactionType": "TRADE",
        "note": "Trade closed",
        "reference": "same-ref",
        "size": "181.3",
        "currency": "EUR",
        "status": "PROCESSED",
    }

    result = summarize_capital_realized_transactions([tx, dict(tx)])
    assert result[0]["net_profit_loss_eur"] == 181.3
    assert result[0]["closed_transactions"] == 1
