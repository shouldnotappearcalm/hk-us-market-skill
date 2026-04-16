#!/usr/bin/env python3
"""Batch backtest over HK+US universe with at least N symbols."""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, List

import pandas as pd
import yfinance as yf


SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_ROOT = SCRIPT_DIR.parents[1]
UNIVERSE_SCRIPT = SKILL_ROOT / "market-data" / "scripts" / "fetch_universe_hkus.py"


def _normalize_symbol(raw: str) -> str:
    s = str(raw or "").strip().upper()
    if not s:
        return s
    if s.endswith(".HK"):
        digits = "".join(ch for ch in s if ch.isdigit())
        digits = digits.lstrip("0") or "0"
        return f"{digits.zfill(4)}.HK"
    if s.isdigit():
        digits = s.lstrip("0") or "0"
        return f"{digits.zfill(4)}.HK"
    if ":" in s:
        ex, ticker = s.split(":", 1)
        return f"{ex.strip().upper()}:{ticker.strip().upper()}"
    return f"NASDAQ:{s}"


def _to_yahoo_ticker(symbol: str) -> str:
    normalized = _normalize_symbol(symbol)
    if normalized.endswith(".HK"):
        return normalized
    return normalized.split(":", 1)[1]


def load_universe(market: str) -> List[str]:
    cmd = [sys.executable, str(UNIVERSE_SCRIPT), "--market", market, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    payload = json.loads(proc.stdout)
    rows = payload.get("data") or []
    symbols = []
    seen = set()
    for row in rows:
        s = _normalize_symbol(row.get("symbol"))
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        symbols.append(s)
    if market == "all":
        us = [s for s in symbols if not s.endswith(".HK")]
        hk = [s for s in symbols if s.endswith(".HK")]
        mixed = []
        max_len = max(len(us), len(hk))
        for i in range(max_len):
            if i < len(us):
                mixed.append(us[i])
            if i < len(hk):
                mixed.append(hk[i])
        return mixed
    return symbols


def compute_buy_hold_metrics(df: pd.DataFrame, initial_cash: float) -> Dict:
    bars = df.copy().dropna(subset=["Close"])
    if len(bars) < 30:
        raise ValueError("not_enough_bars")
    start_price = float(bars.iloc[0]["Close"])
    end_price = float(bars.iloc[-1]["Close"])
    if start_price <= 0 or end_price <= 0:
        raise ValueError("invalid_price")
    qty = max(1, int(initial_cash // start_price))
    final_capital = qty * end_price + (initial_cash - qty * start_price)
    equity_curve = bars["Close"].astype(float) * qty + (initial_cash - qty * start_price)
    peak = equity_curve.expanding(min_periods=1).max()
    dd = ((peak - equity_curve) / peak).fillna(0.0)
    max_drawdown_pct = float(dd.max() * 100.0)
    total_return_pct = (final_capital - initial_cash) / initial_cash * 100.0
    return {
        "start": bars.index[0].strftime("%Y-%m-%d"),
        "end": bars.index[-1].strftime("%Y-%m-%d"),
        "bars": int(len(bars)),
        "initial_capital": round(float(initial_cash), 2),
        "final_capital": round(float(final_capital), 2),
        "total_return_pct": round(float(total_return_pct), 4),
        "max_drawdown_pct": round(max_drawdown_pct, 4),
    }


def backtest_batch(
    symbols: List[str],
    start: str,
    end: str,
    min_success: int,
    batch_size: int,
    initial_cash: float,
) -> Dict:
    tested = 0
    success = []
    failures = []

    for i in range(0, len(symbols), batch_size):
        if len(success) >= min_success:
            break
        chunk_symbols = symbols[i : i + batch_size]
        ticker_map = {_to_yahoo_ticker(s): s for s in chunk_symbols}
        tickers = list(ticker_map.keys())
        tested += len(chunk_symbols)

        try:
            data = yf.download(
                tickers=tickers,
                start=start,
                end=end,
                group_by="ticker",
                auto_adjust=False,
                progress=False,
                threads=True,
            )
        except Exception as exc:
            for s in chunk_symbols:
                failures.append({"symbol": s, "reason": f"download_error:{exc.__class__.__name__}"})
            continue

        for ticker in tickers:
            symbol = ticker_map[ticker]
            try:
                if isinstance(data.columns, pd.MultiIndex):
                    if ticker not in data.columns.get_level_values(0):
                        raise ValueError("missing_ticker_data")
                    df = data[ticker].copy()
                else:
                    if len(tickers) != 1:
                        raise ValueError("unexpected_single_frame")
                    df = data.copy()
                if df.empty:
                    raise ValueError("empty_data")
                metrics = compute_buy_hold_metrics(df, initial_cash=initial_cash)
                metrics["symbol"] = symbol
                metrics["ticker"] = ticker
                success.append(metrics)
            except Exception as exc:
                failures.append({"symbol": symbol, "reason": str(exc)})

    success_sorted = sorted(success, key=lambda x: x["total_return_pct"], reverse=True)
    failure_counter = Counter(item["reason"] for item in failures)
    success_market_counter = Counter("HK" if item["symbol"].endswith(".HK") else "US" for item in success)
    scanned_market_counter = Counter("HK" if item.endswith(".HK") else "US" for item in symbols[:tested])
    summary = {
        "requested_min_success": min_success,
        "scanned_symbols": tested,
        "success_count": len(success),
        "failure_count": len(failures),
        "success_rate_on_scanned": round((len(success) / tested), 4) if tested else 0.0,
        "avg_return_pct": round(sum(x["total_return_pct"] for x in success) / len(success), 4) if success else math.nan,
        "median_return_pct": round(float(pd.Series([x["total_return_pct"] for x in success]).median()), 4) if success else math.nan,
        "avg_max_drawdown_pct": round(sum(x["max_drawdown_pct"] for x in success) / len(success), 4) if success else math.nan,
        "success_by_market": dict(success_market_counter),
        "scanned_by_market": dict(scanned_market_counter),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    return {
        "summary": summary,
        "top_10": success_sorted[:10],
        "bottom_10": list(reversed(success_sorted[-10:])),
        "fail_reason_top": [{"reason": k, "count": v} for k, v in failure_counter.most_common(10)],
        "sample_failures": failures[:20],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="全市场批量回测（HK+US）")
    parser.add_argument("--market", default="all", choices=["all", "us", "hk"])
    parser.add_argument("--start", default="2025-01-01")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"))
    parser.add_argument("--min-success", type=int, default=500)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--initial-cash", type=float, default=100000.0)
    parser.add_argument("--output", default="", help="写入 JSON 结果路径")
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    universe = load_universe(args.market)
    result = backtest_batch(
        symbols=universe,
        start=args.start,
        end=args.end,
        min_success=args.min_success,
        batch_size=args.batch_size,
        initial_cash=args.initial_cash,
    )
    result["meta"] = {
        "market": args.market,
        "universe_total": len(universe),
        "start": args.start,
        "end": args.end,
        "batch_size": args.batch_size,
    }

    if args.output:
        output_path = Path(args.output).expanduser().resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    s = result["summary"]
    print(
        f"batch_backtest_hkus done | scanned={s['scanned_symbols']} success={s['success_count']} "
        f"failure={s['failure_count']} min_required={s['requested_min_success']}"
    )
    print(
        f"success_rate={s['success_rate_on_scanned']} avg_return={s['avg_return_pct']} "
        f"median_return={s['median_return_pct']} avg_max_dd={s['avg_max_drawdown_pct']}"
    )
    if result["top_10"]:
        print("top_3:")
        for item in result["top_10"][:3]:
            print(f"  {item['symbol']} return={item['total_return_pct']}% dd={item['max_drawdown_pct']}%")
    if result["fail_reason_top"]:
        print("top_fail_reasons:")
        for item in result["fail_reason_top"][:3]:
            print(f"  {item['reason']}: {item['count']}")


if __name__ == "__main__":
    main()
