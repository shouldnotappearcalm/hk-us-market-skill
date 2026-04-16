#!/usr/bin/env python3
import argparse
import json
from datetime import datetime

try:
    from scripts.hkus_data_sources import (
        fetch_fred_series,
        fetch_tencent_quote,
        fetch_yahoo_chart_history,
        fetch_yahooquery_history,
        fetch_yahooquery_fundamental,
        fetch_yfinance_fundamental,
        fetch_yfinance_history,
    )
except Exception:
    from hkus_data_sources import (
        fetch_fred_series,
        fetch_tencent_quote,
        fetch_yahoo_chart_history,
        fetch_yahooquery_history,
        fetch_yahooquery_fundamental,
        fetch_yfinance_fundamental,
        fetch_yfinance_history,
    )


def _status(data):
    return "ok" if data else "failed"


def run(us_symbol: str, hk_symbol: str):
    result = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "us_symbol": us_symbol,
        "hk_symbol": hk_symbol,
        "matrix": {},
    }
    result["matrix"]["history"] = {
        "us": {
            "yfinance": _status(fetch_yfinance_history(us_symbol, "1d", 90)),
            "yahooquery_history": _status(fetch_yahooquery_history(us_symbol, "1d", 90)),
            "yahoo_chart": _status(fetch_yahoo_chart_history(us_symbol, "1d", 90)),
        },
        "hk": {
            "yfinance": _status(fetch_yfinance_history(hk_symbol, "1d", 90)),
            "yahoo_chart": _status(fetch_yahoo_chart_history(hk_symbol, "1d", 90)),
        },
    }
    result["matrix"]["realtime"] = {
        "hk": {"tencent_quote": _status(fetch_tencent_quote(hk_symbol))},
    }
    result["matrix"]["fundamental"] = {
        "us": {
            "yfinance": _status(fetch_yfinance_fundamental(us_symbol)),
            "yahooquery": _status(fetch_yahooquery_fundamental(us_symbol)),
        }
    }
    fred = fetch_fred_series("DGS10", 365)
    result["matrix"]["macro"] = {
        "fred_reader": _status(fred.get("fred_reader")),
        "fred_csv": _status(fred.get("fred_csv")),
    }
    return result


def main():
    parser = argparse.ArgumentParser(description="多渠道可用性检查")
    parser.add_argument("--us-symbol", default="AAPL")
    parser.add_argument("--hk-symbol", default="0700.HK")
    args = parser.parse_args()
    result = run(args.us_symbol, args.hk_symbol)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
