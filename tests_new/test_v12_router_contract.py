from pathlib import Path


def test_v12_stock_router_contains_required_routes_and_one_update_route():
    stock_path = Path(__file__).resolve().parents[1] / "metoxes" / "routers" / "stock.py"
    text = stock_path.read_text(encoding="utf-8")

    assert 'BUILD_VERSION = "V12-capital-sold-enrichment"' in text
    assert '@router.get("/stocks/enrichment-status")' in text
    assert '@router.get("/stocks/capital/realized")' in text
    assert text.count('@router.post("/stocks/update-excel")') == 1
    assert "safe_collect_capital_realized_history" in text
    assert "merge_realized_history_results" in text
    assert "sold_realized_lookup=sold_history_result.get(" in text
