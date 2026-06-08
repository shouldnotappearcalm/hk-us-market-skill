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

US_TENCENT_KLINE_SUFFIX = {
    "NASDAQ": ".OQ",
    "NYSE": ".N",
    "AMEX": ".A",
}


def _us_tencent_kline_code(ticker: str, exchange: str) -> str:
    suffix = US_TENCENT_KLINE_SUFFIX.get(exchange.upper(), ".OQ")
    return f"us{ticker}{suffix}"


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
        tencent_code = f"hk{digits.zfill(5)}"
        return {
            "market": "HK",
            "normalized": hk,
            "yahoo_symbol": hk,
            "display_symbol": hk,
            "tencent_code": tencent_code,
            "tencent_kline_code": tencent_code,
            "sina_code": tencent_code,
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
            "exchange": exchange,
            "tencent_code": f"us{ticker}",
            "tencent_kline_code": _us_tencent_kline_code(ticker, exchange),
            "sina_code": f"gb_{ticker.lower()}",
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
        "exchange": exchange,
        "tencent_code": f"us{ticker}",
        "tencent_kline_code": _us_tencent_kline_code(ticker, exchange),
        "sina_code": f"gb_{ticker.lower()}",
    }


_YAHOO_HISTORY_CHAIN = ["yfinance", "yahooquery_history", "yahoo_chart"]
_YAHOO_REALTIME_CHAIN = ["yahooquery_realtime", "yfinance", "yahoo_chart"]


def build_fallback_chain(market: str, capability: str) -> List[str]:
    m = market.upper()
    c = capability.lower()
    if m in {"US", "HK"} and c in {"history", "realtime", "technical"}:
        if c in {"history", "technical"}:
            return ["tencent_history", "sina_history", *_YAHOO_HISTORY_CHAIN]
        return ["tencent_quote", "sina_quote", *_YAHOO_REALTIME_CHAIN]
    if m == "US" and c in {"fundamental", "sector"}:
        return ["yfinance", "yahooquery"]
    if m == "US" and c == "macro":
        return ["fred_reader", "fred_csv"]
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
