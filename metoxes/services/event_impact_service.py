from __future__ import annotations

"""Estimate the likely near-term impact of recent news and earnings.

The service is deliberately advisory: it never overwrites the deterministic
Final Score.  It produces a separate -100..+100 event-impact score plus a
short explanation.  OpenAI is used when configured; otherwise a transparent
rules fallback is always available.
"""

import json
import math
import os
import re

import httpx


OPENAI_RESPONSES_URL = "https://api.openai.com/v1/responses"
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-6-luna")

POSITIVE_TERMS = {
    "beat": 12, "beats": 12, "raised guidance": 18, "raises guidance": 18,
    "upgrade": 10, "upgraded": 10, "record": 8, "strong": 7,
    "growth": 5, "profit": 6, "wins": 7, "contract": 6,
    "approval": 10, "approved": 10, "buyback": 8, "dividend": 4,
}
NEGATIVE_TERMS = {
    "miss": -12, "misses": -12, "cuts guidance": -18, "cut guidance": -18,
    "downgrade": -10, "downgraded": -10, "warning": -10, "weak": -7,
    "loss": -7, "lawsuit": -8, "probe": -10, "investigation": -10,
    "decline": -6, "layoff": -5, "recall": -8, "default": -18,
}


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


def _clamp(value, low=-100.0, high=100.0):
    return max(low, min(high, float(value)))


def _surprise(actual, estimate):
    actual = _safe_float(actual)
    estimate = _safe_float(estimate)
    if actual is None or estimate in (None, 0):
        return None
    return (actual - estimate) / abs(estimate) * 100


def _label(score):
    value = _safe_float(score) or 0.0
    if value >= 25:
        return "positive"
    if value <= -25:
        return "negative"
    return "neutral"


def _headline_score(headlines):
    score = 0.0
    matched = []
    for item in headlines or []:
        title = str(item.get("title") or "") if isinstance(item, dict) else str(item or "")
        text = re.sub(r"\s+", " ", title.lower())
        for term, weight in POSITIVE_TERMS.items():
            if term in text:
                score += weight
                matched.append(term)
        for term, weight in NEGATIVE_TERMS.items():
            if term in text:
                score += weight
                matched.append(term)
    return _clamp(score, -55, 55), matched


def build_rule_event_impact(row):
    news_score, matched_terms = _headline_score(row.get("news_headlines") or [])

    eps_surprise = _surprise(
        row.get("earnings_eps_actual"),
        row.get("earnings_eps_estimate"),
    )
    revenue_surprise = _surprise(
        row.get("earnings_revenue_actual"),
        row.get("earnings_revenue_estimate"),
    )

    earnings_score = 0.0
    evidence_count = 0
    if eps_surprise is not None:
        earnings_score += _clamp(eps_surprise * 1.4, -55, 55)
        evidence_count += 1
    if revenue_surprise is not None:
        earnings_score += _clamp(revenue_surprise * 0.8, -35, 35)
        evidence_count += 1

    if row.get("news_headlines"):
        evidence_count += 1

    score = _clamp(news_score * 0.55 + earnings_score * 0.45)
    if evidence_count == 0:
        confidence = "low"
    elif evidence_count == 1:
        confidence = "medium"
    else:
        confidence = "high"

    parts = []
    if row.get("news_headlines"):
        parts.append(
            f"News signal {news_score:+.0f}/100 από {len(row.get('news_headlines') or [])} πρόσφατους τίτλους."
        )
    else:
        parts.append("Δεν υπάρχουν αρκετοί πρόσφατοι τίτλοι για ισχυρό news signal.")
    if eps_surprise is not None:
        parts.append(f"EPS surprise {eps_surprise:+.1f}%.")
    if revenue_surprise is not None:
        parts.append(f"Revenue surprise {revenue_surprise:+.1f}%.")
    if not matched_terms and eps_surprise is None and revenue_surprise is None:
        parts.append("Το αποτέλεσμα παραμένει ουδέτερο λόγω περιορισμένων event δεδομένων.")

    return {
        "event_impact_score": round(score, 2),
        "event_impact_label": _label(score),
        "event_impact_confidence": confidence,
        "event_impact_summary": " ".join(parts),
        "event_impact_source": "rules_fallback",
        "earnings_eps_surprise_pct": None if eps_surprise is None else round(eps_surprise, 2),
        "earnings_revenue_surprise_pct": None if revenue_surprise is None else round(revenue_surprise, 2),
    }


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


def _parse_json(text):
    raw = str(text or "").strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    try:
        data = json.loads(raw)
    except Exception:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return {}
        try:
            data = json.loads(raw[start:end + 1])
        except Exception:
            return {}
    return data if isinstance(data, dict) else {}


def _public_event_context(row):
    headlines = []
    for item in (row.get("news_headlines") or [])[:4]:
        if not isinstance(item, dict):
            continue
        headlines.append({
            "title": item.get("title"),
            "published_at": item.get("published_at"),
            "summary": item.get("summary"),
        })
    return {
        "symbol": row.get("symbol"),
        "name": row.get("name"),
        "sector": row.get("sector"),
        "news": headlines,
        "earnings_date": row.get("earnings_date"),
        "eps_estimate": row.get("earnings_eps_estimate"),
        "eps_actual": row.get("earnings_eps_actual"),
        "revenue_estimate": row.get("earnings_revenue_estimate"),
        "revenue_actual": row.get("earnings_revenue_actual"),
    }


def _call_openai(rows):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key or os.getenv("AI_EVENT_IMPACT_ENABLED", "1").lower() in {"0", "false", "no"}:
        return {}

    prompt = (
        "Αξιολόγησε ΜΟΝΟ τα παρεχόμενα news/earnings δεδομένα για κάθε μετοχή. "
        "Μην χρησιμοποιήσεις εξωτερικά γεγονότα και μην εφεύρεις πληροφορίες. "
        "Δώσε impact_score από -100 έως +100 για τον πιθανό βραχυπρόθεσμο επιχειρηματικό/επενδυτικό αντίκτυπο, "
        "label positive/neutral/negative, confidence low/medium/high και summary 25-55 λέξεις στα ελληνικά. "
        "Αν τα δεδομένα είναι ανεπαρκή, score 0 και low confidence. "
        "Επέστρεψε ΜΟΝΟ JSON object της μορφής "
        "{\"SYMBOL\":{\"score\":0,\"label\":\"neutral\",\"confidence\":\"low\",\"summary\":\"...\"}}.\n\nDATA:\n"
        + json.dumps([_public_event_context(row) for row in rows], ensure_ascii=False, default=str)
    )
    body = {
        "model": os.getenv("OPENAI_MODEL", DEFAULT_MODEL),
        "input": prompt,
        "max_output_tokens": max(900, 220 * len(rows)),
    }
    with httpx.Client(timeout=90.0) as client:
        response = client.post(
            OPENAI_RESPONSES_URL,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
        response.raise_for_status()
        return _parse_json(_extract_output_text(response.json()))


def enrich_event_impact(rows, batch_size=10):
    result = [dict(row) for row in rows or []]
    if not result:
        return result

    for row in result:
        row.update(build_rule_event_impact(row))

    if not os.getenv("OPENAI_API_KEY"):
        return result

    size = max(1, int(batch_size))
    halted_error = None
    for start in range(0, len(result), size):
        chunk = result[start:start + size]
        if halted_error:
            for row in chunk:
                row["event_impact_error"] = halted_error
            continue
        try:
            generated = _call_openai(chunk)
        except Exception as error:
            message = str(error)[:300]
            for row in chunk:
                row["event_impact_error"] = message
            if "429" in message or "Too Many Requests" in message:
                halted_error = message
            continue

        for row in chunk:
            symbol = str(row.get("symbol") or "").strip()
            item = generated.get(symbol) or generated.get(symbol.upper())
            if not isinstance(item, dict):
                continue
            score = _safe_float(item.get("score"))
            summary = item.get("summary")
            if score is None or not isinstance(summary, str) or len(summary.strip()) < 10:
                continue
            row["event_impact_score"] = round(_clamp(score), 2)
            row["event_impact_label"] = str(item.get("label") or _label(score)).strip().lower()
            row["event_impact_confidence"] = str(item.get("confidence") or "medium").strip().lower()
            row["event_impact_summary"] = summary.strip()
            row["event_impact_source"] = f"OpenAI/{os.getenv('OPENAI_MODEL', DEFAULT_MODEL)}"
    return result
