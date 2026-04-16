#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime


def _run_case(name: str, cmd: str, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    start = time.time()
    proc = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=os.path.dirname(__file__) + "/..",
        env=env,
        text=True,
    )
    elapsed = round((time.time() - start) * 1000, 2)
    success = proc.returncode == 0
    return {
        "name": name,
        "command": cmd,
        "success": success,
        "exit_code": proc.returncode,
        "elapsed_ms": elapsed,
        "stdout_preview": (proc.stdout or "")[:600],
        "stderr_preview": (proc.stderr or "")[:600],
    }


def main():
    parser = argparse.ArgumentParser(description="全功能回测 + 强制降级验证")
    parser.add_argument("--us-symbol", default="AAPL")
    parser.add_argument("--hk-symbol", default="0700.HK")
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    cases = [
        ("realtime_us", f"python3 scripts/fetch_realtime_hkus.py --symbol {args.us_symbol} --json"),
        ("realtime_hk", f"python3 scripts/fetch_realtime_hkus.py --symbol {args.hk_symbol} --json"),
        ("realtime_batch", f"python3 scripts/fetch_realtime_hkus.py --batch {args.us_symbol},TSLA,{args.hk_symbol} --json"),
        ("history_us", f"python3 scripts/fetch_history_hkus.py --symbol {args.us_symbol} --interval 1d --days 120 --count 60 --json"),
        ("history_hk", f"python3 scripts/fetch_history_hkus.py --symbol {args.hk_symbol} --interval 1d --days 120 --count 60 --json"),
        ("history_batch", f"python3 scripts/fetch_history_hkus.py --batch {args.us_symbol},MSFT,{args.hk_symbol} --interval 1d --days 120 --count 60 --workers 4 --json"),
        ("technical_us", f"python3 scripts/fetch_technical_hkus.py {args.us_symbol} --days 180 --interval 1d --json"),
        ("technical_hk", f"python3 scripts/fetch_technical_hkus.py {args.hk_symbol} --days 180 --interval 1d --json"),
        ("fundamental_us", f"python3 scripts/fetch_fundamental_hkus.py --symbol {args.us_symbol} --json"),
        ("fundamental_hk", f"python3 scripts/fetch_fundamental_hkus.py --symbol {args.hk_symbol} --json"),
        ("sector_etf", "python3 scripts/fetch_sector_hkus.py --sector-name 半导体 --days 60 --json"),
        ("sector_symbol", f"python3 scripts/fetch_sector_hkus.py --symbol {args.hk_symbol} --json"),
        ("macro_interest", "python3 scripts/fetch_macro_us.py --interest-rates --days 365 --json"),
        ("macro_inflation_employment", "python3 scripts/fetch_macro_us.py --inflation-employment --months 24 --json"),
        ("macro_growth", "python3 scripts/fetch_macro_us.py --economic-growth --quarters 20 --json"),
        ("healthcheck", f"python3 scripts/healthcheck_sources.py --us-symbol {args.us_symbol} --hk-symbol {args.hk_symbol}"),
        ("universe_all", "python3 scripts/fetch_universe_hkus.py --market all --limit 200 --json"),
        (
            "market_realtime_all",
            "python3 scripts/fetch_market_realtime_hkus.py --market all --universe-limit 120 --top 120 --sort change_pct_desc --json",
        ),
    ]

    forced_failover_cases = [
        (
            "forced_realtime_us_failover",
            f"python3 scripts/fetch_realtime_hkus.py --symbol {args.us_symbol} --json",
            {"HKUS_DISABLE_SOURCES": "yfinance"},
        ),
        (
            "forced_history_us_failover",
            f"python3 scripts/fetch_history_hkus.py --symbol {args.us_symbol} --interval 1d --days 120 --count 60 --json",
            {"HKUS_DISABLE_SOURCES": "yfinance"},
        ),
        (
            "forced_macro_failover",
            "python3 scripts/fetch_macro_us.py --interest-rates --days 365 --json",
            {"HKUS_DISABLE_SOURCES": "fred_reader"},
        ),
    ]

    results = []
    for name, cmd in cases:
        results.append(_run_case(name, cmd))
    for name, cmd, env in forced_failover_cases:
        results.append(_run_case(name, cmd, env))

    success = [x for x in results if x["success"]]
    fail = [x for x in results if not x["success"]]
    payload = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total": len(results),
        "success": len(success),
        "fail": len(fail),
        "success_rate": round(len(success) / len(results), 4) if results else 0.0,
        "results": results,
    }

    if args.output_json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    print(f"Smoke check total={payload['total']} success={payload['success']} fail={payload['fail']}")
    if fail:
        for item in fail:
            print(f"FAIL {item['name']} exit={item['exit_code']}")
    else:
        print("ALL PASSED")


if __name__ == "__main__":
    main()
