import pytest

from metoxes.services.absolute_quality_service import (
    add_absolute_quality_scores,
    score_fcf_growth,
)


def test_strong_absolute_quality_lifts_final_score():
    rows = [
        {
            "symbol": "STRONG",
            "final_score": 80,
            "fcf_yield": 10,
            "roic": 25,
            "fcf_growth": 30,
            "forward_revenue_growth": 20,
            "forward_eps_growth": 30,
        }
    ]

    result = add_absolute_quality_scores(
        rows
    )[0]

    assert result["relative_score"] == 80
    assert result["absolute_score"] == 100
    assert result["final_score"] == 88
    assert (
        result["score_mode"]
        == "relative_60_absolute_40"
    )


def test_weak_absolute_quality_reduces_high_relative_score():
    rows = [
        {
            "symbol": "WEAK",
            "final_score": 90,
            "fcf_yield": 0,
            "roic": 0,
            "fcf_growth": -25,
            "forward_revenue_growth": -10,
            "forward_eps_growth": -20,
        }
    ]

    result = add_absolute_quality_scores(
        rows
    )[0]

    assert result["absolute_score"] == 0
    assert result["final_score"] == 54


def test_extreme_fcf_growth_is_capped_at_100():
    assert score_fcf_growth(30) == 100
    assert score_fcf_growth(1000) == 100


def test_insufficient_absolute_data_keeps_relative_score():
    rows = [
        {
            "symbol": "SPARSE",
            "final_score": 72,
            "fcf_yield": 10,
            "roic": None,
            "fcf_growth": None,
            "forward_revenue_growth": None,
            "forward_eps_growth": None,
        }
    ]

    result = add_absolute_quality_scores(
        rows
    )[0]

    assert result["absolute_coverage"] == 25
    assert result["final_score"] == 72
    assert result["score_mode"] == "relative_only"


def test_missing_metrics_are_renormalized_when_coverage_is_enough():
    rows = [
        {
            "symbol": "PARTIAL",
            "final_score": 70,
            "fcf_yield": 10,
            "roic": 25,
            "fcf_growth": None,
            "forward_revenue_growth": None,
            "forward_eps_growth": None,
        }
    ]

    result = add_absolute_quality_scores(
        rows
    )[0]

    assert result["absolute_coverage"] == 50
    assert result["absolute_score"] == pytest.approx(100)
    assert result["final_score"] == 82
