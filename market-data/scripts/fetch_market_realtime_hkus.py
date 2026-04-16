#!/usr/bin/env python3
import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Dict, List

import requests

try:
    from scripts.fetch_universe_hkus import fetch_hk_universe, fetch_us_universe
    from scripts.hkus_data_sources import fetch_yahooquery_history, fetch_yfinance_realtime
except Exception:
    from fetch_universe_hkus import fetch_hk_universe, fetch_us_universe
    from hkus_data_sources import fetch_yahooquery_history, fetch_yfinance_realtime


TENCENT_BATCH_URL = "https://qt.gtimg.cn/q="


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    return s


def _chunk(items: List[str], size: int):
    for i in range(0, len(items), size):
        yield items[i : i + size]


def _parse_tencent_hk_line(line: str):
    if "~" not in line:
        return None
    try:
        body = line.split('"', 1)[1].rsplit('"', 1)[0]
        arr = body.split("~")
        if len(arr) < 6:
            return None
        code = arr[2]
        price = float(arr[3]) if arr[3] else 0.0
        prev_close = float(arr[4]) if arr[4] else 0.0
        open_v = float(arr[5]) if arr[5] else None
        if price <= 0 or prev_close <= 0:
            return None
        change = price - prev_close
        change_pct = change / prev_close * 100
        return {
            "symbol": f"{code}.HK",
            "name": arr[1],
            "price": round(price, 4),
            "previous_close": round(prev_close, 4),
            "open": open_v,
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "volume": None,
            "market": "HK",
            "source_actual": "tencent_quote",
        }
    except Exception:
        return None


def _fetch_hk_quotes_tencent(hk_symbols: List[str]) -> Dict[str, Dict]:
    s = _session()
    out = {}
    for batch in _chunk(hk_symbols, 200):
        tk_codes = []
        for sym in batch:
            digits = "".join(ch for ch in sym if ch.isdigit())
            tk_codes.append(f"hk{digits.zfill(5)}")
        url = TENCENT_BATCH_URL + ",".join(tk_codes)
        resp = s.get(url, timeout=20)
        for line in resp.text.splitlines():
            item = _parse_tencent_hk_line(line)
            if item:
                out[item["symbol"]] = item
    return out


def _fetch_us_quotes_yahooquery(us_symbols: List[str]) -> Dict[str, Dict]:
    try:
        from yahooquery import Ticker
    except Exception:
        return {}

    out = {}
    tickers = [x.split(":")[1] for x in us_symbols]
    for batch in _chunk(tickers, 300):
        tq = Ticker(batch, asynchronous=True)
        prices = tq.price
        if not isinstance(prices, dict):
            continue
        for ticker in batch:
            p = prices.get(ticker)
            if not isinstance(p, dict):
                continue
            price = p.get("regularMarketPrice")
            prev_close = p.get("regularMarketPreviousClose")
            if price is None or prev_close in (None, 0):
                continue
            change = float(price) - float(prev_close)
            out[f"{p.get('fullExchangeName', 'NASDAQ').upper()}:{ticker}"] = {
                "symbol": f"{p.get('fullExchangeName', 'NASDAQ').upper()}:{ticker}",
                "name": p.get("shortName") or p.get("longName") or ticker,
                "price": float(price),
                "previous_close": float(prev_close),
                "open": p.get("regularMarketOpen"),
                "change": round(change, 4),
                "change_pct": round(change / float(prev_close) * 100, 4),
                "volume": p.get("regularMarketVolume"),
                "market": "US",
                "source_actual": "yahooquery_price",
            }
    return out


def _fallback_single_quote(symbol: str, market: str):
    if market == "US":
        ticker = symbol.split(":")[1]
        y = fetch_yfinance_realtime(ticker)
        if y:
            return {
                "symbol": symbol,
                "name": ticker,
                "price": y.get("price"),
                "previous_close": y.get("previous_close"),
                "open": y.get("open"),
                "change": y.get("change"),
                "change_pct": y.get("change_pct"),
                "volume": y.get("volume"),
                "market": market,
                "source_actual": "yfinance",
            }
        h = fetch_yahooquery_history(ticker, "1d", 7)
        if h and len(h) >= 2:
            last, prev = h[-1], h[-2]
            change = float(last["close"]) - float(prev["close"])
            return {
                "symbol": symbol,
                "name": ticker,
                "price": last["close"],
                "previous_close": prev["close"],
                "open": last.get("open"),
                "change": round(change, 4),
                "change_pct": round(change / float(prev["close"]) * 100, 4) if prev["close"] else 0.0,
                "volume": last.get("volume"),
                "market": market,
                "source_actual": "yahooquery_history",
            }
    else:
        ticker = symbol
        y = fetch_yfinance_realtime(ticker)
        if y:
            return {
                "symbol": symbol,
                "name": ticker,
                "price": y.get("price"),
                "previous_close": y.get("previous_close"),
                "open": y.get("open"),
                "change": y.get("change"),
                "change_pct": y.get("change_pct"),
                "volume": y.get("volume"),
                "market": market,
                "source_actual": "yfinance",
            }
    return None


def _build_symbol_pool(market: str, symbols: str, universe_limit: int):
    if symbols:
        cleaned = [x.strip() for x in symbols.split(",") if x.strip()]
        us = [x for x in cleaned if ":" in x]
        hk = [x for x in cleaned if x.upper().endswith(".HK")]
        return us, hk

    us, hk = [], []
    if market in {"all", "us"}:
        us = [x["symbol"] for x in fetch_us_universe()]
    if market in {"all", "hk"}:
        hk = [x["symbol"] for x in fetch_hk_universe()]

    if universe_limit > 0:
        us = us[:universe_limit] if market != "hk" else us
        hk = hk[:universe_limit] if market != "us" else hk
    return us, hk


def _sort_quotes(data: List[Dict], sort_key: str):
    reverse = True
    key = "change_pct"
    if sort_key == "change_pct_asc":
        reverse = False
    elif sort_key == "volume_desc":
        key = "volume"
    elif sort_key == "price_desc":
        key = "price"
    data.sort(key=lambda x: x.get(key) if x.get(key) is not None else -math.inf, reverse=reverse)


def run(market: str, symbols: str, universe_limit: int, workers: int, top: int, sort_key: str):
    us_symbols, hk_symbols = _build_symbol_pool(market, symbols, universe_limit)
    quotes = []
    failed = []

    us_map = _fetch_us_quotes_yahooquery(us_symbols) if us_symbols else {}
    hk_map = _fetch_hk_quotes_tencent(hk_symbols) if hk_symbols else {}

    # 容错：exchange 名可能和标准化 symbol 不完全一致，这里按 ticker 再映射一次
    us_by_ticker = {k.split(":")[1]: v for k, v in us_map.items() if ":" in k}
    for sym in us_symbols:
        ticker = sym.split(":")[1]
        item = us_map.get(sym) or us_by_ticker.get(ticker)
        if item:
            item["symbol"] = sym
            quotes.append(item)
        else:
            failed.append({"symbol": sym, "market": "US"})

    for sym in hk_symbols:
        item = hk_map.get(sym)
        if item:
            quotes.append(item)
        else:
            failed.append({"symbol": sym, "market": "HK"})

    if failed:
        recovered = []
        remain = []
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            fut_map = {
                pool.submit(_fallback_single_quote, f["symbol"], f["market"]): f for f in failed
            }
            for fut in as_completed(fut_map):
                req = fut_map[fut]
                try:
                    data = fut.result()
                    if data:
                        recovered.append(data)
                    else:
                        remain.append(req)
                except Exception:
                    remain.append(req)
        quotes.extend(recovered)
        failed = remain

    _sort_quotes(quotes, sort_key)
    display = quotes[:top] if top > 0 else quotes

    source_counts = {}
    for q in quotes:
        src = q.get("source_actual", "unknown")
        source_counts[src] = source_counts.get(src, 0) + 1

    return {
        "meta": {
            "market": market,
            "requested": len(us_symbols) + len(hk_symbols),
            "success": len(quotes),
            "fail": len(failed),
            "success_rate": round(len(quotes) / (len(us_symbols) + len(hk_symbols)), 4)
            if (len(us_symbols) + len(hk_symbols))
            else 0.0,
            "top": top,
            "sort": sort_key,
            "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "source_counts": source_counts,
        },
        "data": display,
        "failed": failed,
    }


def main():
    parser = argparse.ArgumentParser(description="拉取 US/HK 当前交易数据（可全市场）")
    parser.add_argument("--market", default="all", choices=["all", "us", "hk"])
    parser.add_argument("--symbols", help="可选：手动股票列表，逗号分隔；给了则不拉全市场池")
    parser.add_argument("--universe-limit", type=int, default=800, help="全市场模式每个市场最多拉取多少只")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--top", type=int, default=100)
    parser.add_argument(
        "--sort",
        default="change_pct_desc",
        choices=["change_pct_desc", "change_pct_asc", "volume_desc", "price_desc"],
    )
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    result = run(args.market, args.symbols, args.universe_limit, args.workers, args.top, args.sort)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    m = result["meta"]
    print(
        f"【市场当前交易数据】market={m['market']} requested={m['requested']} "
        f"success={m['success']} fail={m['fail']} success_rate={m['success_rate']}"
    )
    print(f"source_counts={m['source_counts']}")
    for row in result["data"][:20]:
        print(
            f"{row.get('symbol')} | price={row.get('price')} | change_pct={row.get('change_pct')} "
            f"| volume={row.get('volume')} | src={row.get('source_actual')}"
        )
    if len(result["data"]) > 20:
        print(f"... 仅展示前20条，共 {len(result['data'])} 条")


if __name__ == "__main__":
    main()
