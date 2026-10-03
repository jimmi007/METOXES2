from pathlib import Path


def test_v13_stock_router_contains_required_routes_and_one_update_route():
    stock_path = Path(__file__).resolve().parents[1] / "metoxes" / "routers" / "stock.py"
    text = stock_path.read_text(encoding="utf-8")

    assert 'BUILD_VERSION = "V14-score-accordion-fmp-explain"' in text
    assert '@router.get("/stocks/enrichment-status")' in text
    assert '@router.get("/stocks/capital/realized")' in text
    assert '@router.get("/stocks/freedom/realized")' in text
    assert '@router.get("/stocks/trading212/history-debug")' in text
    assert text.count('@router.post("/stocks/update-excel")') == 1
