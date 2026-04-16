#!/usr/bin/env python3
import argparse
import io
import json
from datetime import datetime
from typing import Dict, List

import pandas as pd
import requests


NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"
HKEX_SECURITIES_XLSX = "https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx"


def _session() -> requests.Session:
    s = requests.Session()
    s.trust_env = False
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "*/*"})
    return s


def _normalize_us_symbol(exchange: str, ticker: str) -> str:
    t = (ticker or "").strip().upper()
    ex = (exchange or "NASDAQ").strip().upper()
    return f"{ex}:{t}"


def _normalize_hk_symbol(stock_code: str) -> str:
    code = "".join(ch for ch in str(stock_code or "") if ch.isdigit())
    if not code:
        return ""
    return f"{code.zfill(4)}.HK"


def fetch_us_universe() -> List[Dict]:
    s = _session()
    results = []

    nasdaq_text = s.get(NASDAQ_LISTED_URL, timeout=30).text
    lines = [x for x in nasdaq_text.splitlines() if x.strip()]
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 4:
            continue
        ticker, name, market_category, test_issue = parts[0], parts[1], parts[2], parts[3]
        if test_issue == "Y":
            continue
        symbol = _normalize_us_symbol("NASDAQ", ticker)
        results.append(
            {
                "symbol": symbol,
                "ticker": ticker,
                "name": name,
                "market": "US",
                "exchange": "NASDAQ",
                "market_category": market_category,
                "source": "nasdaqtrader_nasdaqlisted",
            }
        )

    exch_map = {
        "N": "NYSE",
        "A": "NYSEAMERICAN",
        "P": "NYSEARCA",
        "Q": "NASDAQ",
        "V": "IEX",
        "Z": "CBOE",
    }
    other_text = s.get(OTHER_LISTED_URL, timeout=30).text
    lines = [x for x in other_text.splitlines() if x.strip()]
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            break
        parts = line.split("|")
        if len(parts) < 7:
            continue
        act_symbol, name, exchange_code, _, _, _, test_issue = parts[:7]
        if test_issue == "Y":
            continue
        ex = exch_map.get(exchange_code, "US")
        symbol = _normalize_us_symbol(ex, act_symbol)
        results.append(
            {
                "symbol": symbol,
                "ticker": act_symbol,
                "name": name,
                "market": "US",
                "exchange": ex,
                "market_category": exchange_code,
                "source": "nasdaqtrader_otherlisted",
            }
        )

    dedup = {}
    for row in results:
        dedup[row["symbol"]] = row
    out = list(dedup.values())
    out.sort(key=lambda x: x["symbol"])
    return out


def fetch_hk_universe() -> List[Dict]:
    s = _session()
    content = s.get(HKEX_SECURITIES_XLSX, timeout=45).content
    raw = pd.read_excel(io.BytesIO(content), sheet_name="ListOfSecurities", header=None)
    header_idx = None
    for i in range(min(len(raw), 20)):
        first = str(raw.iloc[i, 0]).strip().lower()
        second = str(raw.iloc[i, 1]).strip().lower() if raw.shape[1] > 1 else ""
        if first == "stock code" and "name of securities" in second:
            header_idx = i
            break
    if header_idx is None:
        return []

    header = [str(x).strip() for x in raw.iloc[header_idx].tolist()]
    df = raw.iloc[header_idx + 1 :].copy()
    df.columns = header
    df = df.rename(
        columns={
            "Stock Code": "stock_code",
            "Name of Securities": "name",
            "Category": "category",
            "Sub-Category": "sub_category",
            "Trading Currency": "currency",
        }
    )
    keep_cols = ["stock_code", "name", "category", "sub_category", "currency"]
    for col in keep_cols:
        if col not in df.columns:
            df[col] = None
    df = df[keep_cols].copy()
    df = df[df["category"].astype(str).str.contains("Equity", na=False)]
    df["symbol"] = df["stock_code"].map(_normalize_hk_symbol)
    df = df[df["symbol"] != ""]
    df["market"] = "HK"
    df["exchange"] = "HKEX"
    df["source"] = "hkex_list_of_securities"
    records = df.to_dict(orient="records")
    records.sort(key=lambda x: x["symbol"])
    return records


def run(market: str) -> Dict:
    market = market.lower()
    data = []
    if market in {"us", "all"}:
        data.extend(fetch_us_universe())
    if market in {"hk", "all"}:
        data.extend(fetch_hk_universe())
    meta = {
        "market": market,
        "total": len(data),
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sources": sorted(list({x.get("source") for x in data if x.get("source")})),
    }
    return {"meta": meta, "data": data}


def main():
    parser = argparse.ArgumentParser(description="拉取 US/HK 全市场股票清单")
    parser.add_argument("--market", default="all", choices=["all", "us", "hk"])
    parser.add_argument("--limit", type=int, default=0, help="输出条数限制，0 表示不限制")
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    result = run(args.market)
    if args.limit and args.limit > 0:
        result["data"] = result["data"][: args.limit]
    result["meta"]["returned"] = len(result["data"])

    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    print(
        f"【市场股票清单】market={result['meta']['market']} total={result['meta']['total']} "
        f"returned={result['meta']['returned']}"
    )
    print(f"sources={','.join(result['meta']['sources'])}")
    for row in result["data"][:20]:
        print(f"{row.get('symbol')} | {row.get('name')} | {row.get('exchange')}")
    if len(result["data"]) > 20:
        print(f"... 仅展示前20条，共 {len(result['data'])} 条")


if __name__ == "__main__":
    main()
