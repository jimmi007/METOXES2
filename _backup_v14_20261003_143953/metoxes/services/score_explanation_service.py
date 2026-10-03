from __future__ import annotations

"""Human-readable, deterministic explanations for Final Score.

This module deliberately does not expose the hidden relative/absolute score
numbers. It turns the same inputs that feed scoring into user-facing drivers,
risks, missing-data notes and source-validation context.
"""

import math


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


def _impact_from_component(score):
    number = _safe_float(score)
    if number is None:
        return None
    if number >= 75:
        return "ισχυρό θετικό"
    if number >= 55:
        return "θετικό"
    if number >= 40:
        return "ουδέτερο"
    if number >= 20:
        return "αρνητικό"
    return "ισχυρό αρνητικό"


def _general_metric_rows(row):
    return [
        ("FCF Yield", "fcf_yield", "fcf_yield_score", "αποτίμηση/παραγωγή ελεύθερων ταμειακών ροών"),
        ("ROIC", "roic", "roic_score", "αποδοτικότητα του επενδεδυμένου κεφαλαίου"),
        ("FCF Growth", "fcf_growth", "fcf_growth_score", "ρυθμός μεταβολής ελεύθερων ταμειακών ροών"),
        ("Forward Revenue", "forward_revenue_growth", "forward_revenue_growth_score", "προσδοκώμενη ανάπτυξη εσόδων"),
        ("Forward EPS", "forward_eps_growth", "forward_eps_growth_score", "προσδοκώμενη ανάπτυξη κερδών ανά μετοχή"),
    ]


def _financial_metric_rows(row):
    return [
        ("ROE", "financial_roe", "financial_roe_relative_score", "απόδοση ιδίων κεφαλαίων"),
        ("Price/Book", "financial_price_to_book", "financial_price_to_book_relative_score", "αποτίμηση έναντι λογιστικής αξίας"),
        ("Profit Margin", "financial_profit_margin", "financial_profit_margin_relative_score", "κερδοφορία"),
        ("Revenue Growth", "financial_revenue_growth", "financial_revenue_growth_relative_score", "ανάπτυξη εσόδων"),
        ("Forward EPS", "financial_forward_eps_growth", "financial_forward_eps_growth_relative_score", "προσδοκώμενη ανάπτυξη EPS"),
    ]


def _crosscheck_text(row):
    source = row.get("secondary_source")
    status = str(row.get("fundamental_crosscheck_status") or "")
    discrepancy = _safe_float(row.get("fundamental_discrepancy_pct"))

    if not source:
        return "Δεν υπάρχει διαθέσιμη δεύτερη πηγή fundamentals για ουσιαστική διασταύρωση."

    pieces = [f"Δεύτερη πηγή: {source}."]
    if status == "consistent":
        pieces.append("Οι συγκρίσιμες τιμές συμφωνούν σε ικανοποιητικό βαθμό.")
    elif status == "moderate_difference":
        pieces.append("Υπάρχει μέτρια απόκλιση από την κύρια πηγή και χρειάζεται προσοχή.")
    elif status == "large_difference":
        pieces.append("Υπάρχει μεγάλη απόκλιση από την κύρια πηγή· το score χρειάζεται αυξημένο έλεγχο.")
    elif status == "available_not_comparable":
        pieces.append("Υπάρχουν ανεξάρτητα στοιχεία, αλλά όχι αρκετά ίδια πεδία για αριθμητική σύγκριση.")

    if discrepancy is not None:
        pieces.append(f"Μέγιστη σχετική απόκλιση: {discrepancy:.2f}%.")

    if source == "FMP":
        fcf = _safe_float(row.get("secondary_fcf_yield"))
        roic = _safe_float(row.get("secondary_roic"))
        roe = _safe_float(row.get("secondary_roe"))
        pb = _safe_float(row.get("secondary_price_to_book"))
        values = []
        if fcf is not None:
            values.append(f"FCF Yield {_fmt(fcf)}")
        if roic is not None:
            values.append(f"ROIC {_fmt(roic)}")
        if roe is not None:
            values.append(f"ROE {_fmt(roe)}")
        if pb is not None:
            values.append(f"P/B {_fmt(pb, '')}")
        if values:
            pieces.append("FMP TTM: " + ", ".join(values) + ".")

    return " ".join(pieces)


def _metric_explanations(row, financial=False):
    metrics = _financial_metric_rows(row) if financial else _general_metric_rows(row)
    details = []
    positives = []
    risks = []
    missing = []

    for label, value_field, component_field, meaning in metrics:
        value = _safe_float(row.get(value_field))
        if value is None:
            missing.append(label)
            continue

        impact = _impact_from_component(row.get(component_field))
        if impact is None:
            # Absolute-value fallback if a component rank is not present.
            if value_field in {"fcf_yield", "roic", "financial_roe", "financial_profit_margin"}:
                impact = "θετικό" if value >= 10 else "ουδέτερο" if value >= 5 else "αρνητικό"
            elif value_field == "financial_price_to_book":
                impact = "θετικό" if 0 < value <= 1.5 else "ουδέτερο" if value <= 2.5 else "αρνητικό"
            else:
                impact = "θετικό" if value >= 10 else "ουδέτερο" if value >= 0 else "αρνητικό"

        suffix = "" if value_field == "financial_price_to_book" else "%"
        sentence = f"{label} {_fmt(value, suffix)}: {impact} — {meaning}."
        details.append({"metric": label, "value": value, "impact": impact, "text": sentence})

        if "θετικό" in impact:
            positives.append(sentence)
        elif "αρνητικό" in impact:
            risks.append(sentence)

    return details, positives, risks, missing


def build_score_explanation(row):
    financial = bool(row.get("financial_model"))
    score = _safe_float(row.get("final_score"))
    details, positives, risks, missing = _metric_explanations(row, financial=financial)

    if score is None:
        headline = "Δεν υπάρχει επαρκές Final Score λόγω ελλιπών scoring δεδομένων."
    elif score >= 80:
        headline = "Το Final Score είναι υψηλό επειδή οι περισσότεροι βασικοί παράγοντες είναι ισχυροί."
    elif score >= 65:
        headline = "Το Final Score είναι καλό, με περισσότερους θετικούς από αρνητικούς παράγοντες."
    elif score >= 50:
        headline = "Το Final Score είναι μικτό: υπάρχουν θετικά στοιχεία αλλά και ουσιαστικοί περιορισμοί."
    else:
        headline = "Το Final Score πιέζεται από αδύναμους ή αρνητικούς βασικούς παράγοντες."

    if financial:
        model_text = (
            "Χρησιμοποιείται το ειδικό Financial Services μοντέλο: ROE, Price/Book, Profit Margin, "
            "Revenue Growth και Forward EPS Growth. Το γενικό FCF/ROIC μοντέλο δεν είναι ο αποφασιστικός μηχανισμός."
        )
    else:
        model_text = (
            "Το γενικό μοντέλο αξιολογεί FCF Yield, FCF Growth, ROIC και forward ανάπτυξη. "
            "Το Final Score συνδυάζει εσωτερικά σχετική εικόνα έναντι peers και απόλυτη ποιότητα, χωρίς να εμφανίζονται οι δύο επιμέρους βαθμοί."
        )

    cross = _crosscheck_text(row)
    anomaly = row.get("anomaly_summary") or "Δεν εντοπίστηκε anomaly που να απαιτεί ειδική προειδοποίηση."

    drivers = positives[:3]
    weaknesses = risks[:3]
    if not drivers and details:
        drivers = [details[0]["text"]]
    if not weaknesses and missing:
        weaknesses = ["Λείπουν δεδομένα για: " + ", ".join(missing) + "."]

    text_parts = [headline, model_text]
    if drivers:
        text_parts.append("Θετικοί οδηγοί: " + " ".join(drivers))
    if weaknesses:
        text_parts.append("Αδύνατα σημεία/κίνδυνοι: " + " ".join(weaknesses))
    if missing:
        text_parts.append("Ελλιπή πεδία: " + ", ".join(missing) + ".")
    text_parts.append(cross)
    text_parts.append("Έλεγχος δεδομένων: " + anomaly)

    return {
        "score_rationale_headline": headline,
        "score_rationale_text": " ".join(text_parts),
        "score_drivers": drivers,
        "score_weaknesses": weaknesses,
        "score_missing_metrics": missing,
        "score_metric_details": details,
        "score_crosscheck_text": cross,
        "score_model_label": "Financial Services" if financial else "General Fundamentals",
    }


def enrich_score_explanations(rows):
    result = [dict(row) for row in rows or []]
    for row in result:
        row.update(build_score_explanation(row))
    return result


def _relative_difference(a, b):
    x = _safe_float(a)
    y = _safe_float(b)
    if x is None or y is None:
        return None
    denom = max(abs(x), abs(y), 1e-9)
    return abs(x - y) / denom * 100


def reconcile_financial_crosschecks(rows):
    """Use ROE/P-B for Financial Services source validation.

    Generic companies remain cross-checked on FCF Yield/ROIC by the secondary
    fundamentals service. Banks/financials should not be judged on those
    generic metrics, so when FMP is available we compare the dedicated model
    inputs instead. This changes validation metadata only, never Final Score.
    """
    result = [dict(row) for row in rows or []]
    for row in result:
        if not row.get("financial_model") or row.get("secondary_source") != "FMP":
            continue

        diffs = []
        for primary_field, secondary_field in (
            ("financial_roe", "secondary_roe"),
            ("financial_price_to_book", "secondary_price_to_book"),
        ):
            diff = _relative_difference(row.get(primary_field), row.get(secondary_field))
            if diff is not None:
                diffs.append(diff)

        if not diffs:
            row["fundamental_crosscheck_status"] = "available_not_comparable"
            row["fundamental_discrepancy_pct"] = None
            row["financial_crosscheck_metrics"] = "ROE/P-B"
            continue

        max_diff = max(diffs)
        if max_diff >= 50:
            status = "large_difference"
        elif max_diff >= 25:
            status = "moderate_difference"
        else:
            status = "consistent"
        row["fundamental_crosscheck_status"] = status
        row["fundamental_discrepancy_pct"] = round(max_diff, 2)
        row["financial_crosscheck_metrics"] = "ROE/P-B"
    return result
