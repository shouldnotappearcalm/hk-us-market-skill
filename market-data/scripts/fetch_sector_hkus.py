#!/usr/bin/env python3
import argparse
import json

try:
    from scripts.hkus_common import build_response, normalize_symbol
    from scripts.hkus_data_sources import fetch_sector_etf, fetch_yfinance_fundamental
except Exception:
    from hkus_common import build_response, normalize_symbol
    from hkus_data_sources import fetch_sector_etf, fetch_yfinance_fundamental


def run_sector_etf(sector_name: str, days: int):
    data = fetch_sector_etf(sector_name, days)
    if not data:
        raise ValueError("source_unavailable: sector etf 无可用数据")
    symbol_info = {"normalized": data["mapped_etf"], "market": "US"}
    source_payload = {
        "source_primary": "yfinance",
        "source_actual": "yfinance",
        "fallback_used": False,
        "fallback_chain": ["yfinance"],
        "data": data,
    }
    return build_response(symbol_info, "sector", source_payload)


def run_symbol_industry(symbol: str):
    symbol_info = normalize_symbol(symbol)
    data = fetch_yfinance_fundamental(symbol_info["yahoo_symbol"])
    if not data:
        raise ValueError("source_unavailable: 行业字段不可用")
    source_payload = {
        "source_primary": "yfinance",
        "source_actual": "yfinance",
        "fallback_used": False,
        "fallback_chain": ["yfinance"],
        "data": {
            "sector": data.get("sector"),
            "industry": data.get("industry"),
            "currency": data.get("currency"),
        },
    }
    return build_response(symbol_info, "sector", source_payload)


def main():
    parser = argparse.ArgumentParser(description="HK+US 行业/板块能力")
    parser.add_argument("--sector-name", help="行业名，如 technology/半导体")
    parser.add_argument("--symbol", help="标的查询行业归属，如 AAPL 或 0700.HK")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    if not args.sector_name and not args.symbol:
        parser.error("需要提供 --sector-name 或 --symbol")

    result = run_sector_etf(args.sector_name, args.days) if args.sector_name else run_symbol_industry(args.symbol)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"【行业能力】source={result['source_actual']} fallback={result['fallback_used']}")
    print(json.dumps(result["data"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
