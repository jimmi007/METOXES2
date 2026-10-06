from __future__ import annotations

"""AI/rule-based commentary for portfolio and candidate stocks.

When OPENAI_API_KEY exists, the service calls the OpenAI Responses API in
small batches.  Without a key (or when the request fails) every stock still
receives a deterministic explanation built from the same structured inputs.
"""

import json
import math
import os

import httpx


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")


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


def _fmt(value, suffix="%"):
    number = _safe_float(value)
    return "μη διαθέσιμο" if number is None else f"{number:.2f}{suffix}"


def _score_band(score):
    value = _safe_float(score)
    if value is None:
        return "χωρίς επαρκές score"
    if value >= 80:
        return "υψηλό"
    if value >= 65:
        return "καλό"
    if value >= 50:
        return "μέτριο"
    return "χαμηλό"


def build_rule_commentary(row):
    name = str(row.get("name") or row.get("symbol") or "Η μετοχή").strip()
    score = _safe_float(row.get("final_score"))
    score_text = f"{score:.2f}/100" if score is not None else "μη διαθέσιμο"

    rationale = str(row.get("score_rationale_text") or "").strip()
    if not rationale:
        model = row.get("financial_model")
        if model:
            rationale = (
                f"Το ειδικό μοντέλο Financial Services χρησιμοποιεί ROE {_fmt(row.get('financial_roe'))}, "
                f"P/B {_fmt(row.get('financial_price_to_book'), '')}, περιθώριο {_fmt(row.get('financial_profit_margin'))} "
                f"και forward EPS growth {_fmt(row.get('financial_forward_eps_growth'))}."
            )
        else:
            rationale = (
                f"Οι βασικοί δείκτες είναι FCF Yield {_fmt(row.get('fcf_yield'))}, ROIC {_fmt(row.get('roic'))}, "
                f"FCF Growth {_fmt(row.get('fcf_growth'))}, forward revenue {_fmt(row.get('forward_revenue_growth'))} "
                f"και forward EPS {_fmt(row.get('forward_eps_growth'))}."
            )

    news = row.get("news_headlines") or []
    if news:
        titles = "; ".join(str(item.get("title") or "") for item in news[:2] if isinstance(item, dict))
        market_text = f" Πρόσφατες ειδήσεις: {titles}."
    else:
        market_text = " Δεν βρέθηκαν πρόσφατοι τίτλοι ειδήσεων στο τελευταίο refresh."

    earnings_date = row.get("earnings_date")
    if earnings_date:
        market_text += f" Earnings: {earnings_date}."

    cross_text = str(row.get("score_crosscheck_text") or "").strip()
    if not cross_text:
        source = row.get("secondary_source")
        cross = row.get("fundamental_crosscheck_status")
        if source:
            cross_text = f"Ανεξάρτητος έλεγχος {source}: {cross or 'διαθέσιμος'}."

    anomaly = str(row.get("anomaly_summary") or "").strip()
    anomaly_text = f" Έλεγχος δεδομένων: {anomaly}." if anomaly else ""
    cross_suffix = f" {cross_text}" if cross_text else ""

    peer_text = str(row.get("peer_summary") or "").strip()
    peer_suffix = f" Ανταγωνιστές: {peer_text}" if peer_text else ""

    event_summary = str(row.get("event_impact_summary") or "").strip()
    event_score = _safe_float(row.get("event_impact_score"))
    if event_summary:
        event_suffix = (
            f" Event impact {event_score:+.0f}/100: {event_summary}"
            if event_score is not None
            else f" Event impact: {event_summary}"
        )
    else:
        event_suffix = ""

    scenario_text = str(row.get("scenario_summary") or "").strip()
    scenario_suffix = f" Scenario analysis: {scenario_text}" if scenario_text else ""

    return (
        f"Η {name} έχει Final Score {score_text}. {rationale}{cross_suffix}{market_text}{peer_suffix}"
        f"{event_suffix}{scenario_suffix}{anomaly_text} "
        "Η ανάλυση είναι επεξήγηση του μοντέλου και όχι σύσταση αγοράς ή πώλησης."
    )

def _public_context(row):
    keys = (
        "symbol", "name", "sector", "country", "final_score", "percent_change",
        "avg_monthly_change", "fcf_yield", "fcf_growth", "roic",
        "forward_revenue_growth", "forward_eps_growth", "financial_model",
        "financial_roe", "financial_price_to_book", "financial_profit_margin",
        "financial_revenue_growth", "financial_forward_eps_growth",
        "secondary_source", "fundamental_crosscheck_status", "fundamental_discrepancy_pct",
        "news_sentiment", "news_headlines", "earnings_date", "earnings_eps_estimate",
        "earnings_eps_actual", "anomaly_summary", "discount_from_52w_high_pct",
        "score_rationale_headline", "score_rationale_text", "score_drivers",
        "score_weaknesses", "score_crosscheck_text", "score_model_label",
        "industry", "peer_source", "peer_symbols", "peer_count",
        "peer_quality_percentile", "peer_advantage_label", "peer_strengths",
        "peer_weaknesses", "peer_summary",
        "event_impact_score", "event_impact_label", "event_impact_confidence",
        "event_impact_summary", "event_impact_source",
        "scenario_eps_minus_15_score", "scenario_eps_minus_15_delta",
        "scenario_growth_slowdown_score", "scenario_growth_slowdown_delta",
        "scenario_bear_score", "scenario_bear_delta", "scenario_risk_label",
        "scenario_summary",
    )
    return {key: row.get(key) for key in keys}


def _extract_output_text(payload):
    if isinstance(payload.get("output_text"), str):
        return payload["output_text"]
    pieces = []
    for item in payload.get("output") or []:
        if not isinstance(item, dict):
            continue
        for content in item.get("content") or []:
            if isinstance(content, dict) and content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    pieces.append(text)
    return "\n".join(pieces)


def _parse_json_text(text):
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        payload = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            payload = json.loads(raw[start:end + 1])
        except Exception:
            return {}
    return payload if isinstance(payload, dict) else {}


def _call_openai_batch(rows):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or os.getenv("AI_COMMENTARY_ENABLED", "1").lower() in {"0", "false", "no"}:
        return {}

    requested = [_public_context(row) for row in rows]
    prompt = (
        "Είσαι αναλυτής δεδομένων μετοχών. Για κάθε εγγραφή γράψε 90-140 λέξεις στα ελληνικά. "
        "Εξήγησε γιατί προκύπτει το final_score, ανέφερε 2 θετικά και 2 κινδύνους, σύγκρινε τη μετοχή με τους πραγματικούς/διαθέσιμους peers, "
        "εξήγησε το news/earnings event impact και τι δείχνει το scenario stress test. Ανέφερε discrepancy δεύτερης πηγής και anomalies όπου υπάρχουν. "
        "Μην κάνεις σύσταση αγοράς/πώλησης και μην εφευρίσκεις στοιχεία. Αν peer/event/scenario δεδομένα λείπουν, πες το καθαρά. "
        "Επέστρεψε ΜΟΝΟ JSON object {\"SYMBOL\": \"commentary\"}.\n\nDATA:\n"
        + json.dumps(requested, ensure_ascii=False, default=str)
    )

    body = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": prompt,
        "max_output_tokens": max(1200, 350 * len(rows)),
    }
    with httpx.Client(timeout=90.0) as client:
        response = client.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
    return _parse_json_text(_extract_output_text(payload))


def enrich_ai_commentary(rows, batch_size=8):
    result = [dict(row) for row in rows or []]
    if not result:
        return result

    for row in result:
        row["ai_commentary"] = build_rule_commentary(row)
        row["ai_commentary_source"] = "rules_fallback"

    if not os.getenv("OPENAI_API_KEY"):
        return result

    size = max(1, int(batch_size))
    halted_error = None
    for start in range(0, len(result), size):
        chunk = result[start:start + size]
        if halted_error is not None:
            for row in chunk:
                row["ai_commentary_error"] = halted_error
            continue
        try:
            generated = _call_openai_batch(chunk)
        except Exception as error:
            message = str(error)[:300]
            for row in chunk:
                row["ai_commentary_error"] = message
            if "429" in message or "Too Many Requests" in message:
                halted_error = message
            continue

        for row in chunk:
            symbol = str(row.get("symbol") or "").strip()
            text = generated.get(symbol) or generated.get(symbol.upper())
            if isinstance(text, str) and len(text.strip()) >= 40:
                row["ai_commentary"] = text.strip()
                row["ai_commentary_source"] = f"OpenAI/{os.getenv('OPENAI_MODEL', DEFAULT_MODEL)}"

    return result
