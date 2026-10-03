from __future__ import annotations

"""Independent fundamentals cross-checks.

Primary portfolio fundamentals currently come from Yahoo/yfinance.  This
module adds an independent source without replacing the primary figures:

* FMP (Financial Modeling Prep) when FMP_API_KEY is configured.
* SEC EDGAR companyfacts as a key-free fallback for US issuers.

The output is deliberately diagnostic.  The normal equity score is not
silently overwritten by a second provider; discrepancies are surfaced to the
anomaly/AI layer instead.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import os
from pathlib import Path
import threading
import time

import httpx


FMP_BASE_URL = "https://financialmodelingprep.com/stable"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_COMPANYFACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CACHE_TTL_SECONDS = 12 * 60 * 60
BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_FILE = BASE_DIR / "secondary_fundamentals_cache.json"

_CACHE_LOCK = threading.Lock()
_SEC_TICKER_MAP = None


def _safe_float(value):
    if value in (None, ""):
        return None
    if isinstance(value, dict):
        value = value.get("raw", value.get("value"))
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _percent(value):
    number = _safe_float(value)
    if number is None:
        return None
    # Some providers return ratios as 0.14, others already as 14.
    if -2 <= number <= 2:
        return number * 100
    return number


def _normalize_symbol(symbol):
    value = str(symbol or "").strip().upper()
    for suffix in (".US", ".L", ".DE", ".PA", ".AS", ".MC", ".MI", ".ST", ".AT"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
            break
    return value


def _load_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(cache):
    try:
        CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


def _cache_get(key):
    cache = _load_cache()
    item = cache.get(key)
    if not isinstance(item, dict):
        return None
    saved_at = _safe_float(item.get("saved_at"))
    if saved_at is None or time.time() - saved_at > CACHE_TTL_SECONDS:
        return None
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_put(key, payload):
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[key] = {"saved_at": time.time(), "payload": payload}
        _save_cache(cache)


def _fmp_get(endpoint, params):
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return None
    query = dict(params or {})
    query["apikey"] = api_key
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        response = client.get(f"{FMP_BASE_URL}/{endpoint.lstrip('/')}", params=query)
        response.raise_for_status()
        return response.json()


def _first_record(payload):
    if isinstance(payload, list):
        return payload[0] if payload else {}
    if isinstance(payload, dict):
        return payload
    return {}


def _first_number(mapping, *keys):
    for key in keys:
        if key in mapping:
            number = _safe_float(mapping.get(key))
            if number is not None:
                return number
    return None


def _fetch_fmp(symbol):
    if not os.getenv("FMP_API_KEY"):
        return None

    cache_key = f"fmp:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    # One independent FMP request per symbol keeps a full portfolio refresh
    # comfortably below common personal-plan call limits. Key Metrics TTM
    # contains the cross-check metrics we need (FCF yield, ROIC, ROE).
    metrics = _first_record(_fmp_get("key-metrics-ttm", {"symbol": symbol}) or [])

    if not metrics:
        return None

    fcf_yield = _first_number(
        metrics,
        "freeCashFlowYieldTTM",
        "freeCashFlowYield",
        "fcfYieldTTM",
    )
    roic = _first_number(
        metrics,
        "returnOnInvestedCapitalTTM",
        "returnOnInvestedCapital",
        "roicTTM",
    )
    roe = _first_number(
        metrics,
        "returnOnEquityTTM",
        "returnOnEquity",
    )
    price_to_book = _first_number(
        metrics,
        "priceToBookRatioTTM",
        "priceToBookRatio",
    )

    result = {
        "secondary_source": "FMP",
        "secondary_status": "ok",
        "secondary_fcf_yield": _percent(fcf_yield),
        "secondary_roic": _percent(roic),
        "secondary_roe": _percent(roe),
        "secondary_price_to_book": price_to_book,
        "secondary_fcf_ttm": None,
        "secondary_operating_cash_flow_ttm": None,
        "secondary_revenue_ttm": None,
        "secondary_net_income_ttm": None,
        "secondary_checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    _cache_put(cache_key, result)
    return result


def _sec_headers():
    identity = os.getenv(
        "SEC_USER_AGENT",
        "METOXES2 personal portfolio analytics contact@example.com",
    )
    return {"User-Agent": identity, "Accept-Encoding": "gzip, deflate"}


def _sec_ticker_map():
    global _SEC_TICKER_MAP
    if _SEC_TICKER_MAP is not None:
        return _SEC_TICKER_MAP

    with httpx.Client(timeout=18.0, headers=_sec_headers(), follow_redirects=True) as client:
        response = client.get(SEC_TICKERS_URL)
        response.raise_for_status()
        payload = response.json()

    mapping = {}
    values = payload.values() if isinstance(payload, dict) else payload
    for item in values or []:
        if not isinstance(item, dict):
            continue
        ticker = str(item.get("ticker") or "").strip().upper()
        cik = item.get("cik_str")
        if ticker and cik is not None:
            mapping[ticker] = str(int(cik)).zfill(10)

    _SEC_TICKER_MAP = mapping
    return mapping


def _fact_units(companyfacts, concepts):
    facts = (companyfacts or {}).get("facts", {}).get("us-gaap", {})
    for concept in concepts:
        item = facts.get(concept)
        if not isinstance(item, dict):
            continue
        units = item.get("units") or {}
        for unit_name in ("USD", "shares", "USD/shares", "pure"):
            entries = units.get(unit_name)
            if isinstance(entries, list) and entries:
                return entries
        for entries in units.values():
            if isinstance(entries, list) and entries:
                return entries
    return []


def _latest_instant(entries):
    candidates = []
    for item in entries or []:
        value = _safe_float(item.get("val"))
        end = item.get("end")
        if value is None or not end:
            continue
        form = str(item.get("form") or "")
        if form not in {"10-K", "10-Q", "20-F", "40-F"}:
            continue
        candidates.append((end, value))
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def _ttm_sum(entries):
    records = []
    seen = set()
    for item in entries or []:
        value = _safe_float(item.get("val"))
        start = item.get("start")
        end = item.get("end")
        fp = str(item.get("fp") or "")
        form = str(item.get("form") or "")
        if value is None or not start or not end:
            continue
        if form not in {"10-K", "10-Q", "20-F", "40-F"}:
            continue
        # Prefer quarter-like observations; annual values would double-count TTM.
        try:
            days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days
        except Exception:
            days = 999
        if days > 150 and fp != "Q4":
            continue
        key = (start, end, value)
        if key in seen:
            continue
        seen.add(key)
        records.append((end, value))

    if not records:
        return None
    records.sort(key=lambda pair: pair[0], reverse=True)
    latest_four = records[:4]
    if len(latest_four) < 3:
        return None
    return sum(value for _, value in latest_four)


def _fetch_sec(symbol, country):
    if str(country or "").strip() != "United States":
        return None

    base = _normalize_symbol(symbol)
    cache_key = f"sec:{base}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    cik = _sec_ticker_map().get(base)
    if not cik:
        return None

    with httpx.Client(timeout=20.0, headers=_sec_headers(), follow_redirects=True) as client:
        response = client.get(SEC_COMPANYFACTS_URL.format(cik=cik))
        response.raise_for_status()
        facts = response.json()

    revenue = _ttm_sum(_fact_units(facts, ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet")))
    net_income = _ttm_sum(_fact_units(facts, ("NetIncomeLoss",)))
    operating_cf = _ttm_sum(_fact_units(facts, ("NetCashProvidedByUsedInOperatingActivities",)))
    capex = _ttm_sum(_fact_units(facts, ("PaymentsToAcquirePropertyPlantAndEquipment", "PaymentsForAdditionsToPropertyPlantAndEquipment")))
    equity = _latest_instant(_fact_units(facts, ("StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest")))

    fcf = None
    if operating_cf is not None and capex is not None:
        fcf = operating_cf - abs(capex)

    roe = None
    if net_income is not None and equity not in (None, 0):
        roe = net_income / equity * 100

    result = {
        "secondary_source": "SEC EDGAR",
        "secondary_status": "ok",
        "secondary_fcf_yield": None,
        "secondary_roic": None,
        "secondary_roe": roe,
        "secondary_price_to_book": None,
        "secondary_fcf_ttm": fcf,
        "secondary_operating_cash_flow_ttm": operating_cf,
        "secondary_revenue_ttm": revenue,
        "secondary_net_income_ttm": net_income,
        "secondary_checked_at": datetime.now().isoformat(timespec="seconds"),
        "secondary_cik": cik,
    }
    _cache_put(cache_key, result)
    return result


def _relative_difference(a, b):
    x = _safe_float(a)
    y = _safe_float(b)
    if x is None or y is None:
        return None
    denom = max(abs(x), abs(y), 1e-9)
    return abs(x - y) / denom * 100


def _crosscheck(primary, secondary):
    comparisons = []
    for primary_field, secondary_field in (
        ("fcf_yield", "secondary_fcf_yield"),
        ("roic", "secondary_roic"),
    ):
        diff = _relative_difference(primary.get(primary_field), secondary.get(secondary_field))
        if diff is not None:
            comparisons.append(diff)

    max_diff = max(comparisons) if comparisons else None
    if max_diff is None:
        status = "available_not_comparable"
    elif max_diff >= 50:
        status = "large_difference"
    elif max_diff >= 25:
        status = "moderate_difference"
    else:
        status = "consistent"

    return status, max_diff


def fetch_secondary_fundamentals(row):
    symbol = str(row.get("symbol") or "").strip()
    country = row.get("country")
    if not symbol:
        return {
            "secondary_source": None,
            "secondary_status": "missing_symbol",
        }

    provider_symbol = symbol
    if str(row.get("platform") or "").strip().lower() == "freedom24":
        try:
            from metoxes.services.freedom_service import FREEDOM_TICKER_MAP
            provider_symbol = FREEDOM_TICKER_MAP.get(symbol, symbol)
        except Exception:
            provider_symbol = symbol

    # FMP gives broad US/Europe coverage when configured.
    try:
        fmp = _fetch_fmp(provider_symbol)
    except Exception as error:
        fmp = None
        fmp_error = str(error)
    else:
        fmp_error = None

    if fmp:
        result = dict(fmp)
    else:
        try:
            sec = _fetch_sec(provider_symbol, country)
        except Exception as error:
            sec = None
            sec_error = str(error)
        else:
            sec_error = None

        if sec:
            result = dict(sec)
        else:
            result = {
                "secondary_source": None,
                "secondary_status": "unavailable",
            }
            errors = [value for value in (fmp_error, sec_error) if value]
            if errors:
                result["secondary_error"] = " | ".join(errors)[:500]
            elif not os.getenv("FMP_API_KEY") and str(country or "") != "United States":
                result["secondary_status"] = "fmp_key_required_for_non_us"

    status, max_diff = _crosscheck(row, result)
    result["fundamental_crosscheck_status"] = status
    result["fundamental_discrepancy_pct"] = (
        round(max_diff, 2) if max_diff is not None else None
    )
    return result


def enrich_with_secondary_fundamentals(rows, workers=5):
    result = [dict(row) for row in rows or []]
    if not result:
        return result

    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {
            executor.submit(fetch_secondary_fundamentals, row): index
            for index, row in enumerate(result)
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                payload = future.result()
            except Exception as error:
                payload = {
                    "secondary_source": None,
                    "secondary_status": "error",
                    "secondary_error": str(error)[:500],
                    "fundamental_crosscheck_status": "unavailable",
                    "fundamental_discrepancy_pct": None,
                }
            result[index].update(payload)

    return result
