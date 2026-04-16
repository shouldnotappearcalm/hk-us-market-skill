#!/usr/bin/env python3
import argparse
import json
from datetime import datetime

try:
    from scripts.hkus_common import pick_first_available
    from scripts.hkus_data_sources import FRED_SERIES, fetch_fred_series
except Exception:
    from hkus_common import pick_first_available
    from hkus_data_sources import FRED_SERIES, fetch_fred_series


def _pack(series_ids, lookback_days):
    output = {}
    source_stats = {}
    for series_id in series_ids:
        data_map = fetch_fred_series(series_id, lookback_days)
        picked = pick_first_available(data_map, ["fred_reader", "fred_csv"])
        output[series_id] = {
            "series_name": FRED_SERIES.get(series_id, series_id),
            "source_actual": picked["source_actual"],
            "fallback_used": picked["fallback_used"],
            "fallback_chain": picked["fallback_chain"],
            "data": picked["data"],
        }
        source_stats[series_id] = picked["source_actual"]
    return {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source_stats": source_stats,
        "series": output,
    }


def run_interest_rates(days: int):
    return _pack(["DGS2", "DGS10", "FEDFUNDS"], days)


def run_inflation_employment(months: int):
    return _pack(["CPIAUCSL", "UNRATE"], months * 31)


def run_economic_growth(quarters: int):
    return _pack(["GDPC1"], quarters * 95)


def main():
    parser = argparse.ArgumentParser(description="US 宏观数据（FRED 双渠道兜底）")
    parser.add_argument("--interest-rates", action="store_true")
    parser.add_argument("--inflation-employment", action="store_true")
    parser.add_argument("--economic-growth", action="store_true")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--months", type=int, default=24)
    parser.add_argument("--quarters", type=int, default=20)
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    selected = [args.interest_rates, args.inflation_employment, args.economic_growth]
    if sum(1 for x in selected if x) != 1:
        parser.error("必须且只能选择一个宏观能力")

    if args.interest_rates:
        result = run_interest_rates(args.days)
    elif args.inflation_employment:
        result = run_inflation_employment(args.months)
    else:
        result = run_economic_growth(args.quarters)

    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    print(json.dumps(result["source_stats"], ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
