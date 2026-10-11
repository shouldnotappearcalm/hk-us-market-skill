import re
import os
import queue
import threading
import time
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
        digits = str(int(digits)).zfill(4)
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
    exchange = DEFAULT_US_EXCHANGE.get(ticker, "US")
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
    if m in {"US", "HK"} and c in {"fundamental", "sector"}:
        return ["yfinance", "yahooquery"]
    if m == "US" and c == "macro":
        return ["fred_reader", "fred_csv"]
    return ["yfinance"]


def call_source(fn, timeout):
    """Bound waiting for an external source without joining a stuck thread."""
    finished = queue.Queue()
    def run():
        try:
            finished.put((fn(), None))
        except Exception as exc:
            finished.put((None, exc))
    threading.Thread(target=run, daemon=True).start()
    try:
        value, error = finished.get(timeout=max(0.01, timeout))
    except queue.Empty:
        raise TimeoutError(f"source timeout after {timeout:.2f}s")
    if error is not None:
        raise error
    return value


def pick_first_available(data_by_source: Dict[str, Any], chain: List[str]) -> Dict[str, Any]:
    disabled = {x.strip() for x in os.environ.get("HKUS_DISABLE_SOURCES", "").split(",") if x.strip()}
    visited, errors, timings = [], {}, {}
    source_timeout = max(0.1, min(60, float(os.environ.get("HKUS_SOURCE_TIMEOUT", "6"))))
    deadline = time.monotonic() + max(0.1, min(60, float(os.environ.get("HKUS_MAX_SECONDS", "25"))))
    for source in chain:
        visited.append(source)
        if source in disabled:
            errors[source] = "disabled"
            continue
        if time.monotonic() >= deadline:
            errors[source] = "overall deadline exceeded"
            break
        started = time.monotonic()
        try:
            value = data_by_source.get(source)
            if callable(value):
                value = call_source(value, min(source_timeout, deadline - time.monotonic()))
            if value is None or value == [] or value == {}:
                errors[source] = "empty response"
                continue
            return {"source_primary": chain[0], "source_actual": source,
                    "fallback_used": source != chain[0], "fallback_chain": visited.copy(),
                    "source_errors": errors, "source_elapsed_sec": dict(timings, **{source: round(time.monotonic()-started, 3)}),
                    "data": value}
        except Exception as exc:
            errors[source] = f"{type(exc).__name__}: {str(exc)[:220]}"
        finally:
            timings[source] = round(time.monotonic() - started, 3)
    raise ValueError("source_unavailable: " + str(errors))


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
        "source_errors": source_payload.get("source_errors", {}),
        "source_elapsed_sec": source_payload.get("source_elapsed_sec", {}),
    }
    if extra:
        payload.update(extra)
    return payload
