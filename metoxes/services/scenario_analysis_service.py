from __future__ import annotations

"""Transparent what-if analysis for METOXES2.

Scenarios are *shadow* scores. They reuse the deterministic scoring thresholds
already used by the project while holding the peer-relative component fixed.
They never overwrite ``final_score``.
"""

import math

from metoxes.services.absolute_quality_service import (
    ABSOLUTE_METRIC_WEIGHTS,
    ABSOLUTE_SCORERS,
    MIN_ABSOLUTE_COVERAGE,
    RELATIVE_WEIGHT as GENERAL_RELATIVE_WEIGHT,
    ABSOLUTE_WEIGHT as GENERAL_ABSOLUTE_WEIGHT,
)
from metoxes.services.financial_sector_scoring_service import (
    METRIC_WEIGHTS as FINANCIAL_METRIC_WEIGHTS,
    SCORERS as FINANCIAL_SCORERS,
    MIN_COVERAGE as FINANCIAL_MIN_COVERAGE,
    RELATIVE_WEIGHT as FINANCIAL_RELATIVE_WEIGHT,
    ABSOLUTE_WEIGHT as FINANCIAL_ABSOLUTE_WEIGHT,
)


def _safe_float(value):
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _clamp(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _is_financial(row):
    return bool(row.get("financial_model")) or str(row.get("sector") or "").strip() == "Financial Services"


def _weighted_absolute(row, weights, scorers):
    total = 0.0
    available = 0.0
    components = {}
    for field, weight in weights.items():
        scorer = scorers[field]
        score = scorer(row.get(field))
        components[field] = score
        if score is None:
            continue
        total += score * weight
        available += weight
    if available <= 0:
        return None, 0.0, components
    absolute = total / available
    coverage = available / sum(weights.values())
    return round(absolute, 2), coverage, components


def calculate_shadow_score(row):
    """Recalculate a comparable score from a row after scenario shocks."""
    if _is_financial(row):
        absolute, coverage, components = _weighted_absolute(
            row,
            FINANCIAL_METRIC_WEIGHTS,
            FINANCIAL_SCORERS,
        )
        relative = _safe_float(row.get("financial_relative_score"))
        if relative is None:
            relative = _safe_float(row.get("relative_score"))
        if relative is None:
            # If historical/public payload no longer has hidden relative score,
            # use the observed live score as the fixed peer anchor.
            relative = _safe_float(row.get("final_score"))
        if relative is None:
            final = absolute
            mode = "financial_absolute_only"
        elif absolute is None or coverage < FINANCIAL_MIN_COVERAGE:
            final = relative
            mode = "financial_relative_only"
        else:
            final = relative * FINANCIAL_RELATIVE_WEIGHT + absolute * FINANCIAL_ABSOLUTE_WEIGHT
            mode = "financial_shadow_60_40"
    else:
        absolute, coverage, components = _weighted_absolute(
            row,
            ABSOLUTE_METRIC_WEIGHTS,
            ABSOLUTE_SCORERS,
        )
        relative = _safe_float(row.get("relative_score"))
        if relative is None:
            relative = _safe_float(row.get("final_score"))
        if relative is None:
            final = absolute
            mode = "absolute_only"
        elif absolute is None or coverage < MIN_ABSOLUTE_COVERAGE:
            final = relative
            mode = "relative_only"
        else:
            final = relative * GENERAL_RELATIVE_WEIGHT + absolute * GENERAL_ABSOLUTE_WEIGHT
            mode = "shadow_60_40"

    return {
        "score": None if final is None else round(_clamp(final), 2),
        "absolute_score": absolute,
        "coverage_pct": round(coverage * 100, 2),
        "mode": mode,
        "component_scores": components,
    }


def _subtract_pp(row, field, shock_pp):
    value = _safe_float(row.get(field))
    if value is not None:
        row[field] = value + float(shock_pp)


def _multiply(row, field, multiplier):
    value = _safe_float(row.get(field))
    if value is not None:
        row[field] = value * float(multiplier)


def apply_custom_shocks(
    row,
    eps_growth_shock_pp=0.0,
    revenue_growth_shock_pp=0.0,
    fcf_growth_shock_pp=0.0,
    roic_change_pct=0.0,
    roe_change_pct=0.0,
    profit_margin_shock_pp=0.0,
):
    stressed = dict(row)

    _subtract_pp(stressed, "forward_eps_growth", eps_growth_shock_pp)
    _subtract_pp(stressed, "financial_forward_eps_growth", eps_growth_shock_pp)
    _subtract_pp(stressed, "forward_revenue_growth", revenue_growth_shock_pp)
    _subtract_pp(stressed, "financial_revenue_growth", revenue_growth_shock_pp)
    _subtract_pp(stressed, "fcf_growth", fcf_growth_shock_pp)
    _subtract_pp(stressed, "financial_profit_margin", profit_margin_shock_pp)

    _multiply(stressed, "roic", 1.0 + float(roic_change_pct) / 100.0)
    _multiply(stressed, "financial_roe", 1.0 + float(roe_change_pct) / 100.0)
    return stressed


def analyze_custom_scenario(
    row,
    eps_growth_shock_pp=-15.0,
    revenue_growth_shock_pp=0.0,
    fcf_growth_shock_pp=0.0,
    roic_change_pct=0.0,
    roe_change_pct=0.0,
    profit_margin_shock_pp=0.0,
    name="custom",
):
    base_score = _safe_float(row.get("final_score"))
    # Calibrate the shadow engine against its own unshocked baseline. This is
    # important for public/dashboard payloads where hidden relative_score is
    # intentionally absent: the *delta* remains valid without exposing it.
    baseline_shadow = calculate_shadow_score(row).get("score")

    stressed = apply_custom_shocks(
        row,
        eps_growth_shock_pp=eps_growth_shock_pp,
        revenue_growth_shock_pp=revenue_growth_shock_pp,
        fcf_growth_shock_pp=fcf_growth_shock_pp,
        roic_change_pct=roic_change_pct,
        roe_change_pct=roe_change_pct,
        profit_margin_shock_pp=profit_margin_shock_pp,
    )
    calculated = calculate_shadow_score(stressed)
    stressed_shadow = calculated.get("score")
    delta = None
    scenario_score = stressed_shadow
    if baseline_shadow is not None and stressed_shadow is not None:
        delta = round(stressed_shadow - baseline_shadow, 2)
        if base_score is not None:
            scenario_score = round(_clamp(base_score + delta), 2)

    return {
        "name": name,
        "base_final_score": base_score,
        "scenario_score": scenario_score,
        "score_delta": delta,
        "shocks": {
            "eps_growth_shock_pp": float(eps_growth_shock_pp),
            "revenue_growth_shock_pp": float(revenue_growth_shock_pp),
            "fcf_growth_shock_pp": float(fcf_growth_shock_pp),
            "roic_change_pct": float(roic_change_pct),
            "roe_change_pct": float(roe_change_pct),
            "profit_margin_shock_pp": float(profit_margin_shock_pp),
        },
        "coverage_pct": calculated.get("coverage_pct"),
        "mode": calculated.get("mode"),
    }


def _risk_label(delta):
    value = _safe_float(delta)
    if value is None:
        return "insufficient_data"
    if value <= -12:
        return "high_sensitivity"
    if value <= -6:
        return "moderate_sensitivity"
    return "low_sensitivity"


def build_standard_scenarios(row):
    eps = analyze_custom_scenario(
        row,
        eps_growth_shock_pp=-15.0,
        name="EPS growth -15pp",
    )
    growth = analyze_custom_scenario(
        row,
        revenue_growth_shock_pp=-10.0,
        fcf_growth_shock_pp=-20.0,
        name="Growth slowdown",
    )
    bear = analyze_custom_scenario(
        row,
        eps_growth_shock_pp=-20.0,
        revenue_growth_shock_pp=-10.0,
        fcf_growth_shock_pp=-25.0,
        roic_change_pct=-20.0,
        roe_change_pct=-20.0,
        profit_margin_shock_pp=-5.0,
        name="Bear case",
    )
    deltas = [
        _safe_float(eps.get("score_delta")),
        _safe_float(growth.get("score_delta")),
        _safe_float(bear.get("score_delta")),
    ]
    deltas = [x for x in deltas if x is not None]
    worst_delta = min(deltas) if deltas else None
    label = _risk_label(worst_delta)

    def fmt(item):
        score = item.get("scenario_score")
        delta = item.get("score_delta")
        if score is None:
            return f"{item['name']}: ανεπαρκή δεδομένα"
        return f"{item['name']}: {score:.2f}/100 ({delta:+.2f} μονάδες)" if delta is not None else f"{item['name']}: {score:.2f}/100"

    summary = "; ".join(fmt(item) for item in (eps, growth, bear)) + f". Sensitivity: {label}."
    return {
        "scenario_eps_minus_15_score": eps.get("scenario_score"),
        "scenario_eps_minus_15_delta": eps.get("score_delta"),
        "scenario_growth_slowdown_score": growth.get("scenario_score"),
        "scenario_growth_slowdown_delta": growth.get("score_delta"),
        "scenario_bear_score": bear.get("scenario_score"),
        "scenario_bear_delta": bear.get("score_delta"),
        "scenario_risk_label": label,
        "scenario_summary": summary,
        "scenario_details": [eps, growth, bear],
    }


def enrich_standard_scenarios(rows):
    result = [dict(row) for row in rows or []]
    for row in result:
        row.update(build_standard_scenarios(row))
    return result
