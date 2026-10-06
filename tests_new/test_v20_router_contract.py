from pathlib import Path


def test_v20_router_contract():
    path = Path(__file__).resolve().parents[1] / "metoxes" / "routers" / "stock.py"
    text = path.read_text(encoding="utf-8")
    assert 'BUILD_VERSION = "V20-ai-model-intelligence"' in text
    assert '@router.get("/stocks/model-intelligence")' in text
    assert '@router.get("/stocks/scenario/{symbol}")' in text
    assert '@router.post("/stocks/backtest-scores")' in text
    assert "enrich_peer_intelligence" in text
    assert "enrich_event_impact" in text
    assert "enrich_standard_scenarios" in text
    assert "record_model_snapshots" in text
