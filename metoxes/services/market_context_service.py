from __future__ import annotations

"""Recent company news and earnings context with short-lived local caching."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import threading
import time

import httpx


FMP_BASE_URL = "https://financialmodelingprep.com/stable"
BASE_DIR = Path(__file__).resolve().parents[2]
CACHE_FILE = BASE_DIR / "market_context_cache.json"
CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_LOCK = threading.Lock()

POSITIVE_WORDS = {"beat", "beats", "raises", "raised", "growth", "record", "upgrade", "strong", "profit", "surge", "wins"}
NEGATIVE_WORDS = {"miss", "misses", "cuts", "cut", "downgrade", "weak", "loss", "lawsuit", "probe", "decline", "warning"}


def _load_cache():
    try:
        data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _save_cache(cache):
    try:
        CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    except Exception:
        pass


def _cache_get(key):
    item = _load_cache().get(key)
    if not isinstance(item, dict):
        return None
    saved = item.get("saved_at")
    try:
        fresh = time.time() - float(saved) <= CACHE_TTL_SECONDS
    except Exception:
        fresh = False
    return item.get("payload") if fresh else None


def _cache_put(key, payload):
    with _CACHE_LOCK:
        cache = _load_cache()
        cache[key] = {"saved_at": time.time(), "payload": payload}
        _save_cache(cache)


def _sentiment(headlines):
    pos = neg = 0
    for headline in headlines or []:
        text = str(headline.get("title") or "").lower()
        words = set(text.replace("'", " ").replace("-", " ").split())
        pos += len(words & POSITIVE_WORDS)
        neg += len(words & NEGATIVE_WORDS)
    if pos > neg:
        return "positive"
    if neg > pos:
        return "negative"
    return "neutral"


def _fmp_context(symbol, max_news):
    key = os.getenv("FMP_API_KEY")
    enabled = os.getenv("FMP_NEWS_ENABLED", "0").lower() in {"1", "true", "yes"}
    if not key or not enabled:
        return None
    params = {"apikey": key}
    with httpx.Client(timeout=18.0, follow_redirects=True) as client:
        news_resp = client.get(
            f"{FMP_BASE_URL}/news/stock",
            params={"symbols": symbol, "page": 0, "limit": max_news, **params},
        )
        earnings_resp = client.get(
            f"{FMP_BASE_URL}/earnings",
            params={"symbol": symbol, **params},
        )
        news_resp.raise_for_status()
        earnings_resp.raise_for_status()
        news_payload = news_resp.json()
        earnings_payload = earnings_resp.json()

    headlines = []
    for item in (news_payload if isinstance(news_payload, list) else [])[:max_news]:
        headlines.append({
            "title": item.get("title"),
            "publisher": item.get("publisher") or item.get("site"),
            "published_at": item.get("publishedDate"),
            "url": item.get("url"),
            "summary": item.get("text"),
        })

    earnings = None
    if isinstance(earnings_payload, list) and earnings_payload:
        # Prefer the nearest future/most recent record by date.
        records = [x for x in earnings_payload if isinstance(x, dict)]
        records.sort(key=lambda x: str(x.get("date") or ""), reverse=True)
        earnings = records[0] if records else None

    return {
        "news_source": "FMP",
        "news_headlines": headlines,
        "news_sentiment": _sentiment(headlines),
        "earnings_source": "FMP",
        "earnings_date": (earnings or {}).get("date"),
        "earnings_eps_estimate": (earnings or {}).get("epsEstimated") or (earnings or {}).get("epsEstimate"),
        "earnings_eps_actual": (earnings or {}).get("epsActual") or (earnings or {}).get("eps"),
        "earnings_revenue_estimate": (earnings or {}).get("revenueEstimated") or (earnings or {}).get("revenueEstimate"),
        "earnings_revenue_actual": (earnings or {}).get("revenueActual") or (earnings or {}).get("revenue"),
    }


def _normalize_yahoo_news(raw, max_news):
    headlines = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        content = item.get("content") if isinstance(item.get("content"), dict) else item
        provider = content.get("provider") if isinstance(content.get("provider"), dict) else {}
        canonical = content.get("canonicalUrl") if isinstance(content.get("canonicalUrl"), dict) else {}
        title = content.get("title") or item.get("title")
        if not title:
            continue
        headlines.append({
            "title": title,
            "publisher": provider.get("displayName") or content.get("publisher") or item.get("publisher"),
            "published_at": content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime"),
            "url": canonical.get("url") or content.get("link") or item.get("link"),
            "summary": content.get("summary") or content.get("description"),
        })
        if len(headlines) >= max_news:
            break
    return headlines


def _extract_calendar_date(calendar):
    if calendar is None:
        return None
    if isinstance(calendar, dict):
        value = calendar.get("Earnings Date") or calendar.get("earningsDate")
        if isinstance(value, (list, tuple)) and value:
            value = value[0]
        return str(value) if value not in (None, "") else None
    try:
        # pandas DataFrame-like object
        if "Earnings Date" in calendar.index:
            value = calendar.loc["Earnings Date"].iloc[0]
            return str(value)
    except Exception:
        pass
    return None


def _yahoo_context(symbol, max_news):
    import yfinance as yf

    ticker = yf.Ticker(symbol)
    try:
        news = ticker.news or []
    except Exception:
        news = []
    try:
        calendar = ticker.calendar
    except Exception:
        calendar = None

    headlines = _normalize_yahoo_news(news, max_news)
    return {
        "news_source": "Yahoo Finance",
        "news_headlines": headlines,
        "news_sentiment": _sentiment(headlines),
        "earnings_source": "Yahoo Finance",
        "earnings_date": _extract_calendar_date(calendar),
        "earnings_eps_estimate": None,
        "earnings_eps_actual": None,
        "earnings_revenue_estimate": None,
        "earnings_revenue_actual": None,
    }


def fetch_market_context(row, max_news=3):
    symbol = str(row.get("symbol") or "").strip()
    if not symbol:
        return {}

    provider_symbol = symbol
    if str(row.get("platform") or "").strip().lower() == "freedom24":
        try:
            from metoxes.services.freedom_service import FREEDOM_TICKER_MAP
            provider_symbol = FREEDOM_TICKER_MAP.get(symbol, symbol)
        except Exception:
            provider_symbol = symbol

    cache_key = f"context:{provider_symbol}:{max_news}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    payload = None
    try:
        payload = _fmp_context(provider_symbol, max_news)
    except Exception as error:
        fmp_error = str(error)
    else:
        fmp_error = None

    if payload is None:
        try:
            payload = _yahoo_context(provider_symbol, max_news)
        except Exception as error:
            payload = {
                "news_source": None,
                "news_headlines": [],
                "news_sentiment": "unknown",
                "earnings_source": None,
                "earnings_date": None,
                "market_context_error": str(error)[:500],
            }
        if fmp_error:
            payload["fmp_context_error"] = fmp_error[:500]

    payload["market_context_checked_at"] = datetime.now().isoformat(timespec="seconds")
    _cache_put(cache_key, payload)
    return payload


def enrich_market_context(rows, workers=5, max_news=3):
    result = [dict(row) for row in rows or []]
    if not result:
        return result
    with ThreadPoolExecutor(max_workers=max(1, int(workers))) as executor:
        futures = {executor.submit(fetch_market_context, row, max_news): i for i, row in enumerate(result)}
        for future in as_completed(futures):
            index = futures[future]
            try:
                result[index].update(future.result())
            except Exception as error:
                result[index]["market_context_error"] = str(error)[:500]
    return result
