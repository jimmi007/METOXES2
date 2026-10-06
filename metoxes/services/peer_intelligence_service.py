from __future__ import annotations

"""Competitor-aware peer intelligence for METOXES2.

The live Final Score remains deterministic.  This module adds an explanatory
layer based on real peer tickers (FMP when configured) and an industry/sector
fallback from the rows already being analysed.

Nothing in this module silently changes ``final_score``.
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import math
import os
from pathlib import Path
import statistics
import threading
import time

import httpx


BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_FILE = BASE_DIR / "peer_intelligence_cache.json"
CACHE_TTL_SECONDS = 24 * 60 * 60
FMP_STABLE_BASE = "https://financialmodelingprep.com/stable"
FMP_V4_BASE = "https://financialmodelingprep.com/api/v4"
MAX_PEERS = 5
_CACHE_LOCK = threading.Lock()


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


def _pct(value):
    number = _safe_float(value)
    if number is None:
        return None
    if -2 <= number <= 2:
        return number * 100
    return number


def _normalize_symbol(symbol):
    return str(symbol or "").strip().upper()


def _provider_symbol(row):
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        return symbol
    if str(row.get("platform") or "").strip().lower() == "freedom24":
        try:
            from metoxes.services.freedom_service import FREEDOM_TICKER_MAP
            return FREEDOM_TICKER_MAP.get(symbol, symbol)
        except Exception:
            return symbol
    return symbol


def _load_cache():
    try:
        payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_cache(cache):
    try:
        CACHE_FILE.write_text(
            json.dumps(cache, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
    except Exception:
        pass


def _cache_get(key):
    item = _load_cache().get(key)
    if not isinstance(item, dict):
        return None
    try:
        age = time.time() - float(item.get("saved_at"))
    except Exception:
        return None
    if age > CACHE_TTL_SECONDS:
        return None
    payload = item.get("payload")
    return payload if isinstance(payload, dict) else None


def _cache_put(key, payload):
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[key] = {"saved_at": time.time(), "payload": payload}
        _save_cache(cache)


def _extract_peer_symbols(payload, target_symbol):
    target = _normalize_symbol(target_symbol)
    candidates = []

    def add(value):
        symbol = _normalize_symbol(value)
        if not symbol or symbol == target or symbol in candidates:
            return
        candidates.append(symbol)

    if isinstance(payload, dict):
        for key in ("peersList", "peers", "symbols", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        add(item.get("symbol") or item.get("ticker"))
                    else:
                        add(item)
        add(payload.get("symbol"))
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                nested = item.get("peersList") or item.get("peers")
                if isinstance(nested, list):
                    for value in nested:
                        add(value.get("symbol") if isinstance(value, dict) else value)
                else:
                    add(item.get("symbol") or item.get("ticker"))
            else:
                add(item)
    return candidates


def _fmp_peer_symbols(symbol):
    key = os.getenv("FMP_API_KEY")
    if not key or not symbol:
        return []

    attempts = [
        (f"{FMP_STABLE_BASE}/stock-peers", {"symbol": symbol, "apikey": key}),
        (f"{FMP_V4_BASE}/stock_peers", {"symbol": symbol, "apikey": key}),
    ]
    last_error = None
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        for url, params in attempts:
            try:
                response = client.get(url, params=params)
                response.raise_for_status()
                peers = _extract_peer_symbols(response.json(), symbol)
                if peers:
                    return peers
            except Exception as error:
                last_error = error
                continue
    if last_error:
        raise last_error
    return []


def _ticker_snapshot(symbol):
    """Small comparable metric snapshot from Yahoo/yfinance."""
    import yfinance as yf

    info = yf.Ticker(symbol).get_info() or {}
    market_cap = _safe_float(info.get("marketCap"))
    free_cash_flow = _safe_float(info.get("freeCashflow"))
    fcf_yield = None
    if market_cap not in (None, 0) and free_cash_flow is not None:
        fcf_yield = free_cash_flow / market_cap * 100

    roic = _pct(
        info.get("returnOnInvestedCapital")
        or info.get("returnOnCapital")
    )
    return {
        "symbol": symbol,
        "name": info.get("shortName") or info.get("longName") or symbol,
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "market_cap": market_cap,
        "fcf_yield": fcf_yield,
        "roic": roic,
        "forward_revenue_growth": _pct(info.get("revenueGrowth")),
        "forward_eps_growth": _pct(info.get("earningsGrowth")),
        "financial_roe": _pct(info.get("returnOnEquity")),
        "financial_price_to_book": _safe_float(info.get("priceToBook")),
        "financial_profit_margin": _pct(info.get("profitMargins")),
        "financial_revenue_growth": _pct(info.get("revenueGrowth")),
        "financial_forward_eps_growth": _pct(info.get("earningsGrowth")),
    }


def _median(rows, field):
    values = [_safe_float(row.get(field)) for row in rows]
    values = [value for value in values if value is not None]
    return statistics.median(values) if values else None


def _percentile(value, peers, higher_is_better=True):
    number = _safe_float(value)
    values = [_safe_float(x) for x in peers]
    values = [x for x in values if x is not None]
    if number is None or not values:
        return None
    pool = values + [number]
    if len(pool) <= 1:
        return 50.0
    if higher_is_better:
        lower = sum(1 for x in pool if x < number)
        equal = sum(1 for x in pool if x == number)
    else:
        lower = sum(1 for x in pool if x > number)
        equal = sum(1 for x in pool if x == number)
    average_index = lower + (equal - 1) / 2
    return round(average_index / (len(pool) - 1) * 100, 2)


def _peer_fields(row):
    if str(row.get("sector") or "").strip() == "Financial Services" or row.get("financial_model"):
        return [
            ("ROE", "financial_roe", True, "%"),
            ("P/B", "financial_price_to_book", False, ""),
            ("Profit Margin", "financial_profit_margin", True, "%"),
            ("Revenue Growth", "financial_revenue_growth", True, "%"),
            ("Forward EPS", "financial_forward_eps_growth", True, "%"),
        ]
    return [
        ("FCF Yield", "fcf_yield", True, "%"),
        ("ROIC", "roic", True, "%"),
        ("Forward Revenue", "forward_revenue_growth", True, "%"),
        ("Forward EPS", "forward_eps_growth", True, "%"),
    ]


def _fallback_peers(row, universe_rows, limit=MAX_PEERS):
    symbol = _normalize_symbol(row.get("symbol"))
    sector = str(row.get("sector") or "").strip()
    industry = str(row.get("industry") or row.get("financial_industry") or "").strip()
    country = str(row.get("country") or "").strip()

    candidates = []
    for item in universe_rows or []:
        if _normalize_symbol(item.get("symbol")) == symbol:
            continue
        score = 0
        item_industry = str(item.get("industry") or item.get("financial_industry") or "").strip()
        if industry and item_industry and industry.lower() == item_industry.lower():
            score += 4
        if sector and str(item.get("sector") or "").strip() == sector:
            score += 2
        if country and str(item.get("country") or "").strip() == country:
            score += 1
        if score >= 2:
            candidates.append((score, dict(item)))
    candidates.sort(key=lambda pair: (-pair[0], str(pair[1].get("symbol") or "")))
    return [item for _, item in candidates[:limit]]


def build_peer_intelligence(row, universe_rows=None, max_peers=MAX_PEERS, allow_network=True):
    result = dict(row)
    provider_symbol = _provider_symbol(result)
    cache_key = f"peer:{provider_symbol}:{max_peers}"
    cached = _cache_get(cache_key) if allow_network else None
    if cached is not None:
        result.update(cached)
        return result

    peer_rows = []
    peer_source = None
    peer_error = None

    # Target metadata is useful for fallback matching and dashboard context.
    if allow_network and provider_symbol:
        try:
            target_snapshot = _ticker_snapshot(provider_symbol)
            result.setdefault("industry", target_snapshot.get("industry"))
            for key, value in target_snapshot.items():
                if key not in {"symbol", "name"} and result.get(key) in (None, ""):
                    result[key] = value
        except Exception as error:
            peer_error = str(error)[:300]

    peer_symbols = []
    if allow_network and provider_symbol and os.getenv("FMP_API_KEY"):
        try:
            peer_symbols = _fmp_peer_symbols(provider_symbol)[: max(1, int(max_peers))]
            if peer_symbols:
                peer_source = "FMP stock peers + Yahoo metrics"
        except Exception as error:
            peer_error = str(error)[:300]

    if peer_symbols:
        with ThreadPoolExecutor(max_workers=min(4, len(peer_symbols))) as executor:
            futures = {executor.submit(_ticker_snapshot, symbol): symbol for symbol in peer_symbols}
            for future in as_completed(futures):
                try:
                    peer_rows.append(future.result())
                except Exception:
                    continue

    if not peer_rows:
        peer_rows = _fallback_peers(result, universe_rows or [], limit=max_peers)
        if peer_rows:
            peer_source = "industry/sector fallback from analysed universe"

    comparisons = []
    percentiles = []
    strengths = []
    weaknesses = []

    for label, field, higher_is_better, suffix in _peer_fields(result):
        own = _safe_float(result.get(field))
        median = _median(peer_rows, field)
        percentile = _percentile(own, [p.get(field) for p in peer_rows], higher_is_better)
        if own is None or median is None:
            continue
        percentiles.append(percentile) if percentile is not None else None
        gap = own - median
        if not higher_is_better:
            better = own < median
        else:
            better = own > median
        magnitude = abs(gap)
        comparison = {
            "metric": label,
            "field": field,
            "value": round(own, 4),
            "peer_median": round(median, 4),
            "difference": round(gap, 4),
            "percentile": percentile,
            "higher_is_better": higher_is_better,
        }
        comparisons.append(comparison)
        if percentile is not None and percentile >= 65:
            strengths.append(
                f"{label}: {own:.2f}{suffix} έναντι median peers {median:.2f}{suffix} (percentile {percentile:.0f})."
            )
        elif percentile is not None and percentile <= 35:
            weaknesses.append(
                f"{label}: {own:.2f}{suffix} έναντι median peers {median:.2f}{suffix} (percentile {percentile:.0f})."
            )

    quality_percentile = None
    valid_percentiles = [x for x in percentiles if x is not None]
    if valid_percentiles:
        quality_percentile = round(sum(valid_percentiles) / len(valid_percentiles), 2)

    if quality_percentile is None:
        label = "insufficient_data"
    elif quality_percentile >= 70:
        label = "peer_leader"
    elif quality_percentile >= 55:
        label = "above_peer_median"
    elif quality_percentile >= 45:
        label = "near_peer_median"
    elif quality_percentile >= 30:
        label = "below_peer_median"
    else:
        label = "peer_laggard"

    summary = (
        f"Σύγκριση με {len(peer_rows)} peers ({peer_source or 'μη διαθέσιμη πηγή'}): "
        f"{label.replace('_', ' ')}"
        + (f", μέσο peer percentile {quality_percentile:.1f}/100." if quality_percentile is not None else ".")
    )

    enrichment = {
        "peer_source": peer_source,
        "peer_symbols": [str(peer.get("symbol") or "") for peer in peer_rows if peer.get("symbol")],
        "peer_count": len(peer_rows),
        "peer_comparison": comparisons,
        "peer_quality_percentile": quality_percentile,
        "peer_advantage_label": label,
        "peer_strengths": strengths[:3],
        "peer_weaknesses": weaknesses[:3],
        "peer_summary": summary,
        "peer_checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    if peer_error:
        enrichment["peer_intelligence_error"] = peer_error

    result.update(enrichment)
    if allow_network:
        _cache_put(cache_key, enrichment)
    return result


def enrich_peer_intelligence(rows, workers=4, max_network_rows=20, max_peers=MAX_PEERS):
    """Enrich rows with competitor comparison.

    Network enrichment is capped by default to keep a normal portfolio refresh
    fast.  Rows outside that cap still receive an in-universe sector fallback.
    """
    result = [dict(row) for row in rows or []]
    if not result:
        return result

    ranked_indexes = list(range(len(result)))
    ranked_indexes.sort(
        key=lambda i: (
            _safe_float(result[i].get("portfolio_weight")) or 0,
            _safe_float(result[i].get("final_score")) or 0,
        ),
        reverse=True,
    )
    network_indexes = set(ranked_indexes[: max(0, int(max_network_rows))])

    # First provide cheap in-universe comparisons to every row.
    for i, row in enumerate(result):
        result[i] = build_peer_intelligence(
            row,
            universe_rows=result,
            max_peers=max_peers,
            allow_network=False,
        )

    if not network_indexes:
        return result

    with ThreadPoolExecutor(max_workers=max(1, min(int(workers), len(network_indexes)))) as executor:
        futures = {
            executor.submit(
                build_peer_intelligence,
                result[i],
                result,
                max_peers,
                True,
            ): i
            for i in network_indexes
        }
        for future in as_completed(futures):
            index = futures[future]
            try:
                result[index] = future.result()
            except Exception as error:
                result[index]["peer_intelligence_error"] = str(error)[:300]
    return result
