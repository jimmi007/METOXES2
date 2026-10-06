from __future__ import annotations

"""Point-in-time score snapshotting and forward-return backtesting.

The project did not historically store point-in-time score snapshots, so a
credible backtest cannot be reconstructed without look-ahead bias.  V20 starts
capturing them now.  Once snapshots mature past the selected horizon, this
module measures whether scores/metrics predicted subsequent returns and emits
weight recommendations.

Recommendations are advisory and never silently replace live scoring weights.
"""

from datetime import date, datetime, timedelta
import json
import math
import os
from pathlib import Path
import statistics


BASE_DIR = Path(__file__).resolve().parents[2]
HISTORY_FILE = BASE_DIR / "model_score_history.jsonl"
LATEST_REPORT_FILE = BASE_DIR / "model_backtest_latest.json"
WEIGHT_RECOMMENDATIONS_FILE = BASE_DIR / "model_weight_recommendations.json"

GENERAL_METRICS = {
    "fcf_yield": 1,
    "roic": 1,
    "fcf_growth": 1,
    "forward_revenue_growth": 1,
    "forward_eps_growth": 1,
}
FINANCIAL_METRICS = {
    "financial_roe": 1,
    "financial_price_to_book": -1,
    "financial_profit_margin": 1,
    "financial_revenue_growth": 1,
    "financial_forward_eps_growth": 1,
}
SNAPSHOT_FIELDS = (
    "symbol", "name", "sector", "country", "platform", "industry",
    "current_price", "final_score", "fcf_yield", "roic", "fcf_growth",
    "forward_revenue_growth", "forward_eps_growth", "financial_model",
    "financial_roe", "financial_price_to_book", "financial_profit_margin",
    "financial_revenue_growth", "financial_forward_eps_growth",
    "event_impact_score", "peer_quality_percentile", "scenario_bear_delta",
)


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


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value in (None, ""):
        return None
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _snapshot_key(item):
    return (
        str(item.get("snapshot_date") or ""),
        str(item.get("source") or ""),
        str(item.get("symbol") or "").strip().upper(),
        str(item.get("platform") or "").strip().upper(),
    )


def load_model_history(path=HISTORY_FILE):
    path = Path(path)
    if not path.exists():
        return []
    rows = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except Exception:
                continue
            if isinstance(item, dict):
                rows.append(item)
    except Exception:
        return []
    return rows


def record_model_snapshots(rows, source="portfolio", snapshot_date=None, path=HISTORY_FILE):
    if os.getenv("MODEL_HISTORY_ENABLED", "1").lower() in {"0", "false", "no"}:
        return {"recorded": 0, "status": "disabled"}

    day = _parse_date(snapshot_date) or date.today()
    incoming = []
    for row in rows or []:
        symbol = str(row.get("symbol") or "").strip()
        price = _safe_float(row.get("current_price"))
        score = _safe_float(row.get("final_score"))
        if not symbol or price is None or price <= 0 or score is None:
            continue
        item = {field: row.get(field) for field in SNAPSHOT_FIELDS}
        item.update({
            "snapshot_date": day.isoformat(),
            "captured_at": datetime.now().isoformat(timespec="seconds"),
            "source": source,
        })
        incoming.append(item)

    existing = load_model_history(path)
    merged = {_snapshot_key(item): item for item in existing}
    for item in incoming:
        merged[_snapshot_key(item)] = item

    ordered = sorted(
        merged.values(),
        key=lambda item: (_snapshot_key(item), str(item.get("captured_at") or "")),
    )
    path = Path(path)
    path.write_text(
        "\n".join(json.dumps(item, ensure_ascii=False, default=str) for item in ordered)
        + ("\n" if ordered else ""),
        encoding="utf-8",
    )
    return {
        "recorded": len(incoming),
        "total_snapshots": len(ordered),
        "file": str(path),
        "snapshot_date": day.isoformat(),
        "status": "ok",
    }


def _average_ranks(values):
    indexed = sorted(enumerate(values), key=lambda pair: pair[1])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(indexed):
        j = i + 1
        while j < len(indexed) and indexed[j][1] == indexed[i][1]:
            j += 1
        avg_rank = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[indexed[k][0]] = avg_rank
        i = j
    return ranks


def _pearson(x, y):
    if len(x) != len(y) or len(x) < 3:
        return None
    mx = statistics.mean(x)
    my = statistics.mean(y)
    numerator = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    if dx == 0 or dy == 0:
        return None
    return numerator / (dx * dy)


def _spearman(x, y):
    if len(x) != len(y) or len(x) < 3:
        return None
    return _pearson(_average_ranks(x), _average_ranks(y))


def _default_forward_price(symbol, target_date):
    import yfinance as yf

    target = _parse_date(target_date)
    if target is None:
        return None
    start = target - timedelta(days=4)
    end = target + timedelta(days=10)
    history = yf.Ticker(symbol).history(
        start=start.isoformat(),
        end=end.isoformat(),
        auto_adjust=False,
    )
    if history is None or getattr(history, "empty", True):
        return None
    series = history.get("Close")
    if series is None or getattr(series, "empty", True):
        return None
    # Prefer first market close on/after target; otherwise latest before target.
    for idx, value in series.items():
        idx_date = idx.date() if hasattr(idx, "date") else _parse_date(idx)
        if idx_date and idx_date >= target:
            price = _safe_float(value)
            if price is not None and price > 0:
                return price
    for value in reversed(list(series.values)):
        price = _safe_float(value)
        if price is not None and price > 0:
            return price
    return None


def _benchmark_return(benchmark, start_date, end_date, cache, price_fetcher):
    if not benchmark:
        return None
    key1 = (benchmark, str(start_date))
    key2 = (benchmark, str(end_date))
    if key1 not in cache:
        cache[key1] = price_fetcher(benchmark, start_date)
    if key2 not in cache:
        cache[key2] = price_fetcher(benchmark, end_date)
    p0 = _safe_float(cache[key1])
    p1 = _safe_float(cache[key2])
    if p0 in (None, 0) or p1 is None:
        return None
    return (p1 / p0 - 1) * 100


def _evaluate_snapshots(history, horizon_days, as_of_date, benchmark, price_fetcher):
    as_of = _parse_date(as_of_date) or date.today()
    cache = {}
    evaluated = []

    for item in history:
        snap_date = _parse_date(item.get("snapshot_date"))
        start_price = _safe_float(item.get("current_price"))
        symbol = str(item.get("symbol") or "").strip()
        if snap_date is None or start_price in (None, 0) or not symbol:
            continue
        target = snap_date + timedelta(days=int(horizon_days))
        if target > as_of:
            continue

        cache_key = (symbol, target.isoformat())
        if cache_key not in cache:
            try:
                cache[cache_key] = price_fetcher(symbol, target)
            except Exception:
                cache[cache_key] = None
        end_price = _safe_float(cache[cache_key])
        if end_price is None or end_price <= 0:
            continue

        forward_return = (end_price / start_price - 1) * 100
        benchmark_return = None
        if benchmark:
            try:
                benchmark_return = _benchmark_return(
                    benchmark,
                    snap_date,
                    target,
                    cache,
                    price_fetcher,
                )
            except Exception:
                benchmark_return = None
        excess = forward_return - benchmark_return if benchmark_return is not None else forward_return

        row = dict(item)
        row.update({
            "target_date": target.isoformat(),
            "forward_price": round(end_price, 6),
            "forward_return_pct": round(forward_return, 4),
            "benchmark_return_pct": None if benchmark_return is None else round(benchmark_return, 4),
            "forward_excess_return_pct": round(excess, 4),
        })
        evaluated.append(row)
    return evaluated


def _metric_ic(rows, metric, direction=1):
    x = []
    y = []
    for row in rows:
        metric_value = _safe_float(row.get(metric))
        outcome = _safe_float(row.get("forward_excess_return_pct"))
        if metric_value is None or outcome is None:
            continue
        x.append(metric_value)
        y.append(outcome)
    ic = _spearman(x, y)
    directional = None if ic is None else ic * direction
    return {
        "metric": metric,
        "sample_size": len(x),
        "spearman_ic": None if ic is None else round(ic, 4),
        "directional_ic": None if directional is None else round(directional, 4),
    }


def _suggest_weights(ic_rows, fallback_weights):
    positive = {}
    for item in ic_rows:
        ic = _safe_float(item.get("directional_ic"))
        n = int(item.get("sample_size") or 0)
        if ic is None or ic <= 0 or n < 8:
            continue
        # Shrink small samples toward zero to avoid overfitting.
        reliability = min(1.0, n / 40.0)
        positive[item["metric"]] = ic * reliability

    if not positive or sum(positive.values()) <= 0:
        total = sum(fallback_weights.values()) or 1.0
        return {key: round(value / total, 4) for key, value in fallback_weights.items()}, "fallback_existing"

    total = sum(positive.values())
    raw = {key: value / total for key, value in positive.items()}
    # Keep every existing factor alive with a 5% floor, then renormalise.
    combined = {}
    for key in fallback_weights:
        combined[key] = max(0.05, raw.get(key, 0.0))
    total = sum(combined.values()) or 1.0
    return {key: round(value / total, 4) for key, value in combined.items()}, "ic_recommended"


def _quartile_summary(rows):
    valid = [row for row in rows if _safe_float(row.get("final_score")) is not None and _safe_float(row.get("forward_excess_return_pct")) is not None]
    valid.sort(key=lambda row: _safe_float(row.get("final_score")), reverse=True)
    if len(valid) < 8:
        return {"sample_size": len(valid), "status": "insufficient"}
    q = max(1, len(valid) // 4)
    top = valid[:q]
    bottom = valid[-q:]
    top_mean = statistics.mean(_safe_float(row["forward_excess_return_pct"]) for row in top)
    bottom_mean = statistics.mean(_safe_float(row["forward_excess_return_pct"]) for row in bottom)
    hit_rate = sum(1 for row in top if _safe_float(row["forward_excess_return_pct"]) > 0) / len(top) * 100
    return {
        "sample_size": len(valid),
        "top_quartile_mean_excess_return_pct": round(top_mean, 2),
        "bottom_quartile_mean_excess_return_pct": round(bottom_mean, 2),
        "top_minus_bottom_spread_pct": round(top_mean - bottom_mean, 2),
        "top_quartile_positive_hit_rate_pct": round(hit_rate, 2),
        "status": "ok",
    }


def run_score_backtest(
    horizon_days=90,
    min_samples=12,
    benchmark=None,
    as_of_date=None,
    history_path=HISTORY_FILE,
    price_fetcher=None,
    save=True,
):
    history = load_model_history(history_path)
    benchmark = benchmark or os.getenv("BACKTEST_BENCHMARK_SYMBOL") or None
    fetcher = price_fetcher or _default_forward_price
    evaluated = _evaluate_snapshots(
        history,
        horizon_days=horizon_days,
        as_of_date=as_of_date,
        benchmark=benchmark,
        price_fetcher=fetcher,
    )

    general_rows = [row for row in evaluated if not row.get("financial_model") and str(row.get("sector") or "") != "Financial Services"]
    financial_rows = [row for row in evaluated if row.get("financial_model") or str(row.get("sector") or "") == "Financial Services"]

    general_ics = [_metric_ic(general_rows, metric, direction) for metric, direction in GENERAL_METRICS.items()]
    financial_ics = [_metric_ic(financial_rows, metric, direction) for metric, direction in FINANCIAL_METRICS.items()]
    final_score_ic = _metric_ic(evaluated, "final_score", 1)

    general_fallback = {
        "fcf_yield": 0.25,
        "roic": 0.25,
        "fcf_growth": 0.20,
        "forward_revenue_growth": 0.15,
        "forward_eps_growth": 0.15,
    }
    financial_fallback = {
        "financial_roe": 0.30,
        "financial_price_to_book": 0.20,
        "financial_profit_margin": 0.15,
        "financial_revenue_growth": 0.15,
        "financial_forward_eps_growth": 0.20,
    }
    general_weights, general_weight_source = _suggest_weights(general_ics, general_fallback)
    financial_weights, financial_weight_source = _suggest_weights(financial_ics, financial_fallback)

    status = "ok" if len(evaluated) >= int(min_samples) else "insufficient_history"
    report = {
        "status": status,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "horizon_days": int(horizon_days),
        "benchmark": benchmark,
        "history_snapshots": len(history),
        "evaluated_samples": len(evaluated),
        "minimum_samples": int(min_samples),
        "final_score_predictive_ic": final_score_ic,
        "quartile_test": _quartile_summary(evaluated),
        "general_model": {
            "samples": len(general_rows),
            "metric_ic": general_ics,
            "suggested_weights": general_weights,
            "weight_source": general_weight_source,
        },
        "financial_model": {
            "samples": len(financial_rows),
            "metric_ic": financial_ics,
            "suggested_weights": financial_weights,
            "weight_source": financial_weight_source,
        },
        "policy": (
            "Recommendations only. Live Final Score weights are not changed automatically; "
            "this avoids overfitting and look-ahead leakage."
        ),
    }

    if status != "ok":
        report["message"] = (
            "V20 started point-in-time history collection. More matured snapshots are needed "
            "before weight recommendations should be trusted."
        )

    if save:
        LATEST_REPORT_FILE.write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        WEIGHT_RECOMMENDATIONS_FILE.write_text(
            json.dumps({
                "generated_at": report["generated_at"],
                "horizon_days": report["horizon_days"],
                "status": report["status"],
                "general_model": general_weights,
                "financial_model": financial_weights,
                "policy": report["policy"],
            }, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return report


def load_latest_backtest_report(path=LATEST_REPORT_FILE):
    path = Path(path)
    if not path.exists():
        return {
            "status": "not_run_yet",
            "message": "Score snapshots are being collected; run POST /stocks/backtest-scores after enough history has matured.",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as error:
        return {"status": "error", "error": str(error)[:300]}
    return payload if isinstance(payload, dict) else {"status": "error"}
