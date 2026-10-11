#!/usr/bin/env python3
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import math

try:
    from .hkus_common import normalize_history_records, market_timezone
    from .hkus_runtime import cached_fetch
    from .hkus_calendar import freshness
except ImportError:
    from hkus_common import normalize_history_records, market_timezone
    from hkus_runtime import cached_fetch
    from hkus_calendar import freshness

import pandas as pd

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import (
        fetch_sina_history,
        fetch_tencent_history,
        fetch_yahooquery_history,
        fetch_yahoo_chart_history,
        fetch_yfinance_history,
    )
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import (
        fetch_sina_history,
        fetch_tencent_history,
        fetch_yahooquery_history,
        fetch_yahoo_chart_history,
        fetch_yfinance_history,
    )


def _filter_and_trim(records, start: str, end: str, count: int):
    # Date filters are inclusive exchange session dates, including intraday bars on end.
    rows = [row for row in records if (not start or row["trade_date"] >= start) and (not end or row["trade_date"] <= end)]
    return sorted(rows, key=lambda row: row["time"])[-count:]


def validate_bars(records, source):
    if not isinstance(records, list) or not records:
        raise ValueError("empty bar series")
    for row in records:
        values = [row.get(key) for key in ("open", "high", "low", "close")]
        if not all(isinstance(value, (int, float)) and math.isfinite(value) for value in values):
            raise ValueError("bar has missing or non-finite OHLC")
        opening, high, low, close = values
        if low > min(opening, close) or high < max(opening, close) or low > high:
            raise ValueError("invalid OHLC ordering")
        if row.get("volume") is not None and row["volume"] < 0:
            raise ValueError("negative volume")


def fetch_symbol_history(symbol: str, interval: str, days: int, start: str, end: str, count: int, adjust="raw", no_cache=False):
    if adjust not in ("raw", "qfq", "split_adjusted", "total_return"):
        raise ValueError("adjust=raw/qfq/split_adjusted/total_return")
    if days < 1 or count < 1:
        raise ValueError("days/count must be positive")
    if interval not in ("1d", "1wk", "1mo", "1m", "5m", "15m", "30m", "60m"):
        raise ValueError("unsupported interval")
    for value in (start, end):
        if value and datetime.strptime(value, "%Y-%m-%d").strftime("%Y-%m-%d") != value:
            raise ValueError("dates must be YYYY-MM-DD")
    if start and end and start > end:
        raise ValueError("start must not be after end")
    info = normalize_symbol(symbol)
    yahoo = info["yahoo_symbol"]
    chain = build_fallback_chain(info["market"], "history")
    requested_days = max(days, (datetime.now(timezone.utc).date() - datetime.strptime(start, "%Y-%m-%d").date()).days + 7) if start else days
    key = f"history-v3:{info['normalized']}:{interval}:{requested_days}:{start}:{end}:{count}:{adjust}"

    def fetch(lookback):
        stale_candidates = []
        callbacks = {
            "tencent_history": lambda: fetch_tencent_history(info, interval, lookback, adjust=adjust),
            "sina_history": lambda: fetch_sina_history(info, interval, lookback, adjust=adjust),
            "yfinance": lambda: fetch_yfinance_history(yahoo, interval, lookback, adjust=adjust),
            "yahooquery_history": lambda: fetch_yahooquery_history(yahoo, interval, lookback, adjust=adjust),
            "yahoo_chart": lambda: fetch_yahoo_chart_history(yahoo, interval, lookback, adjust=adjust),
        }
        def validate(records, source):
            validate_bars(records, source)
            if interval == "1d" and not end:
                normalized = normalize_history_records(records, info["market"], interval)
                quality = freshness(normalized[-1]["trade_date"], info["market"])
                if quality.get("stale"):
                    stale_candidates.append((normalized[-1]["trade_date"], source, records))
                    raise ValueError("stale series: latest completed exchange session missing")
        try:
            return pick_first_available(callbacks, chain, validator=validate, health_scope=f"history:{adjust}:{interval}")
        except ValueError as exc:
            if not stale_candidates:
                raise
            # Preserve the newest valid stale source when every fresh route is unavailable.
            _, source, records = max(stale_candidates, key=lambda item: item[0])
            return {"source_primary":chain[0],"source_actual":source,"fallback_used":source!=chain[0],
                    "fallback_chain":chain,"source_errors":{"freshness":str(exc)},"data":records}

    def load(previous):
        old = previous["data"] if previous else None
        incremental = bool(old and interval == "1d" and adjust == "raw" and old.get("data"))
        lookback = requested_days
        if incremental:
            last = datetime.fromisoformat(old["data"][-1]["trade_date"]).date()
            lookback = min(requested_days, max(7, (datetime.now(timezone.utc).date() - last).days + 5))
        picked = fetch(lookback)
        rows = normalize_history_records(picked["data"], info["market"], interval)
        if incremental:
            if picked["source_actual"] == old["source_actual"]:
                merged = {row["time"]: row for row in old["data"]}
                merged.update({row["time"]: row for row in rows})
                rows = sorted(merged.values(), key=lambda row: row["time"])
            elif lookback < requested_days:
                picked = fetch(requested_days)
                rows = normalize_history_records(picked["data"], info["market"], interval)
        picked["data"] = _filter_and_trim(rows, start, end, count)
        if not picked["data"]:
            raise ValueError("no bars in the requested date range")
        details = {"adjust_requested": adjust, "adjust_actual": adjust, "timezone": market_timezone(info["market"]),
                   "time_basis": "exchange_session_date" if interval in ("1d", "1wk", "1mo") else "exchange_local_time",
                   "incremental_refresh": incremental and lookback < requested_days,
                   "coverage_start": rows[0]["trade_date"], "coverage_end": rows[-1]["trade_date"],
                   "requested_start": start or None, "requested_end": end or None}
        details.update(freshness(rows[-1]["trade_date"], info["market"]))
        if end:
            details["historical_query"] = True
        return build_response(info, interval, picked, details)

    result, cache = cached_fetch(key, load, ttl=300 if interval in ("1d", "1wk", "1mo") else 15, no_cache=no_cache)
    result["cache"] = cache
    # A cache hit must still evaluate freshness against the current exchange session.
    result.update(freshness(result["data"][-1]["trade_date"], info["market"]))
    return result


def run_batch(symbols, interval, days, start, end, count, workers: int, adjust="raw", no_cache=False):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_symbol_history, symbol, interval, days, start, end, count, adjust, no_cache): symbol
            for symbol in symbols
        }
        for future in as_completed(futures):
            symbol = futures[future]
            try:
                data = future.result()
                results.append({"ok": True, "symbol": symbol, "result": data})
            except Exception as exc:
                results.append({"ok": False, "symbol": symbol, "error": str(exc)})
    results.sort(key=lambda x: symbols.index(x["symbol"]))
    success = [x for x in results if x["ok"]]
    fail = [x for x in results if not x["ok"]]
    return {
        "meta": {
            "requested": len(symbols),
            "success": len(success),
            "fail": len(fail),
            "success_rate": round(len(success) / len(symbols), 4) if symbols else 0.0,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        },
        "results": results,
    }


def main():
    parser = argparse.ArgumentParser(description="HK+US 历史K线（多渠道兜底）")
    parser.add_argument("--symbol", help="单个标的，如 AAPL 或 0700.HK")
    parser.add_argument("--batch", help="批量标的，逗号分隔")
    parser.add_argument(
        "--interval",
        default="1d",
        choices=["1d", "1wk", "1mo", "1m", "5m", "15m", "30m", "60m"],
    )
    parser.add_argument("--adjust", choices=["raw", "qfq", "split_adjusted", "total_return"], default="raw", help="raw=原始价；qfq=腾讯前复权；total_return=Yahoo分红拆股调整；split_adjusted=Yahoo仅拆股调整，口径不混用")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--start", help="开始日期 YYYY-MM-DD")
    parser.add_argument("--end", help="结束日期 YYYY-MM-DD")
    parser.add_argument("--count", type=int, default=180)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    if not args.symbol and not args.batch:
        parser.error("需要提供 --symbol 或 --batch")

    if args.batch:
        symbols = [x.strip() for x in args.batch.split(",") if x.strip()]
        result = run_batch(symbols, args.interval, args.days, args.start, args.end, args.count, args.workers, args.adjust, args.no_cache)
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return

    result = fetch_symbol_history(args.symbol, args.interval, args.days, args.start, args.end, args.count, args.adjust, args.no_cache)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return
    print(f"【{result['symbol']} 历史K线】{result['timeframe']} 数据源: {result['source_actual']}")
    print(f"fallback_used={result['fallback_used']} chain={result['fallback_chain']}")
    print(json.dumps(result["data"][:10], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status":"unavailable","error":f"{type(exc).__name__}: {exc}","data":[]},ensure_ascii=False))
        raise SystemExit(1)
