import re
import os
from datetime import datetime
from typing import Any, Dict, List, Optional


DEFAULT_US_EXCHANGE = {
    "AAPL": "NASDAQ",
    "MSFT": "NASDAQ",
    "NVDA": "NASDAQ",
    "AMZN": "NASDAQ",
    "TSLA": "NASDAQ",
    "META": "NASDAQ",
    "GOOGL": "NASDAQ",
    "SPY": "NYSE",
    "QQQ": "NASDAQ",
}


def normalize_symbol(raw_symbol: str) -> Dict[str, str]:
    symbol = (raw_symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol 不能为空")

    if symbol.endswith(".HK") or symbol.isdigit():
        digits = re.sub(r"[^0-9]", "", symbol)
        if not digits:
            raise ValueError(f"无法识别港股代码: {raw_symbol}")
        digits = digits.zfill(4)
        hk = f"{digits}.HK"
        return {
            "market": "HK",
            "normalized": hk,
            "yahoo_symbol": hk,
            "display_symbol": hk,
        }

    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        ticker = ticker.strip().upper()
        exchange = exchange.strip().upper()
        if not ticker:
            raise ValueError(f"无法识别美股代码: {raw_symbol}")
        normalized = f"{exchange}:{ticker}"
        return {
            "market": "US",
            "normalized": normalized,
            "yahoo_symbol": ticker,
            "display_symbol": normalized,
        }

    ticker = re.sub(r"[^A-Z]", "", symbol)
    if not ticker:
        raise ValueError(f"无法识别代码: {raw_symbol}")
    exchange = DEFAULT_US_EXCHANGE.get(ticker, "NASDAQ")
    normalized = f"{exchange}:{ticker}"
    return {
        "market": "US",
        "normalized": normalized,
        "yahoo_symbol": ticker,
        "display_symbol": normalized,
    }


def build_fallback_chain(market: str, capability: str) -> List[str]:
    m = market.upper()
    c = capability.lower()
    if m == "US" and c in {"history", "realtime", "technical"}:
        return ["yfinance", "yahooquery_history", "yahoo_chart"]
    if m == "US" and c in {"fundamental", "sector"}:
        return ["yfinance", "yahooquery"]
    if m == "US" and c == "macro":
        return ["fred_reader", "fred_csv"]
    if m == "HK" and c in {"history", "technical"}:
        return ["yfinance", "yahoo_chart"]
    if m == "HK" and c == "realtime":
        return ["yfinance", "yahoo_chart", "tencent_quote"]
    return ["yfinance"]


def pick_first_available(data_by_source: Dict[str, Any], chain: List[str]) -> Dict[str, Any]:
    disabled_raw = os.environ.get("HKUS_DISABLE_SOURCES", "")
    disabled = {x.strip() for x in disabled_raw.split(",") if x.strip()}
    visited = []
    for source in chain:
        visited.append(source)
        if source in disabled:
            continue
        value = data_by_source.get(source)
        if value is not None:
            return {
                "source_primary": chain[0],
                "source_actual": source,
                "fallback_used": source != chain[0],
                "fallback_chain": visited.copy(),
                "data": value,
            }
    raise ValueError(f"source_unavailable: {','.join(chain)}")


def build_response(
    symbol_info: Dict[str, str],
    timeframe: str,
    source_payload: Dict[str, Any],
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    payload = {
        "symbol": symbol_info["normalized"],
        "market": symbol_info["market"],
        "timeframe": timeframe,
        "source_primary": source_payload["source_primary"],
        "source_actual": source_payload["source_actual"],
        "fallback_used": source_payload["fallback_used"],
        "fallback_chain": source_payload["fallback_chain"],
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "data": source_payload["data"],
    }
    if extra:
        payload.update(extra)
    return payload
