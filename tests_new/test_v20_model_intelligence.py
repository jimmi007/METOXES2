from datetime import date, timedelta
import json
from pathlib import Path

from metoxes.services.event_impact_service import build_rule_event_impact
from metoxes.services.peer_intelligence_service import enrich_peer_intelligence
from metoxes.services.scenario_analysis_service import build_standard_scenarios, analyze_custom_scenario
from metoxes.services.model_backtest_service import run_score_backtest
from metoxes.services.ai_commentary_service import build_rule_commentary
from metoxes.services.dashboard_service import generate_portfolio_dashboard


def _base_row(symbol="AAA", score=75.0):
    return {
        "symbol": symbol,
        "name": f"{symbol} Corp",
        "sector": "Technology",
        "country": "United States",
        "platform": "Research",
        "current_price": 100.0,
        "final_score": score,
        "relative_score": 72.0,
        "fcf_yield": 6.0,
        "roic": 18.0,
        "fcf_growth": 15.0,
        "forward_revenue_growth": 12.0,
        "forward_eps_growth": 18.0,
    }


def test_event_impact_positive_earnings_and_news():
    row = _base_row()
    row.update({
        "news_headlines": [{"title": "Company beats estimates and raises guidance"}],
        "earnings_eps_estimate": 1.0,
        "earnings_eps_actual": 1.2,
        "earnings_revenue_estimate": 100.0,
        "earnings_revenue_actual": 108.0,
    })
    result = build_rule_event_impact(row)
    assert result["event_impact_score"] > 0
    assert result["event_impact_label"] == "positive"
    assert result["earnings_eps_surprise_pct"] == 20.0


def test_peer_fallback_compares_same_sector_without_network(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    rows = [
        _base_row("AAA", 80),
        {**_base_row("BBB", 65), "fcf_yield": 3.0, "roic": 10.0, "forward_revenue_growth": 5.0, "forward_eps_growth": 6.0},
        {**_base_row("CCC", 60), "fcf_yield": 4.0, "roic": 12.0, "forward_revenue_growth": 7.0, "forward_eps_growth": 8.0},
    ]
    enriched = enrich_peer_intelligence(rows, workers=1, max_network_rows=0, max_peers=5)
    first = enriched[0]
    assert first["peer_count"] == 2
    assert first["peer_source"] == "industry/sector fallback from analysed universe"
    assert first["peer_quality_percentile"] > 50
    assert first["peer_strengths"]


def test_scenario_stress_reduces_shadow_score():
    row = _base_row()
    scenarios = build_standard_scenarios(row)
    assert scenarios["scenario_eps_minus_15_score"] < row["final_score"]
    assert scenarios["scenario_eps_minus_15_delta"] < 0
    assert scenarios["scenario_bear_score"] <= scenarios["scenario_eps_minus_15_score"]

    custom = analyze_custom_scenario(row, eps_growth_shock_pp=-15)
    assert custom["scenario_score"] < custom["base_final_score"]


def test_backtest_detects_predictive_score_and_recommends_weights(tmp_path):
    history_file = tmp_path / "history.jsonl"
    old_day = date.today() - timedelta(days=180)
    rows = []
    price_map = {}
    for i in range(1, 21):
        symbol = f"T{i:02d}"
        rows.append({
            "snapshot_date": old_day.isoformat(),
            "source": "test",
            "symbol": symbol,
            "platform": "Research",
            "sector": "Technology",
            "current_price": 100.0,
            "final_score": 40.0 + i,
            "fcf_yield": float(i),
            "roic": float(i),
            "fcf_growth": float(i),
            "forward_revenue_growth": float(i),
            "forward_eps_growth": float(i),
        })
        price_map[symbol] = 100.0 + i * 2.0

    history_file.write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n",
        encoding="utf-8",
    )

    def fake_price(symbol, target_date):
        return price_map.get(symbol)

    report = run_score_backtest(
        horizon_days=90,
        min_samples=12,
        benchmark=None,
        as_of_date=date.today(),
        history_path=history_file,
        price_fetcher=fake_price,
        save=False,
    )
    assert report["status"] == "ok"
    assert report["evaluated_samples"] == 20
    assert report["final_score_predictive_ic"]["directional_ic"] > 0.9
    assert report["quartile_test"]["top_minus_bottom_spread_pct"] > 0
    assert report["general_model"]["weight_source"] == "ic_recommended"


def test_commentary_and_dashboard_include_v20_intelligence(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    row = _base_row()
    row.update({
        "peer_summary": "Σύγκριση με 4 peers: above peer median.",
        "peer_symbols": ["BBB", "CCC"],
        "peer_strengths": ["ROIC πάνω από median peers."],
        "peer_weaknesses": [],
        "event_impact_score": 30.0,
        "event_impact_label": "positive",
        "event_impact_confidence": "medium",
        "event_impact_summary": "Θετικό earnings signal.",
        "scenario_summary": "Bear case: 66/100 (-9 μονάδες).",
        "scenario_eps_minus_15_score": 71.0,
        "scenario_eps_minus_15_delta": -4.0,
        "scenario_growth_slowdown_score": 69.0,
        "scenario_growth_slowdown_delta": -6.0,
        "scenario_bear_score": 66.0,
        "scenario_bear_delta": -9.0,
        "scenario_risk_label": "moderate_sensitivity",
    })
    text = build_rule_commentary(row)
    assert "Ανταγωνιστές" in text
    assert "Event impact" in text
    assert "Scenario analysis" in text

    out_json = tmp_path / "dash.json"
    out_html = tmp_path / "dash.html"
    generate_portfolio_dashboard(
        [row],
        quality_report={},
        candidates=[],
        json_path=out_json,
        html_path=out_html,
    )
    html = out_html.read_text(encoding="utf-8")
    assert "Πραγματικοί ανταγωνιστές / Peers" in html
    assert "News & Earnings Impact" in html
    assert "Scenario Analysis" in html
    assert "Model Intelligence — Backtest & Learning" in html
