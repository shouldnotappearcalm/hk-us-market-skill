#!/usr/bin/env python3
import argparse
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import (
        enrich_realtime_premarket,
        fetch_sina_quote,
        fetch_tencent_quote,
        fetch_yahoo_chart_realtime,
        fetch_yahooquery_realtime,
        fetch_yfinance_realtime,
    )
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import (
        enrich_realtime_premarket,
        fetch_sina_quote,
        fetch_tencent_quote,
        fetch_yahoo_chart_realtime,
        fetch_yahooquery_realtime,
        fetch_yfinance_realtime,
    )


def fetch_symbol_realtime(symbol: str, with_premarket: bool = False):
    symbol_info = normalize_symbol(symbol)
    chain = build_fallback_chain(symbol_info["market"], "realtime")
    yahoo_symbol = symbol_info["yahoo_symbol"]
    data_map = {
        "tencent_quote": lambda: fetch_tencent_quote(symbol_info),
        "sina_quote": lambda: fetch_sina_quote(symbol_info),
        "yahooquery_realtime": lambda: fetch_yahooquery_realtime(yahoo_symbol),
        "yfinance": lambda: fetch_yfinance_realtime(yahoo_symbol),
        "yahoo_chart": lambda: fetch_yahoo_chart_realtime(yahoo_symbol),
    }
    picked = pick_first_available(data_map, chain)
    if with_premarket and symbol_info["market"] == "US":
        picked["data"] = enrich_realtime_premarket(picked.get("data"), yahoo_symbol)
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
    parser.add_argument("--with-premarket", action="store_true", help="单票美股显式补查盘前信息；默认不额外请求Yahoo")
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

    result = fetch_symbol_realtime(args.symbol, args.with_premarket)
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
