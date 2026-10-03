import os
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import httpx
from dotenv import load_dotenv

load_dotenv()


# ==========================================================
# GENERIC HELPERS
# ==========================================================


def _first_nonempty(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _module_value(module, names):
    for name in names:
        value = getattr(module, name, None)
        if value not in (None, ""):
            return value
    return None


def _env_value(names):
    for name in names:
        value = os.getenv(name)
        if value not in (None, ""):
            return value
    return None


def _safe_dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _normalise_base_url(base_url, default_url):
    base_url = str(base_url or default_url).strip().rstrip("/")
    return base_url


# ==========================================================
# TRADING212
# ==========================================================


def _get_trading212_config():
    """
    Reuse credentials/constants already present in the user's
    trading212_service when possible. Fallback to common .env names.

    This deliberately supports both the current key+secret Basic auth and
    older/legacy API-key-only setups because the existing project may have
    been created against an earlier Trading212 API version.
    """
    from metoxes.services import trading212_service as t212

    api_key = _first_nonempty(
        _module_value(
            t212,
            [
                "TRADING212_API_KEY",
                "T212_API_KEY",
                "TRADING_212_API_KEY",
                "API_KEY",
            ],
        ),
        _env_value(
            [
                "TRADING212_API_KEY",
                "T212_API_KEY",
                "TRADING_212_API_KEY",
                "API_KEY",
            ]
        ),
    )

    api_secret = _first_nonempty(
        _module_value(
            t212,
            [
                "TRADING212_API_SECRET",
                "T212_API_SECRET",
                "TRADING_212_API_SECRET",
                "API_SECRET",
            ],
        ),
        _env_value(
            [
                "TRADING212_API_SECRET",
                "T212_API_SECRET",
                "TRADING_212_API_SECRET",
                "API_SECRET",
            ]
        ),
    )

    module_headers = _module_value(
        t212,
        ["HEADERS", "headers", "AUTH_HEADERS"],
    )

    base_url = _first_nonempty(
        _module_value(
            t212,
            [
                "TRADING212_BASE_URL",
                "T212_BASE_URL",
                "BASE_URL",
            ],
        ),
        _env_value(
            [
                "TRADING212_BASE_URL",
                "T212_BASE_URL",
            ]
        ),
        "https://live.trading212.com",
    )

    return {
        "api_key": api_key,
        "api_secret": api_secret,
        "headers": _safe_dict(module_headers),
        "base_url": _normalise_base_url(
            base_url,
            "https://live.trading212.com",
        ),
    }


def _trading212_history_url(base_url):
    if base_url.endswith("/api/v0"):
        return f"{base_url}/equity/history/orders"
    return f"{base_url}/api/v0/equity/history/orders"


def _trading212_http_credentials():
    """Return reusable headers/auth for Trading212 requests."""
    config = _get_trading212_config()

    if not config["api_key"] and not config["headers"]:
        raise ValueError(
            "Δεν βρέθηκαν Trading212 API credentials στο υπάρχον service/.env"
        )

    headers = dict(config["headers"])
    auth = None

    if config["api_key"] and config["api_secret"]:
        auth = httpx.BasicAuth(
            str(config["api_key"]),
            str(config["api_secret"]),
        )
    elif config["api_key"]:
        headers.setdefault(
            "Authorization",
            str(config["api_key"]),
        )

    return config, headers, auth


def _trading212_next_url(base_url, next_page_path):
    """Resolve Trading212 relative cursor URLs safely against the broker origin."""
    path = str(next_page_path or "").strip()
    if not path:
        return None
    if path.startswith("http://") or path.startswith("https://"):
        return path

    base = str(base_url or "").rstrip("/")
    if "/api/v0" in base:
        base = base.split("/api/v0", 1)[0]

    return urljoin(base + "/", path.lstrip("/"))


async def fetch_trading212_history_orders_all(
    limit=50,
    ticker=None,
    max_pages=250,
):
    """
    Fetch all Trading212 historical-order pages using nextPagePath cursors.

    The returned `items` are left in the original broker payload form so the
    realised-P/L parser can use nested order/fill/walletImpact fields exactly.
    Duplicate fills are handled later by the realised-history summariser.
    """
    config, headers, auth = _trading212_http_credentials()
    page_limit = max(1, min(int(limit), 50))
    max_pages = max(1, int(max_pages))

    params = {"limit": page_limit}
    if ticker:
        params["ticker"] = str(ticker)

    current_url = _trading212_history_url(config["base_url"])
    current_params = params
    items = []
    page_count = 0
    seen_paths = set()
    last_next_path = None

    async with httpx.AsyncClient(timeout=30) as client:
        while current_url and page_count < max_pages:
            response = await client.get(
                current_url,
                headers=headers,
                params=current_params,
                auth=auth,
            )
            response.raise_for_status()
            payload = response.json()
            page_count += 1

            page_items = payload.get("items") or []
            if isinstance(page_items, list):
                items.extend(
                    item for item in page_items
                    if isinstance(item, dict)
                )

            next_path = payload.get("nextPagePath")
            last_next_path = next_path
            if not next_path:
                break

            next_key = str(next_path)
            if next_key in seen_paths:
                break
            seen_paths.add(next_key)

            current_url = _trading212_next_url(
                config["base_url"],
                next_path,
            )
            current_params = None

    return {
        "items": items,
        "page_count": page_count,
        "nextPagePath": last_next_path,
        "possibly_truncated": bool(last_next_path) and page_count >= max_pages,
        "requested_limit": page_limit,
        "ticker_filter": ticker,
        "source": "Trading212 /api/v0/equity/history/orders",
    }


def _coerce_float(value):
    try:
        if value in (None, ""):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _trading212_side(item, order):
    """
    Trading212 historical-order payloads currently arrive as:
        {"order": {...}, "fill": {...}}

    Keep fallbacks for older/flat responses so the diagnostic endpoint remains
    backwards compatible.
    """
    raw = _first_nonempty(
        order.get("side"),
        order.get("direction"),
        item.get("side"),
        item.get("direction"),
    )
    if raw not in (None, ""):
        return str(raw).upper()

    # Some broker payloads encode sells as a negative order quantity. Only use
    # this when an explicit side/direction field is absent.
    quantity = _coerce_float(
        _first_nonempty(
            order.get("quantity"),
            order.get("filledQuantity"),
            item.get("quantity"),
            item.get("filledQuantity"),
        )
    )
    if quantity is not None:
        if quantity < 0:
            return "SELL"
        if quantity > 0:
            return "BUY"

    return "UNKNOWN"


def _trading212_status(item, order):
    raw = _first_nonempty(
        order.get("status"),
        item.get("status"),
    )
    return str(raw or "UNKNOWN").upper()


def _trading212_ticker(item, order, fill):
    return _first_nonempty(
        order.get("ticker"),
        order.get("instrumentCode"),
        fill.get("ticker"),
        fill.get("instrumentCode"),
        item.get("ticker"),
    )


def _trading212_debug_sample(item):
    order = _safe_dict(item.get("order"))
    fill = _safe_dict(item.get("fill"))

    # If the API ever returns a flat item again, preserve it in `order` for a
    # useful diagnostic response instead of discarding the fields.
    if not order and not fill:
        order = dict(item)

    return {
        "side": _trading212_side(item, order),
        "status": _trading212_status(item, order),
        "ticker": _trading212_ticker(item, order, fill),
        "order": order,
        "fill": fill,
    }


def summarize_trading212_history_debug(payload, sample_size=5):
    """
    Summarise one Trading212 historical-orders page.

    The live API response observed in this project nests the useful fields
    under `order` and `fill`, e.g. {"order": {...}, "fill": {...}}.  V12 was
    incorrectly looking only at the top level, which produced UNKNOWN status
    and empty BUY/SELL samples.  This parser reads the nested payload first and
    keeps flat-response fallbacks for compatibility.
    """
    payload = payload if isinstance(payload, dict) else {}
    items = payload.get("items") or []
    if not isinstance(items, list):
        items = []

    buys = []
    sells = []
    unknown_side_samples = []
    statuses = {}
    sides = {}
    top_level_keys = set()
    order_keys = set()
    fill_keys = set()
    tickers = []
    seen_tickers = set()

    for item in items:
        if not isinstance(item, dict):
            continue

        top_level_keys.update(item.keys())
        order = _safe_dict(item.get("order"))
        fill = _safe_dict(item.get("fill"))
        order_keys.update(order.keys())
        fill_keys.update(fill.keys())

        # Flat-response compatibility.
        effective_order = order or item

        status = _trading212_status(item, effective_order)
        statuses[status] = statuses.get(status, 0) + 1

        side = _trading212_side(item, effective_order)
        sides[side] = sides.get(side, 0) + 1

        ticker = _trading212_ticker(item, effective_order, fill)
        if ticker not in (None, ""):
            ticker_text = str(ticker)
            if ticker_text not in seen_tickers and len(tickers) < 25:
                seen_tickers.add(ticker_text)
                tickers.append(ticker_text)

        sample = _trading212_debug_sample(item)
        if side == "BUY" and len(buys) < sample_size:
            buys.append(sample)
        elif side == "SELL" and len(sells) < sample_size:
            sells.append(sample)
        elif side == "UNKNOWN" and len(unknown_side_samples) < sample_size:
            unknown_side_samples.append(sample)

    return {
        "count": len(items),
        # Keep `keys` for compatibility with the old debug output.
        "keys": sorted(top_level_keys),
        "top_level_keys": sorted(top_level_keys),
        "order_keys": sorted(order_keys),
        "fill_keys": sorted(fill_keys),
        "status_counts": statuses,
        "side_counts": sides,
        "ticker_samples": tickers,
        "buy_samples": buys,
        "sell_samples": sells,
        "unknown_side_samples": unknown_side_samples,
        "nextPagePath": payload.get("nextPagePath"),
        "note": (
            "Nested Trading212 order/fill parsing is enabled. Realized P/L is "
            "read from fill.walletImpact.realisedProfitLoss for FILLED SELL fills."
        ),
    }


async def fetch_trading212_history_debug(limit=50, ticker=None):
    config, headers, auth = _trading212_http_credentials()

    params = {
        "limit": max(1, min(int(limit), 50)),
    }
    if ticker:
        params["ticker"] = str(ticker)

    url = _trading212_history_url(config["base_url"])

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            url,
            headers=headers,
            params=params,
            auth=auth,
        )
        response.raise_for_status()
        payload = response.json()

    result = summarize_trading212_history_debug(payload)
    result["source"] = "Trading212 /api/v0/equity/history/orders"
    result["requested_limit"] = params["limit"]
    result["ticker_filter"] = ticker
    return result


async def safe_fetch_trading212_history_debug(limit=50, ticker=None):
    try:
        return await fetch_trading212_history_debug(
            limit=limit,
            ticker=ticker,
        )
    except Exception as error:
        return {
            "source": "Trading212 /api/v0/equity/history/orders",
            "status": "ERROR",
            "error": str(error),
            "count": 0,
            "keys": [],
            "buy_samples": [],
            "sell_samples": [],
        }


# ==========================================================
# CAPITAL.COM
# ==========================================================


def summarize_capital_transactions_debug(payload, sample_size=5):
    payload = payload if isinstance(payload, dict) else {}
    items = payload.get("transactions") or []
    if not isinstance(items, list):
        items = []

    trade_closed = []
    commissions = []
    all_keys = set()
    type_counts = {}

    commission_types = {
        "TRADE_COMMISSION",
        "TRADE_COMMISSION_GSL",
        "FX_COMMISSION",
    }

    for item in items:
        if not isinstance(item, dict):
            continue

        all_keys.update(item.keys())
        tx_type = str(item.get("transactionType") or "UNKNOWN").upper()
        type_counts[tx_type] = type_counts.get(tx_type, 0) + 1

        note = str(item.get("note") or "").lower()
        if (
            tx_type == "TRADE"
            and "closed" in note
            and len(trade_closed) < sample_size
        ):
            trade_closed.append(item)

        if tx_type in commission_types and len(commissions) < sample_size:
            commissions.append(item)

    return {
        "count": len(items),
        "keys": sorted(all_keys),
        "transaction_type_counts": type_counts,
        "trade_closed_samples": trade_closed,
        "commission_samples": commissions,
        "note": (
            "Send me 2-3 Trade closed rows and any matching commission rows. "
            "Then I can verify whether `size` is signed realized cash P/L and "
            "how commission rows link through `reference`."
        ),
    }


async def _capital_session_tokens():
    from metoxes.services import capital_service as capital

    api_key = _first_nonempty(
        getattr(capital, "CAPITAL_API_KEY", None),
        os.getenv("CAPITAL_API_KEY"),
    )
    identifier = _first_nonempty(
        getattr(capital, "CAPITAL_IDENTIFIER", None),
        os.getenv("CAPITAL_IDENTIFIER"),
    )
    password = _first_nonempty(
        getattr(capital, "CAPITAL_PASSWORD", None),
        os.getenv("CAPITAL_PASSWORD"),
    )
    base_url = _normalise_base_url(
        _first_nonempty(
            getattr(capital, "BASE_URL", None),
            os.getenv("CAPITAL_BASE_URL"),
            "https://api-capital.backend-capital.com",
        ),
        "https://api-capital.backend-capital.com",
    )

    if not api_key or not identifier or not password:
        raise ValueError("Λείπουν CAPITAL_API_KEY / IDENTIFIER / PASSWORD")

    headers = {
        "X-CAP-API-KEY": str(api_key),
        "Content-Type": "application/json",
    }
    body = {
        "identifier": str(identifier),
        "password": str(password),
        "encryptedPassword": False,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{base_url}/api/v1/session",
            headers=headers,
            json=body,
        )
        response.raise_for_status()

    cst = response.headers.get("CST")
    security_token = response.headers.get("X-SECURITY-TOKEN")

    if not cst or not security_token:
        raise ValueError("Capital session did not return CST/X-SECURITY-TOKEN")

    return {
        "base_url": base_url,
        "api_key": str(api_key),
        "cst": cst,
        "security_token": security_token,
    }


def _parse_capital_iso(value):
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


async def _fetch_capital_trade_window(client, tokens, from_date, to_date):
    headers = {
        "X-CAP-API-KEY": tokens["api_key"],
        "CST": tokens["cst"],
        "X-SECURITY-TOKEN": tokens["security_token"],
    }
    params = {
        "from": from_date,
        "to": to_date,
        "type": "TRADE",
    }
    response = await client.get(
        f"{tokens['base_url']}/api/v1/history/transactions",
        headers=headers,
        params=params,
    )
    response.raise_for_status()
    payload = response.json()
    items = payload.get("transactions") or []
    return items if isinstance(items, list) else []


async def fetch_capital_trade_transactions(
    from_date="2020-01-01T00:00:00",
    to_date=None,
):
    """
    Fetch the full Capital TRADE transaction history.

    The user's unfiltered request returned exactly 100 rows because most rows
    were CORPORATE_ACTION/DEPOSIT. For realized P/L we ask Capital directly for
    type=TRADE. As a guard against an undocumented 100-row cap, any date window
    that still returns >=100 rows is recursively split until the result is below
    100 rows (or one day).
    """
    tokens = await _capital_session_tokens()
    if not to_date:
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    start = _parse_capital_iso(from_date)
    end = _parse_capital_iso(to_date)
    if start is None or end is None or end <= start:
        raise ValueError("Invalid Capital transaction date range")

    date_windows = 0
    possibly_truncated = False
    collected = []

    async with httpx.AsyncClient(timeout=45) as client:
        async def fetch_window(window_start, window_end, depth=0):
            nonlocal date_windows, possibly_truncated
            date_windows += 1
            start_text = window_start.strftime("%Y-%m-%dT%H:%M:%S")
            end_text = window_end.strftime("%Y-%m-%dT%H:%M:%S")
            items = await _fetch_capital_trade_window(
                client, tokens, start_text, end_text
            )

            if len(items) >= 100 and (window_end - window_start) > timedelta(days=1):
                midpoint = window_start + (window_end - window_start) / 2
                left = await fetch_window(window_start, midpoint, depth + 1)
                # Avoid overlap on the midpoint timestamp.
                right_start = midpoint + timedelta(seconds=1)
                right = await fetch_window(right_start, window_end, depth + 1)
                return left + right

            if len(items) >= 100:
                possibly_truncated = True
            return items

        collected = await fetch_window(start, end)

    # Deduplicate exact transaction rows by reference when possible.
    unique = []
    seen = set()
    for item in collected:
        if not isinstance(item, dict):
            continue
        reference = str(item.get("reference") or "").strip()
        key = reference or "|".join([
            str(item.get("dealId") or ""),
            str(item.get("dateUtc") or item.get("date") or ""),
            str(item.get("instrumentName") or ""),
            str(item.get("size") or ""),
        ])
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)

    return {
        "transactions": unique,
        "source": "Capital /api/v1/history/transactions?type=TRADE",
        "from": from_date,
        "to": to_date,
        "date_windows": date_windows,
        "possibly_truncated": possibly_truncated,
    }


async def fetch_capital_transactions_debug(
    from_date="2020-01-01T00:00:00",
    to_date=None,
):
    tokens = await _capital_session_tokens()

    if not to_date:
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")

    headers = {
        "X-CAP-API-KEY": tokens["api_key"],
        "CST": tokens["cst"],
        "X-SECURITY-TOKEN": tokens["security_token"],
    }
    params = {
        "from": from_date,
        "to": to_date,
    }

    async with httpx.AsyncClient(timeout=45) as client:
        response = await client.get(
            f"{tokens['base_url']}/api/v1/history/transactions",
            headers=headers,
            params=params,
        )
        response.raise_for_status()
        payload = response.json()

    result = summarize_capital_transactions_debug(payload)
    result["source"] = "Capital /api/v1/history/transactions"
    result["from"] = from_date
    result["to"] = to_date
    return result


async def safe_fetch_capital_transactions_debug(
    from_date="2020-01-01T00:00:00",
    to_date=None,
):
    try:
        return await fetch_capital_transactions_debug(
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as error:
        return {
            "source": "Capital /api/v1/history/transactions",
            "status": "ERROR",
            "error": str(error),
            "count": 0,
            "keys": [],
            "trade_closed_samples": [],
            "commission_samples": [],
        }
