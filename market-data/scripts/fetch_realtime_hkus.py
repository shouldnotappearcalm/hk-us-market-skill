#!/usr/bin/env python3
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import (
        fetch_tencent_quote,
        fetch_yahooquery_history,
        fetch_yahoo_chart_realtime,
        fetch_yfinance_realtime,
    )
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import (
        fetch_tencent_quote,
        fetch_yahooquery_history,
        fetch_yahoo_chart_realtime,
        fetch_yfinance_realtime,
    )


def fetch_symbol_realtime(symbol: str):
    symbol_info = normalize_symbol(symbol)
    chain = build_fallback_chain(symbol_info["market"], "realtime")
    yahoo_symbol = symbol_info["yahoo_symbol"]
    yahooquery_hist = fetch_yahooquery_history(yahoo_symbol, "1d", 7)
    yahooquery_rt = None
    if yahooquery_hist:
        last = yahooquery_hist[-1]
        prev = yahooquery_hist[-2] if len(yahooquery_hist) > 1 else yahooquery_hist[-1]
        close = last.get("close")
        prev_close = prev.get("close")
        if close is not None and prev_close is not None:
            change = close - prev_close
            yahooquery_rt = {
                "price": close,
                "open": last.get("open"),
                "high": last.get("high"),
                "low": last.get("low"),
                "previous_close": prev_close,
                "change": round(change, 4),
                "change_pct": round(change / prev_close * 100, 4) if prev_close else 0.0,
                "volume": last.get("volume"),
            }
    data_map = {
        "yfinance": fetch_yfinance_realtime(yahoo_symbol),
        "yahooquery_history": yahooquery_rt,
        "yahoo_chart": fetch_yahoo_chart_realtime(yahoo_symbol),
        "tencent_quote": fetch_tencent_quote(yahoo_symbol) if symbol_info["market"] == "HK" else None,
    }
    picked = pick_first_available(data_map, chain)
    return build_response(symbol_info, "realtime", picked)


def run_batch(symbols, workers: int):
    results = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_symbol_realtime, symbol): symbol for symbol in symbols}
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
    parser = argparse.ArgumentParser(description="HK+US 实时快照（多渠道兜底）")
    parser.add_argument("--symbol", help="单个标的，如 AAPL 或 0700.HK")
    parser.add_argument("--batch", help="批量标的，逗号分隔")
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    if not args.symbol and not args.batch:
        parser.error("需要提供 --symbol 或 --batch")

    if args.batch:
        symbols = [x.strip() for x in args.batch.split(",") if x.strip()]
        result = run_batch(symbols, args.workers)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    result = fetch_symbol_realtime(args.symbol)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    data = result["data"]
    print(f"【{result['symbol']} 实时】source={result['source_actual']} fallback={result['fallback_used']}")
    print(
        f"price={data.get('price')} change={data.get('change')} "
        f"change_pct={data.get('change_pct')} volume={data.get('volume')}"
    )


if __name__ == "__main__":
    main()
