#!/usr/bin/env python3
import argparse
import json
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time

try:
    from scripts.hkus_common import normalize_symbol
    from scripts.hkus_data_sources import (
        fetch_fred_series,
        fetch_sina_history,
        fetch_sina_quote,
        fetch_tencent_history,
        fetch_tencent_quote,
        fetch_yahoo_chart_history,
        fetch_yahooquery_fundamental,
        fetch_yahooquery_realtime,
        fetch_yfinance_fundamental,
        fetch_yfinance_history,
    )
except Exception:
    from hkus_common import normalize_symbol
    from hkus_data_sources import (
        fetch_fred_series,
        fetch_sina_history,
        fetch_sina_quote,
        fetch_tencent_history,
        fetch_tencent_quote,
        fetch_yahoo_chart_history,
        fetch_yahooquery_fundamental,
        fetch_yahooquery_realtime,
        fetch_yfinance_fundamental,
        fetch_yfinance_history,
    )


def run(us_symbol: str, hk_symbol: str):
    try:
        from .hkus_common import call_source
        from .hkus_data_sources import _fred_reader_fetch, _fred_csv_fetch
    except ImportError:
        from hkus_common import call_source
        from hkus_data_sources import _fred_reader_fetch, _fred_csv_fetch
    from datetime import timedelta
    us_info, hk_info = normalize_symbol(us_symbol), normalize_symbol(hk_symbol)
    tasks = {}
    for market, info in [("us", us_info), ("hk", hk_info)]:
        for source, fn in [("tencent_history", lambda info=info: fetch_tencent_history(info,"1d",90)),
                           ("sina_history",lambda info=info: fetch_sina_history(info,"1d",90)),
                           ("yfinance",lambda info=info: fetch_yfinance_history(info["yahoo_symbol"],"1d",90)),
                           ("yahoo_chart",lambda info=info: fetch_yahoo_chart_history(info["yahoo_symbol"],"1d",90))]:
            tasks[("history",market,source)] = fn
        for source, fn in [("tencent_quote",lambda info=info:fetch_tencent_quote(info)),
                           ("sina_quote",lambda info=info:fetch_sina_quote(info))]:
            tasks[("realtime",market,source)] = fn
    tasks[("realtime","us","yahooquery_realtime")] = lambda:fetch_yahooquery_realtime(us_info["yahoo_symbol"])
    tasks[("fundamental","us","yfinance")] = lambda:fetch_yfinance_fundamental(us_info["yahoo_symbol"])
    tasks[("fundamental","us","yahooquery")] = lambda:fetch_yahooquery_fundamental(us_info["yahoo_symbol"])
    end=datetime.now(); start=end-timedelta(days=365)
    tasks[("macro","fred_reader")] = lambda:_fred_reader_fetch("DGS10",start,end)
    tasks[("macro","fred_csv")] = lambda:_fred_csv_fetch("DGS10",start,end)
    result={"generated_at":datetime.now().isoformat(),"us_symbol":us_info["normalized"],
            "hk_symbol":hk_info["normalized"],"matrix":{},"diagnostics":[]}
    def check(path,fn):
        started=time.monotonic()
        try:
            value=call_source(fn,8)
            ok=value is not None and len(value)>0
            row={"source":"/".join(path),"status":"ok" if ok else "empty","records":len(value) if ok else 0}
        except Exception as exc:
            row={"source":"/".join(path),"status":"failed","error":f"{type(exc).__name__}: {str(exc)[:200]}"}
        row["elapsed_sec"]=round(time.monotonic()-started,3)
        return path,row
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(check,path,fn) for path,fn in tasks.items()]):
            path,row=future.result();node=result["matrix"]
            for key in path[:-1]:node=node.setdefault(key,{})
            node[path[-1]]=row["status"]
            result["diagnostics"].append(row)
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
