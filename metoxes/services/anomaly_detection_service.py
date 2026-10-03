from __future__ import annotations

from datetime import date, datetime
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


def _as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        text = value[:10]
        for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    return None


def detect_row_anomalies(row, today=None):
    today = today or date.today()
    flags = []

    def add(code, severity, message):
        flags.append({"code": code, "severity": severity, "message": message})

    current = _safe_float(row.get("current_price"))
    if current is not None and current <= 0:
        add("non_positive_price", "error", "Η τρέχουσα τιμή είναι μη θετική.")

    total_return = _safe_float(row.get("percent_change"))
    avg_month = _safe_float(row.get("avg_monthly_change"))
    one_month = _safe_float(row.get("monthly_percent_change"))

    if total_return is not None and (total_return > 400 or total_return < -95):
        add("extreme_total_return", "warning", f"Ακραία συνολική απόδοση {total_return:.2f}%.")

    if one_month is not None and abs(one_month) > 60:
        add("extreme_1m_return", "warning", f"Ακραία μηνιαία μεταβολή {one_month:.2f}%.")

    if total_return is not None and avg_month is not None:
        if abs(total_return) >= 1 and abs(avg_month) >= 0.1 and (total_return > 0) != (avg_month > 0):
            add("return_sign_mismatch", "error", "Το πρόσημο total return και average monthly return δεν συμφωνεί.")

    purchase_date = _as_date(row.get("purchase_date"))
    if purchase_date and purchase_date > today:
        add("future_purchase_date", "error", "Η ημερομηνία αγοράς βρίσκεται στο μέλλον.")

    for field, low, high in (
        ("fcf_yield", -25, 60),
        ("fcf_growth", -100, 500),
        ("roic", -60, 120),
        ("forward_revenue_growth", -100, 250),
        ("forward_eps_growth", -150, 400),
    ):
        value = _safe_float(row.get(field))
        if value is not None and (value < low or value > high):
            add(f"extreme_{field}", "warning", f"Ακραία τιμή {field}: {value:.2f}%.")

    score = _safe_float(row.get("final_score"))
    if score is not None and not 0 <= score <= 100:
        add("score_out_of_range", "error", f"Final score εκτός 0-100: {score:.2f}.")

    crosscheck = str(row.get("fundamental_crosscheck_status") or "")
    discrepancy = _safe_float(row.get("fundamental_discrepancy_pct"))
    if crosscheck == "large_difference" or (discrepancy is not None and discrepancy >= 50):
        add("fundamental_source_mismatch", "warning", "Μεγάλη απόκλιση μεταξύ κύριας και ανεξάρτητης πηγής fundamentals.")

    severity_order = {"info": 0, "warning": 1, "error": 2}
    max_severity = "none"
    if flags:
        max_severity = max(flags, key=lambda item: severity_order.get(item["severity"], 0))["severity"]

    return {
        "anomaly_flags": flags,
        "anomaly_count": len(flags),
        "anomaly_severity": max_severity,
        "anomaly_summary": " | ".join(flag["message"] for flag in flags[:4]) if flags else "",
    }


def detect_portfolio_anomalies(rows, today=None):
    result = [dict(row) for row in rows or []]
    counts = {"error": 0, "warning": 0, "info": 0}
    rows_with_anomalies = 0

    for row in result:
        payload = detect_row_anomalies(row, today=today)
        row.update(payload)
        if payload["anomaly_count"]:
            rows_with_anomalies += 1
        for flag in payload["anomaly_flags"]:
            severity = flag.get("severity")
            if severity in counts:
                counts[severity] += 1

    return {
        "stocks": result,
        "report": {
            "positions_with_anomalies": rows_with_anomalies,
            "errors": counts["error"],
            "warnings": counts["warning"],
            "info": counts["info"],
            "total_flags": sum(counts.values()),
        },
    }
