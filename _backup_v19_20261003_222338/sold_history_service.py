from collections import defaultdict
from datetime import datetime


def _to_float(value, default=0.0):
    try:
        if value in (None, ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text = str(value).strip()

    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.replace(tzinfo=None)
    except ValueError:
        return None


def _fx_to_eur(currency, trade_date, fx_resolver=None):
    currency = str(currency or "").strip().upper()

    if currency == "EUR":
        return 1.0

    if not currency or fx_resolver is None:
        return None

    try:
        value = fx_resolver(currency, trade_date)
    except Exception:
        return None

    try:
        if value is None:
            return None
        value = float(value)
    except (TypeError, ValueError):
        return None

    return value if value > 0 else None


def _add_daily_sale_value(daily_values, trade_date, value_eur):
    """Accumulate executed sale value by calendar day."""
    if trade_date is None or value_eur in (None, ""):
        return

    try:
        value = abs(float(value_eur))
    except (TypeError, ValueError):
        return

    if value <= 0:
        return

    day_key = trade_date.date().isoformat()
    daily_values[day_key] = daily_values.get(day_key, 0.0) + value


def _select_sell_date(daily_values, fallback_date=None):
    """
    Return the day on which the largest total sale value was executed.

    Multiple fills on the same day are combined before comparing days. If two
    days have exactly the same value, the later day wins deterministically.
    When the broker source does not expose sale value, fall back to the last
    verified sale date rather than inventing a value-based date.
    """
    if daily_values:
        return max(
            daily_values.items(),
            key=lambda item: (item[1], item[0]),
        )[0]

    if isinstance(fallback_date, datetime):
        return fallback_date.date().isoformat()

    if fallback_date not in (None, ""):
        return str(fallback_date)

    return None


def summarize_freedom_realized_trades(trades, fx_resolver=None):
    """
    Build cumulative realized-sale summaries from Freedom24/Tradernet trades.

    Freedom's getTradesHistory fields used here:
      type == "2"      -> sell
      q                -> executed quantity
      p                -> executed sale price
      v / summ         -> executed sale amount
      profit           -> broker-reported realized gross trade profit
      commission       -> broker commission
      commiss_exchange -> exchange commission (if any)
      curr_c           -> trade/profit currency
      commission_currency -> commission currency

    The user-facing total_profit_loss is converted to EUR on the trade date.
    No market/current price is used for realized P/L.
    """
    grouped = defaultdict(lambda: {
        "platform": "Freedom24",
        "sell_trades": 0,
        "sold_quantity": 0.0,
        "sale_proceeds_eur": 0.0,
        "execution_value_eur": 0.0,
        "cost_basis_eur": 0.0,
        "gross_profit_eur": 0.0,
        "commissions_eur": 0.0,
        "net_profit_loss_eur": 0.0,
        "first_sale_date": None,
        "last_sale_date": None,
        "daily_sale_value_eur": {},
        "missing_fx_trades": 0,
    })

    for trade in trades or []:
        if str(trade.get("type")) != "2":
            continue

        instr_type = str(trade.get("instr_type_c") or "")
        if instr_type and instr_type != "1":
            continue

        symbol = str(trade.get("instr_nm") or "").strip()
        if not symbol:
            continue

        quantity = abs(_to_float(trade.get("q")))
        if quantity <= 0:
            continue

        trade_date_value = trade.get("date")
        trade_date = _parse_date(trade_date_value)
        trade_currency = str(trade.get("curr_c") or "").strip().upper()
        trade_fx = _fx_to_eur(
            trade_currency,
            trade_date_value,
            fx_resolver=fx_resolver,
        )

        price = _to_float(trade.get("p"))
        proceeds_native = _to_float(
            trade.get("v"),
            default=_to_float(trade.get("summ"), default=price * quantity),
        )
        gross_profit_native = _to_float(trade.get("profit"))

        commission_native = _to_float(trade.get("commission"))
        commission_currency = str(
            trade.get("commission_currency") or trade_currency
        ).strip().upper()
        commission_fx = _fx_to_eur(
            commission_currency,
            trade_date_value,
            fx_resolver=fx_resolver,
        )

        exchange_commission_native = _to_float(
            trade.get("commiss_exchange")
        )
        exchange_commission_fx = trade_fx

        row = grouped[symbol.upper()]
        row["symbol"] = symbol
        row["sell_trades"] += 1
        row["sold_quantity"] += quantity

        if trade_date is not None:
            if row["first_sale_date"] is None or trade_date < row["first_sale_date"]:
                row["first_sale_date"] = trade_date
            if row["last_sale_date"] is None or trade_date > row["last_sale_date"]:
                row["last_sale_date"] = trade_date

        if trade_fx is None or commission_fx is None or exchange_commission_fx is None:
            row["missing_fx_trades"] += 1
            continue

        proceeds_eur = proceeds_native * trade_fx
        execution_value_eur = price * quantity * trade_fx
        gross_profit_eur = gross_profit_native * trade_fx
        commission_eur = commission_native * commission_fx
        exchange_commission_eur = exchange_commission_native * exchange_commission_fx

        cost_basis_eur = proceeds_eur - gross_profit_eur
        net_profit_eur = gross_profit_eur - commission_eur - exchange_commission_eur

        row["sale_proceeds_eur"] += proceeds_eur
        row["execution_value_eur"] += execution_value_eur
        _add_daily_sale_value(
            row["daily_sale_value_eur"],
            trade_date,
            execution_value_eur if execution_value_eur > 0 else proceeds_eur,
        )
        row["cost_basis_eur"] += cost_basis_eur
        row["gross_profit_eur"] += gross_profit_eur
        row["commissions_eur"] += commission_eur + exchange_commission_eur
        row["net_profit_loss_eur"] += net_profit_eur

    summaries = []

    for symbol_key, row in grouped.items():
        complete = row["missing_fx_trades"] == 0

        average_sale_price_eur = (
            row["sale_proceeds_eur"] / row["sold_quantity"]
            if complete and row["sold_quantity"] > 0
            else None
        )
        average_execution_price_eur = (
            row["execution_value_eur"] / row["sold_quantity"]
            if complete and row["sold_quantity"] > 0
            else None
        )

        realized_return_pct = (
            row["net_profit_loss_eur"] / row["cost_basis_eur"] * 100
            if complete and row["cost_basis_eur"] > 0
            else None
        )

        summaries.append({
            "symbol": row.get("symbol") or symbol_key,
            "platform": "Freedom24",
            "sell_trades": row["sell_trades"],
            "sold_quantity": round(row["sold_quantity"], 8),
            "sale_proceeds_eur": round(row["sale_proceeds_eur"], 2) if complete else None,
            "gross_sale_value_eur": round(row["execution_value_eur"], 2) if complete else None,
            "cost_basis_eur": round(row["cost_basis_eur"], 2) if complete else None,
            "gross_profit_eur": round(row["gross_profit_eur"], 2) if complete else None,
            "commissions_eur": round(row["commissions_eur"], 2) if complete else None,
            "net_profit_loss_eur": round(row["net_profit_loss_eur"], 2) if complete else None,
            "average_sale_price_eur": round(average_sale_price_eur, 6) if average_sale_price_eur is not None else None,
            "average_execution_price_eur": round(average_execution_price_eur, 6) if average_execution_price_eur is not None else None,
            "realized_return_pct": round(realized_return_pct, 2) if realized_return_pct is not None else None,
            "first_sale_date": row["first_sale_date"].date().isoformat() if row["first_sale_date"] is not None else None,
            "last_sale_date": row["last_sale_date"].date().isoformat() if row["last_sale_date"] is not None else None,
            "sell_date": _select_sell_date(
                row["daily_sale_value_eur"],
                row["last_sale_date"],
            ),
            "sell_date_basis": (
                "largest_daily_execution_value_eur"
                if row["daily_sale_value_eur"]
                else "last_sale_date_fallback"
            ),
            "history_complete": complete,
            "pnl_verified": complete,
            "value_return_verified": complete,
            "missing_fx_trades": row["missing_fx_trades"],
            "source": "Freedom24 getTradesHistory",
        })

    summaries.sort(
        key=lambda item: (item.get("last_sale_date") or "", item.get("symbol") or ""),
        reverse=True,
    )
    return summaries


def summarize_capital_realized_transactions(transactions, fx_resolver=None):
    """
    Summarise Capital.com realised P/L from account transaction history.

    Verified rule from the user's real payload:
      transactionType == "TRADE"
      note == "Trade closed"
      status == "PROCESSED"
      size -> signed realised cash P/L in `currency`

    Capital transaction history does not expose execution quantity / sale
    proceeds / cost basis in these rows, so those fields deliberately remain
    None. We therefore populate total_profit_loss exactly from broker history
    but do NOT manufacture SOLD VALUE or SOLD RETURN.

    `reference` is used to deduplicate repeated rows. When missing, a stable
    fallback key is built from deal/date/symbol/size.
    """
    grouped = defaultdict(lambda: {
        "platform": "Capital",
        "closed_transactions": 0,
        "net_profit_loss_eur": 0.0,
        "first_sale_date": None,
        "last_sale_date": None,
        "missing_fx_transactions": 0,
        "references": [],
    })
    seen = set()

    for tx in transactions or []:
        if str(tx.get("transactionType") or "").strip().upper() != "TRADE":
            continue
        if str(tx.get("note") or "").strip().lower() != "trade closed":
            continue
        if str(tx.get("status") or "").strip().upper() != "PROCESSED":
            continue

        symbol = str(tx.get("instrumentName") or "").strip()
        if not symbol:
            continue

        reference = str(tx.get("reference") or "").strip()
        dedupe_key = reference or "|".join([
            str(tx.get("dealId") or ""),
            str(tx.get("dateUtc") or tx.get("date") or ""),
            symbol.upper(),
            str(tx.get("size") or ""),
        ])
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        date_value = tx.get("dateUtc") or tx.get("date")
        trade_date = _parse_date(date_value)
        currency = str(tx.get("currency") or "").strip().upper()
        fx = _fx_to_eur(currency, date_value, fx_resolver=fx_resolver)
        pnl_native = _to_float(tx.get("size"))

        row = grouped[symbol.upper()]
        row["symbol"] = symbol
        row["closed_transactions"] += 1
        if reference:
            row["references"].append(reference)

        if trade_date is not None:
            if row["first_sale_date"] is None or trade_date < row["first_sale_date"]:
                row["first_sale_date"] = trade_date
            if row["last_sale_date"] is None or trade_date > row["last_sale_date"]:
                row["last_sale_date"] = trade_date

        if fx is None:
            row["missing_fx_transactions"] += 1
            continue

        row["net_profit_loss_eur"] += pnl_native * fx

    summaries = []
    for symbol_key, row in grouped.items():
        complete = row["missing_fx_transactions"] == 0
        summaries.append({
            "symbol": row.get("symbol") or symbol_key,
            "platform": "Capital",
            "closed_transactions": row["closed_transactions"],
            "sell_trades": row["closed_transactions"],
            "sold_quantity": None,
            "sale_proceeds_eur": None,
            "cost_basis_eur": None,
            "gross_profit_eur": None,
            "commissions_eur": None,
            "net_profit_loss_eur": round(row["net_profit_loss_eur"], 2) if complete else None,
            "average_sale_price_eur": None,
            "average_execution_price_eur": None,
            "gross_sale_value_eur": None,
            "realized_return_pct": None,
            "first_sale_date": row["first_sale_date"].date().isoformat() if row["first_sale_date"] is not None else None,
            "last_sale_date": row["last_sale_date"].date().isoformat() if row["last_sale_date"] is not None else None,
            "sell_date": _select_sell_date({}, row["last_sale_date"]),
            "sell_date_basis": (
                "single_closed_trade"
                if row["closed_transactions"] == 1
                else "last_sale_date_fallback_no_sale_value"
            ),
            "history_complete": complete,
            "pnl_verified": complete,
            "value_return_verified": False,
            "missing_fx_transactions": row["missing_fx_transactions"],
            "references": row["references"],
            "source": "Capital /api/v1/history/transactions",
            "commission_status": "no separate commission rows included unless broker returns them as confirmed adjustments",
        })

    summaries.sort(
        key=lambda item: (item.get("last_sale_date") or "", item.get("symbol") or ""),
        reverse=True,
    )
    return summaries



def normalize_trading212_symbol(ticker):
    """
    Convert Trading212 instrument tickers to the symbols used by METOXES2.

    Observed examples:
      GASS_US_EQ -> GASS
      VUSAl_EQ   -> VUSA.L
      RAREd_EQ   -> RARE.DE
      FOODm_EQ   -> FOOD.MI

    Unknown exchange suffixes are kept as the base Trading212 code instead of
    inventing a market suffix.
    """
    raw = str(ticker or "").strip()
    if not raw:
        return ""

    upper = raw.upper()
    if upper.endswith("_US_EQ"):
        return raw[:-6].upper()

    if upper.endswith("_EQ"):
        core = raw[:-3]
        suffix_map = {
            "l": ".L",
            "d": ".DE",
            "m": ".MI",
            "p": ".PA",
            "a": ".AS",
            "s": ".SW",
            "b": ".BR",
            "f": ".F",
        }
        if len(core) >= 2 and core[-1] in suffix_map:
            return core[:-1].upper() + suffix_map[core[-1]]
        return core.upper()

    return raw.upper()


def summarize_trading212_realized_orders(items, fx_resolver=None):
    """
    Build broker-authoritative Trading212 realised P/L summaries.

    Verified from the user's live Trading212 payload:
      * order.status == FILLED
      * order.side == SELL
      * fill.id is the stable fill identifier
      * fill.quantity / fill.price are the executed fill
      * fill.walletImpact.netValue is the wallet cash value
      * fill.walletImpact.realisedProfitLoss is broker-reported realised P/L
      * fill.walletImpact.taxes contains conversion/other fees

    `realisedProfitLoss` is used directly and fees are NOT subtracted again.
    This avoids double-counting broker charges already reflected in the broker's
    realised result.
    """
    grouped = defaultdict(lambda: {
        "platform": "Trading212",
        "sell_trades": 0,
        "sold_quantity": 0.0,
        "sale_proceeds_eur": 0.0,
        "execution_value_eur": 0.0,
        "cost_basis_eur": 0.0,
        "net_profit_loss_eur": 0.0,
        "commissions_eur": 0.0,
        "first_sale_date": None,
        "last_sale_date": None,
        "daily_sale_value_eur": {},
        "missing_fx_fills": 0,
        "missing_pnl_fills": 0,
        "fill_ids": [],
        "raw_tickers": set(),
    })
    seen_fill_ids = set()

    for item in items or []:
        if not isinstance(item, dict):
            continue

        order = item.get("order") if isinstance(item.get("order"), dict) else {}
        fill = item.get("fill") if isinstance(item.get("fill"), dict) else {}

        status = str(order.get("status") or item.get("status") or "").strip().upper()
        side = str(order.get("side") or item.get("side") or "").strip().upper()

        if not side:
            signed_qty = _to_float(
                order.get("filledQuantity"),
                default=_to_float(order.get("quantity"), default=0.0),
            )
            if signed_qty < 0:
                side = "SELL"
            elif signed_qty > 0:
                side = "BUY"

        if status != "FILLED" or side != "SELL":
            continue
        if str(fill.get("type") or "TRADE").strip().upper() != "TRADE":
            continue

        wallet = fill.get("walletImpact") if isinstance(fill.get("walletImpact"), dict) else {}
        ticker = (
            order.get("ticker")
            or (order.get("instrument") or {}).get("ticker")
            or item.get("ticker")
        )
        symbol = normalize_trading212_symbol(ticker)
        if not symbol:
            continue

        fill_id = str(fill.get("id") or "").strip()
        dedupe_key = fill_id or "|".join([
            str(order.get("id") or ""),
            str(fill.get("filledAt") or ""),
            str(ticker or ""),
            str(fill.get("quantity") or ""),
            str(fill.get("price") or ""),
        ])
        if dedupe_key in seen_fill_ids:
            continue
        seen_fill_ids.add(dedupe_key)

        row = grouped[symbol]
        row["symbol"] = symbol
        row["raw_tickers"].add(str(ticker or ""))
        row["sell_trades"] += 1
        if fill_id:
            row["fill_ids"].append(fill_id)

        quantity = abs(_to_float(
            fill.get("quantity"),
            default=_to_float(order.get("filledQuantity"), default=0.0),
        ))
        row["sold_quantity"] += quantity

        date_value = fill.get("filledAt") or order.get("createdAt")
        trade_date = _parse_date(date_value)

        # Exact executed sale price converted to EUR. Trading212 returns
        # fill.price in the instrument currency and walletImpact.fxRate as
        # instrument-currency units per wallet-currency unit. For the user's
        # EUR wallet, USD 9.02 / 1.1356201 = about EUR 7.94 per share.
        execution_price_eur = None
        execution_price_native = _to_float(fill.get("price"), default=0.0)
        instrument_currency = str(
            (order.get("instrument") or {}).get("currency") or ""
        ).strip().upper()
        wallet_currency = str(wallet.get("currency") or order.get("currency") or "").strip().upper()
        wallet_fx_rate = _to_float(wallet.get("fxRate"), default=0.0)

        if execution_price_native > 0:
            if instrument_currency == "EUR":
                execution_price_eur = execution_price_native
            elif wallet_currency == "EUR" and wallet_fx_rate > 0:
                execution_price_eur = execution_price_native / wallet_fx_rate
            elif instrument_currency:
                execution_fx = _fx_to_eur(
                    instrument_currency,
                    date_value,
                    fx_resolver=fx_resolver,
                )
                if execution_fx is not None:
                    execution_price_eur = execution_price_native * execution_fx

        recorded_execution_value = None
        if execution_price_eur is not None and quantity > 0:
            recorded_execution_value = abs(execution_price_eur * quantity)
            row["execution_value_eur"] += recorded_execution_value
            _add_daily_sale_value(
                row["daily_sale_value_eur"],
                trade_date,
                recorded_execution_value,
            )

        if trade_date is not None:
            if row["first_sale_date"] is None or trade_date < row["first_sale_date"]:
                row["first_sale_date"] = trade_date
            if row["last_sale_date"] is None or trade_date > row["last_sale_date"]:
                row["last_sale_date"] = trade_date

        currency = str(wallet.get("currency") or order.get("currency") or "").strip().upper()
        fx = _fx_to_eur(currency, date_value, fx_resolver=fx_resolver)
        pnl_native = wallet.get("realisedProfitLoss")
        if pnl_native in (None, ""):
            row["missing_pnl_fills"] += 1
            continue

        pnl_native = _to_float(pnl_native)
        if fx is None:
            row["missing_fx_fills"] += 1
            continue

        pnl_eur = pnl_native * fx
        row["net_profit_loss_eur"] += pnl_eur

        net_value_native = wallet.get("netValue")
        if net_value_native not in (None, ""):
            proceeds_eur = _to_float(net_value_native) * fx
            row["sale_proceeds_eur"] += proceeds_eur
            row["cost_basis_eur"] += proceeds_eur - pnl_eur
            if recorded_execution_value is None:
                _add_daily_sale_value(
                    row["daily_sale_value_eur"],
                    trade_date,
                    proceeds_eur,
                )

        for tax in wallet.get("taxes") or []:
            if not isinstance(tax, dict):
                continue
            tax_currency = str(tax.get("currency") or currency).strip().upper()
            tax_fx = _fx_to_eur(
                tax_currency,
                tax.get("chargedAt") or date_value,
                fx_resolver=fx_resolver,
            )
            if tax_fx is None:
                continue
            # Taxes/fees in the observed payload are negative wallet impacts.
            row["commissions_eur"] += abs(_to_float(tax.get("quantity"))) * tax_fx

    summaries = []
    for symbol, row in grouped.items():
        complete = (
            row["missing_fx_fills"] == 0
            and row["missing_pnl_fills"] == 0
            and row["sell_trades"] > 0
        )
        has_value = complete and row["sale_proceeds_eur"] > 0 and row["cost_basis_eur"] > 0

        average_sale_price_eur = (
            row["sale_proceeds_eur"] / row["sold_quantity"]
            if has_value and row["sold_quantity"] > 0
            else None
        )
        average_execution_price_eur = (
            row["execution_value_eur"] / row["sold_quantity"]
            if complete and row["execution_value_eur"] > 0 and row["sold_quantity"] > 0
            else None
        )
        realized_return_pct = (
            row["net_profit_loss_eur"] / row["cost_basis_eur"] * 100
            if has_value and row["cost_basis_eur"] > 0
            else None
        )

        summaries.append({
            "symbol": symbol,
            "platform": "Trading212",
            "sell_trades": row["sell_trades"],
            "sold_quantity": round(row["sold_quantity"], 8),
            "sale_proceeds_eur": round(row["sale_proceeds_eur"], 2) if has_value else None,
            "gross_sale_value_eur": round(row["execution_value_eur"], 2) if average_execution_price_eur is not None else None,
            "cost_basis_eur": round(row["cost_basis_eur"], 2) if has_value else None,
            "gross_profit_eur": round(row["net_profit_loss_eur"], 2) if complete else None,
            "commissions_eur": round(row["commissions_eur"], 2) if complete else None,
            "net_profit_loss_eur": round(row["net_profit_loss_eur"], 2) if complete else None,
            "average_sale_price_eur": round(average_sale_price_eur, 6) if average_sale_price_eur is not None else None,
            "average_execution_price_eur": round(average_execution_price_eur, 6) if average_execution_price_eur is not None else None,
            "realized_return_pct": round(realized_return_pct, 2) if realized_return_pct is not None else None,
            "first_sale_date": row["first_sale_date"].date().isoformat() if row["first_sale_date"] is not None else None,
            "last_sale_date": row["last_sale_date"].date().isoformat() if row["last_sale_date"] is not None else None,
            "sell_date": _select_sell_date(
                row["daily_sale_value_eur"],
                row["last_sale_date"],
            ),
            "sell_date_basis": (
                "largest_daily_execution_value_eur"
                if row["daily_sale_value_eur"]
                else "last_sale_date_fallback"
            ),
            "history_complete": complete,
            "pnl_verified": complete,
            "value_return_verified": has_value,
            "missing_fx_fills": row["missing_fx_fills"],
            "missing_pnl_fills": row["missing_pnl_fills"],
            "fill_ids": row["fill_ids"],
            "raw_tickers": sorted(t for t in row["raw_tickers"] if t),
            "source": "Trading212 /api/v0/equity/history/orders walletImpact.realisedProfitLoss",
            "pnl_field": "fill.walletImpact.realisedProfitLoss",
            "fee_handling": "broker realisedProfitLoss used directly; walletImpact.taxes shown separately and not subtracted twice",
        })

    summaries.sort(
        key=lambda item: (item.get("last_sale_date") or "", item.get("symbol") or ""),
        reverse=True,
    )
    return summaries

def build_realized_lookup(summaries):
    lookup = {}
    for item in summaries or []:
        symbol = str(item.get("symbol") or "").strip().upper()
        platform = str(item.get("platform") or "").strip().upper()
        if symbol and platform:
            lookup[(symbol, platform)] = dict(item)
    return lookup


def merge_realized_history_results(*results):
    lookup = {}
    summaries = []
    broker_meta = {}

    for result in results:
        if not isinstance(result, dict):
            continue
        lookup.update(result.get("lookup") or {})
        summaries.extend(result.get("summaries") or [])
        meta = result.get("meta") or {}
        broker = str(meta.get("broker") or meta.get("source") or "unknown")
        broker_meta[broker] = meta

    def _status(name):
        meta = broker_meta.get(name) or {}
        return meta.get("status", "NOT_RUN")

    sources = []
    for meta in broker_meta.values():
        source = meta.get("source")
        if source and source not in sources:
            sources.append(source)

    return {
        "lookup": lookup,
        "summaries": summaries,
        "meta": {
            "sources": sources,
            "realized_symbol_platform_pairs": len(lookup),
            "freedom24_status": _status("Freedom24"),
            "capital_status": _status("Capital"),
            "trading212_status": _status("Trading212"),
            "brokers": broker_meta,
        },
    }


def collect_freedom_realized_history(max_rows=5000):
    from metoxes.services.freedom_service import get_freedom_connection
    from metoxes.services.price_service import get_historical_fx_to_eur

    connection = get_freedom_connection()
    response = connection.authorized_request(
        "getTradesHistory",
        {
            "beginDate": "2020-01-01T00:00:00",
            "endDate": "2030-12-31T23:59:59",
            "max": int(max_rows),
            "sort": 1,
        },
    )

    try:
        trades = response["trades"]["trade"]
    except (KeyError, TypeError):
        trades = []
    if isinstance(trades, dict):
        trades = [trades]

    summaries = summarize_freedom_realized_trades(
        trades,
        fx_resolver=get_historical_fx_to_eur,
    )
    lookup = build_realized_lookup(summaries)
    sell_trade_count = sum(
        1 for trade in trades
        if str(trade.get("type")) == "2"
        and str(trade.get("instr_type_c") or "1") == "1"
    )
    complete_symbols = sum(1 for item in summaries if item.get("history_complete"))

    return {
        "lookup": lookup,
        "summaries": summaries,
        "meta": {
            "broker": "Freedom24",
            "source": "Freedom24 getTradesHistory",
            "status": "OK",
            "raw_trades": len(trades),
            "sell_trades": sell_trade_count,
            "realized_symbols": len(summaries),
            "complete_symbols": complete_symbols,
            "max_requested": int(max_rows),
            "possibly_truncated": len(trades) >= int(max_rows),
        },
    }


def safe_collect_freedom_realized_history(max_rows=5000):
    try:
        return collect_freedom_realized_history(max_rows=max_rows)
    except Exception as error:
        return {
            "lookup": {},
            "summaries": [],
            "meta": {
                "broker": "Freedom24",
                "source": "Freedom24 getTradesHistory",
                "status": "ERROR",
                "error": str(error),
            },
        }


async def collect_capital_realized_history(
    from_date="2020-01-01T00:00:00",
    to_date=None,
):
    """Fetch Capital TRADE history and build verified realised P/L by symbol."""
    import asyncio
    from metoxes.services.broker_history_debug_service import (
        fetch_capital_trade_transactions,
    )
    from metoxes.services.price_service import get_historical_fx_to_eur

    payload = await fetch_capital_trade_transactions(
        from_date=from_date,
        to_date=to_date,
    )
    transactions = payload.get("transactions") or []

    summaries = await asyncio.to_thread(
        summarize_capital_realized_transactions,
        transactions,
        get_historical_fx_to_eur,
    )
    lookup = build_realized_lookup(summaries)

    return {
        "lookup": lookup,
        "summaries": summaries,
        "meta": {
            "broker": "Capital",
            "source": "Capital /api/v1/history/transactions?type=TRADE",
            "status": "OK",
            "raw_trade_transactions": len(transactions),
            "trade_closed_transactions": sum(
                int(item.get("closed_transactions") or 0)
                for item in summaries
            ),
            "realized_symbols": len(summaries),
            "complete_symbols": sum(
                1 for item in summaries if item.get("pnl_verified")
            ),
            "possibly_truncated": bool(payload.get("possibly_truncated")),
            "date_windows": payload.get("date_windows"),
            "commission_rows_used": 0,
        },
    }


async def safe_collect_capital_realized_history(
    from_date="2020-01-01T00:00:00",
    to_date=None,
):
    try:
        return await collect_capital_realized_history(
            from_date=from_date,
            to_date=to_date,
        )
    except Exception as error:
        return {
            "lookup": {},
            "summaries": [],
            "meta": {
                "broker": "Capital",
                "source": "Capital /api/v1/history/transactions?type=TRADE",
                "status": "ERROR",
                "error": str(error),
            },
        }


async def collect_trading212_realized_history(
    limit=50,
    max_pages=250,
):
    """Fetch every Trading212 history page and use broker-reported realised P/L."""
    import asyncio
    from metoxes.services.broker_history_debug_service import (
        fetch_trading212_history_orders_all,
    )
    from metoxes.services.price_service import get_historical_fx_to_eur

    payload = await fetch_trading212_history_orders_all(
        limit=limit,
        max_pages=max_pages,
    )
    items = payload.get("items") or []

    summaries = await asyncio.to_thread(
        summarize_trading212_realized_orders,
        items,
        get_historical_fx_to_eur,
    )
    lookup = build_realized_lookup(summaries)

    return {
        "lookup": lookup,
        "summaries": summaries,
        "meta": {
            "broker": "Trading212",
            "source": "Trading212 /api/v0/equity/history/orders",
            "status": "OK",
            "raw_history_items": len(items),
            "history_pages": int(payload.get("page_count") or 0),
            "realized_symbols": len(summaries),
            "sell_fills": sum(int(item.get("sell_trades") or 0) for item in summaries),
            "complete_symbols": sum(1 for item in summaries if item.get("pnl_verified")),
            "possibly_truncated": bool(payload.get("possibly_truncated")),
            "pnl_field": "fill.walletImpact.realisedProfitLoss",
        },
    }


async def safe_collect_trading212_realized_history(
    limit=50,
    max_pages=250,
):
    try:
        return await collect_trading212_realized_history(
            limit=limit,
            max_pages=max_pages,
        )
    except Exception as error:
        return {
            "lookup": {},
            "summaries": [],
            "meta": {
                "broker": "Trading212",
                "source": "Trading212 /api/v0/equity/history/orders",
                "status": "ERROR",
                "error": str(error),
            },
        }

