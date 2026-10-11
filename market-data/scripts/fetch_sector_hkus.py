#!/usr/bin/env python3
import argparse
import json

try:
    from scripts.hkus_common import build_response, normalize_symbol
    from scripts.hkus_data_sources import fetch_sector_etf, fetch_yfinance_fundamental
except Exception:
    from hkus_common import build_response, normalize_symbol
    from hkus_data_sources import fetch_sector_etf, fetch_yfinance_fundamental


def run_sector_etf(sector_name: str, days: int, etf: str = None):
    data = fetch_sector_etf(sector_name, days, etf_symbol=etf)
    if not data:
        raise ValueError("source_unavailable: sector etf 无可用数据")
    symbol_info = {"normalized": data["mapped_etf"], "market": "US"}
    source_payload = data.pop("source_metadata")
    source_payload["data"] = data
    return build_response(symbol_info, "sector", source_payload)


def run_symbol_industry(symbol: str):
    symbol_info = normalize_symbol(symbol)
    try:
        from .fetch_fundamental_hkus import run as fundamental
    except ImportError:
        from fetch_fundamental_hkus import run as fundamental
    result = fundamental(symbol)
    data = result["data"]
    if not data.get("sector") and not data.get("industry"):
        raise ValueError("source_unavailable: source returned no sector/industry fields")
    result["timeframe"] = "sector"
    result["data"] = {key:data.get(key) for key in ("sector", "industry", "currency")}
    return result


def main():
    parser = argparse.ArgumentParser(description="HK+US 行业/板块能力")
    parser.add_argument("--sector-name", help="行业名，如 technology/半导体")
    parser.add_argument("--etf", help="显式选择行业代理ETF，例如 SOXX；不自动把未知行业映射成SPY")
    parser.add_argument("--symbol", help="标的查询行业归属，如 AAPL 或 0700.HK")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    if not args.sector_name and not args.symbol and not args.etf:
        parser.error("需要提供 --sector-name 或 --symbol")

    result = run_sector_etf(args.sector_name or args.etf, args.days, args.etf) if args.sector_name or args.etf else run_symbol_industry(args.symbol)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(f"【行业能力】source={result['source_actual']} fallback={result['fallback_used']}")
    print(json.dumps(result["data"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
