#!/usr/bin/env python3
import argparse
import json

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import fetch_yahooquery_fundamental, fetch_yfinance_fundamental
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import fetch_yahooquery_fundamental, fetch_yfinance_fundamental


def run(symbol: str):
    symbol_info = normalize_symbol(symbol)
    chain = build_fallback_chain(symbol_info["market"], "fundamental")
    yahoo_symbol = symbol_info["yahoo_symbol"]
    data_map = {
        "yfinance": fetch_yfinance_fundamental(yahoo_symbol),
        "yahooquery": fetch_yahooquery_fundamental(yahoo_symbol),
    }
    picked = pick_first_available(data_map, chain)
    return build_response(symbol_info, "fundamental", picked)


def main():
    parser = argparse.ArgumentParser(description="HK+US 基本面（估值/机构持仓）")
    parser.add_argument("--symbol", required=True, help="标的，如 AAPL 或 0700.HK")
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    result = run(args.symbol)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    data = result["data"]
    print(f"【{result['symbol']} 基本面】source={result['source_actual']} fallback={result['fallback_used']}")
    print(
        f"pe_ttm={data.get('pe_ttm')} pe_forward={data.get('pe_forward')} "
        f"pb={data.get('pb')} market_cap={data.get('market_cap')}"
    )
    print(f"institutional_holders={len(data.get('institutional_holders') or [])}")


if __name__ == "__main__":
    main()
