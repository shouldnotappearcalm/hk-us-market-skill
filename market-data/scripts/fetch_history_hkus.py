#!/usr/bin/env python3
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import (
        fetch_yahooquery_history,
        fetch_yahoo_chart_history,
        fetch_yfinance_history,
    )
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import (
        fetch_yahooquery_history,
        fetch_yahoo_chart_history,
        fetch_yfinance_history,
    )


def _filter_and_trim(records, start: str, end: str, count: int):
    if not records:
        return []
    df = pd.DataFrame(records)
    if "time" not in df.columns:
        return records[-count:]
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    if start:
        df = df[df["time"] >= pd.to_datetime(start)]
    if end:
        df = df[df["time"] <= pd.to_datetime(end)]
    df = df.sort_values("time").tail(count)
    df["time"] = df["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df.to_dict(orient="records")


def fetch_symbol_history(symbol: str, interval: str, days: int, start: str, end: str, count: int):
    symbol_info = normalize_symbol(symbol)
    chain = build_fallback_chain(symbol_info["market"], "history")
    yahoo_symbol = symbol_info["yahoo_symbol"]
    data_map = {
        "yfinance": fetch_yfinance_history(yahoo_symbol, interval, days),
        "yahooquery_history": fetch_yahooquery_history(yahoo_symbol, interval, days),
        "yahoo_chart": fetch_yahoo_chart_history(yahoo_symbol, interval, days),
    }
    picked = pick_first_available(data_map, chain)
    cleaned = _filter_and_trim(picked["data"], start, end, count)
    picked["data"] = cleaned
    return build_response(symbol_info, interval, picked)


def run_batch(symbols, interval, days, start, end, count, workers: int):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(fetch_symbol_history, symbol, interval, days, start, end, count): symbol
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
    parser.add_argument("--interval", default="1d", choices=["1d", "1wk", "1mo"])
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
        result = run_batch(symbols, args.interval, args.days, args.start, args.end, args.count, args.workers)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    result = fetch_symbol_history(args.symbol, args.interval, args.days, args.start, args.end, args.count)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"【{result['symbol']} 历史K线】{result['timeframe']} 数据源: {result['source_actual']}")
    print(f"fallback_used={result['fallback_used']} chain={result['fallback_chain']}")
    print(json.dumps(result["data"][:10], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
