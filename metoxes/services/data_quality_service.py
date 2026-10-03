
from __future__ import annotations

import json
import math
from datetime import date, datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2]
QUALITY_REPORT_FILE = BASE_DIR / "portfolio_quality_report.json"


def _to_float(value):
    if value in (None, ""):
        return None
    try:
        value = float(value)
        if math.isfinite(value):
            return value
    except (TypeError, ValueError):
        pass
    return None


def _to_date(value):
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value).strip()

    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def _issue(code, severity, message, field=None, actual=None, expected=None):
    return {
        "code": code,
        "severity": severity,
        "field": field,
        "message": message,
        "actual": actual,
        "expected": expected,
    }


def check_stock_quality(stock, today=None):
    today = today or date.today()

    if isinstance(today, datetime):
        today = today.date()

    issues = []

    symbol = str(stock.get("symbol") or "").strip()
    platform = str(stock.get("platform") or "").strip()

    if not symbol:
        issues.append(
            _issue(
                "missing_symbol",
                "error",
                "Λείπει symbol.",
                "symbol",
            )
        )

    if not platform:
        issues.append(
            _issue(
                "missing_platform",
                "warning",
                "Λείπει platform.",
                "platform",
            )
        )

    purchase_price = _to_float(stock.get("purchase_price"))
    quantity = _to_float(stock.get("quantity"))
    current_price = _to_float(stock.get("current_price"))
    market_value = _to_float(stock.get("market_value"))
    percent_change = _to_float(stock.get("percent_change"))
    monthly_change = _to_float(stock.get("monthly_percent_change"))
    purchase_date = _to_date(stock.get("purchase_date"))

    required_numeric = {
        "purchase_price": purchase_price,
        "quantity": quantity,
        "current_price": current_price,
        "market_value": market_value,
    }

    for field, value in required_numeric.items():
        if value is None:
            issues.append(
                _issue(
                    f"missing_{field}",
                    "error",
                    f"Λείπει ή δεν είναι αριθμός το {field}.",
                    field,
                    stock.get(field),
                )
            )

    for field in ("purchase_price", "quantity", "current_price"):
        value = required_numeric[field]
        if value is not None and value <= 0:
            issues.append(
                _issue(
                    f"non_positive_{field}",
                    "error",
                    f"Το {field} πρέπει να είναι > 0.",
                    field,
                    value,
                )
            )

    if market_value is not None and market_value < 0:
        issues.append(
            _issue(
                "negative_market_value",
                "error",
                "Το market_value δεν μπορεί να είναι αρνητικό.",
                "market_value",
                market_value,
            )
        )

    if stock.get("purchase_date") in (None, ""):
        issues.append(
            _issue(
                "missing_purchase_date",
                "warning",
                "Λείπει purchase_date.",
                "purchase_date",
            )
        )
    elif purchase_date is None:
        issues.append(
            _issue(
                "invalid_purchase_date",
                "error",
                "Η purchase_date δεν αναγνωρίζεται ως ημερομηνία.",
                "purchase_date",
                stock.get("purchase_date"),
            )
        )
    elif purchase_date > today:
        issues.append(
            _issue(
                "future_purchase_date",
                "error",
                "Η purchase_date είναι στο μέλλον.",
                "purchase_date",
                purchase_date.isoformat(),
            )
        )

    if (
        current_price is not None
        and quantity is not None
        and market_value is not None
        and current_price > 0
        and quantity > 0
    ):
        expected_mv = current_price * quantity
        tolerance = max(2.0, abs(expected_mv) * 0.03)

        if abs(market_value - expected_mv) > tolerance:
            issues.append(
                _issue(
                    "market_value_mismatch",
                    "warning",
                    "Το market_value αποκλίνει >3% από current_price × quantity.",
                    "market_value",
                    round(market_value, 4),
                    round(expected_mv, 4),
                )
            )

    calculated_change = None

    if (
        purchase_price is not None
        and current_price is not None
        and purchase_price > 0
    ):
        calculated_change = (
            current_price / purchase_price - 1
        ) * 100

        if (
            percent_change is not None
            and abs(percent_change - calculated_change) > 2.0
        ):
            issues.append(
                _issue(
                    "percent_change_mismatch",
                    "warning",
                    "Το percent_change δεν συμφωνεί με purchase_price/current_price.",
                    "percent_change",
                    round(percent_change, 2),
                    round(calculated_change, 2),
                )
            )

    if percent_change is not None:
        if percent_change > 150 or percent_change < -80:
            # Μεγάλη απόδοση από μόνη της δεν είναι σφάλμα.
            # Αν purchase_price/current_price δεν συμφωνούν,
            # το percent_change_mismatch πιο πάνω παραμένει WARNING.
            #
            # Όταν όμως ο υπολογισμός είναι μαθηματικά συνεπής
            # (όπως TSM και MOH.GR), το extreme return είναι INFO.
            return_is_consistent = (
                calculated_change is not None
                and abs(
                    percent_change
                    - calculated_change
                ) <= 2.0
            )

            severity = (
                "info"
                if return_is_consistent
                else "warning"
            )

            message = (
                "Πολύ μεγάλη συνολική απόδοση, αλλά συμφωνεί "
                "με purchase_price/current_price."
                if return_is_consistent
                else
                "Ακραία συνολική απόδοση με πιθανή ασυνέπεια. "
                "Έλεγξε split, purchase_price και ticker mapping."
            )

            issues.append(
                _issue(
                    "extreme_return",
                    severity,
                    message,
                    "percent_change",
                    round(percent_change, 2),
                    (
                        round(calculated_change, 2)
                        if calculated_change is not None
                        else None
                    ),
                )
            )

    holding_days = None
    if purchase_date is not None:
        holding_days = (today - purchase_date).days

    if (
        holding_days is not None
        and 0 <= holding_days <= 60
        and percent_change is not None
        and monthly_change is not None
        and abs(percent_change - monthly_change) >= 40
    ):
        # Το total return από την ημερομηνία αγοράς
        # και το 1M return δεν έχουν το ίδιο χρονικό διάστημα.
        # Μεγάλη διαφορά μεταξύ τους δεν σημαίνει απαραίτητα
        # πρόβλημα δεδομένων.
        #
        # Αν purchase/current/percent_change συμφωνούν,
        # το κρατάμε ως INFO. Αν δεν συμφωνούν, μένει WARNING.
        return_is_consistent = (
            calculated_change is not None
            and abs(
                percent_change
                - calculated_change
            ) <= 2.0
        )

        severity = (
            "info"
            if return_is_consistent
            else "warning"
        )

        message = (
            "Πρόσφατη θέση με μεγάλη διαφορά μεταξύ total return "
            "και 1M return, αλλά το total return συμφωνεί με "
            "purchase_price/current_price."
            if return_is_consistent
            else
            "Πρόσφατη θέση με μεγάλη απόκλιση total return από "
            "1M return και πιθανή ασυνέπεια στα δεδομένα."
        )

        issues.append(
            _issue(
                "recent_return_anomaly",
                severity,
                message,
                "percent_change",
                round(percent_change, 2),
                round(monthly_change, 2),
            )
        )

    if (
        purchase_price is not None
        and current_price is not None
        and purchase_price > 0
        and current_price > 0
    ):
        ratio = current_price / purchase_price
        split_factors = (
            2, 3, 4, 5, 10,
            1 / 2, 1 / 3, 1 / 4, 1 / 5, 1 / 10,
        )

        nearest = min(
            split_factors,
            key=lambda x: abs(ratio - x) / x
        )

        relative_error = abs(ratio - nearest) / nearest

        # Ratio κοντά σε 2x/3x/4x από μόνο του
        # δεν σημαίνει split. Η μετοχή μπορεί απλώς
        # να έχει αυξηθεί πολύ σε τιμή.
        return_mismatch = (
            calculated_change is not None
            and percent_change is not None
            and abs(
                percent_change
                - calculated_change
            ) > 20
        )

        if (
            relative_error <= 0.04
            and percent_change is not None
            and abs(percent_change) >= 40
            and return_mismatch
        ):
            issues.append(
                _issue(
                    "possible_stock_split",
                    "warning",
                    "Η αναλογία current_price/purchase_price είναι κοντά σε συνηθισμένο split factor. Θέλει επιβεβαίωση.",
                    "price_ratio",
                    round(ratio, 4),
                    round(nearest, 4),
                )
            )

    missing_fundamentals = [
        field
        for field in ("fcf_yield", "fcf_growth", "roic", "final_score")
        if stock.get(field) in (None, "")
    ]

    if missing_fundamentals:
        issues.append(
            _issue(
                "missing_fundamentals",
                "info",
                "Λείπουν ορισμένα fundamentals.",
                "fundamentals",
                missing_fundamentals,
            )
        )

    return issues


def run_portfolio_quality_checks(stocks, today=None):
    results = []
    total_errors = 0
    total_warnings = 0
    total_info = 0

    for stock in stocks:
        issues = check_stock_quality(
            stock,
            today=today,
        )

        if not issues:
            continue

        error_count = sum(
            1 for x in issues
            if x["severity"] == "error"
        )
        warning_count = sum(
            1 for x in issues
            if x["severity"] == "warning"
        )
        info_count = sum(
            1 for x in issues
            if x["severity"] == "info"
        )

        total_errors += error_count
        total_warnings += warning_count
        total_info += info_count

        results.append({
            "symbol": stock.get("symbol"),
            "platform": stock.get("platform"),
            "errors": error_count,
            "warnings": warning_count,
            "info": info_count,
            "issues": issues,
        })

    status = "OK"

    if total_errors:
        status = "ERROR"
    elif total_warnings:
        status = "WARNING"

    return {
        "status": status,
        "positions_checked": len(stocks),
        "positions_with_issues": len(results),
        "errors": total_errors,
        "warnings": total_warnings,
        "info": total_info,
        "stocks": results,
    }


def save_quality_report(
    report,
    path=QUALITY_REPORT_FILE,
):
    path = Path(path)

    path.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )

    return path
