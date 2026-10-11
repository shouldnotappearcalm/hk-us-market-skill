import re
import os
import queue
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

try:
    from .hkus_runtime import call_source, circuit_ready, source_result
except ImportError:
    from hkus_runtime import call_source, circuit_ready, source_result
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
    return f"us{ticker}{US_TENCENT_KLINE_SUFFIX.get(exchange.upper(), '')}"


def normalize_symbol(raw_symbol: str) -> Dict[str, str]:
    symbol = (raw_symbol or "").strip().upper()
    if not symbol:
        raise ValueError("symbol 不能为空")
    if symbol.endswith(".HK") or symbol.isdigit():
        digits = symbol.removesuffix(".HK")
        if not digits.isdigit() or not 0 < int(digits) <= 99999:
            raise ValueError(f"无法识别港股代码: {raw_symbol}")
        digits = str(int(digits)).zfill(4)
        return {"market": "HK", "normalized": f"{digits}.HK", "yahoo_symbol": f"{digits}.HK",
                "display_symbol": f"{digits}.HK", "tencent_code": f"hk{digits.zfill(5)}",
                "tencent_kline_code": f"hk{digits.zfill(5)}", "sina_code": f"hk{digits.zfill(5)}"}
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if not re.fullmatch(r"[A-Z][A-Z0-9_-]{0,19}", exchange):
            raise ValueError(f"unsupported exchange: {exchange}")
    else:
        ticker = symbol
        exchange = DEFAULT_US_EXCHANGE.get(ticker, "US")
    if not re.fullmatch(r"[A-Z][A-Z0-9]*(?:[.-][A-Z0-9]+)?", ticker):
        raise ValueError(f"无法识别美股代码: {raw_symbol}")
    canonical = ticker.replace("-", ".")
    yahoo = canonical.replace(".", "-")
    return {"market": "US", "normalized": f"{exchange}:{canonical}", "yahoo_symbol": yahoo,
            "display_symbol": f"{exchange}:{canonical}", "exchange": exchange, "exchange_verified": False,
            "tencent_code": f"us{canonical}", "tencent_kline_code": _us_tencent_kline_code(canonical, exchange),
            "sina_code": f"gb_{canonical.lower()}"}


def market_timezone(market):
    return "Asia/Hong_Kong" if market == "HK" else "America/New_York"


def normalize_history_records(records, market, interval):
    """Daily bars use the exchange session date; intraday times retain an explicit offset."""
    import pandas as pd
    tz = market_timezone(market)
    rows = []
    for row in records or []:
        stamp = pd.Timestamp(row.get("time"))
        if pd.isna(stamp):
            raise ValueError("invalid bar timestamp")
        stamp = stamp.tz_localize(tz) if stamp.tzinfo is None else stamp.tz_convert(tz)
        trade_date = stamp.date().isoformat()
        if interval in ("1d", "1wk", "1mo"):
            stamp = stamp.normalize()
        rows.append(dict(row, time=stamp.isoformat(), trade_date=trade_date))
    return sorted(rows, key=lambda row: row["time"])


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


def pick_first_available(data_by_source: Dict[str, Any], chain: List[str], validator=None, health_scope="default") -> Dict[str, Any]:
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
        health_key = (health_scope, source)
        if not circuit_ready(health_key):
            errors[source] = "circuit_open: repeated recent failures"
            continue
        started = time.monotonic()
        try:
            value = data_by_source.get(source)
            if callable(value):
                value = call_source(value, min(source_timeout, deadline - time.monotonic()))
            if value is None or value == [] or value == {}:
                raise ValueError("empty response")
            if validator is not None:
                validator(value, source)
            source_result(health_key, True)
            return {"source_primary": chain[0], "source_actual": source,
                    "fallback_used": source != chain[0], "fallback_chain": visited.copy(),
                    "source_errors": errors, "source_elapsed_sec": dict(timings, **{source: round(time.monotonic()-started, 3)}),
                    "data": value}
        except Exception as exc:
            source_result(health_key, False)
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
        "exchange_verified": symbol_info.get("exchange_verified") if symbol_info.get("market") == "US" else None,
        "source_primary": source_payload["source_primary"],
        "source_actual": source_payload["source_actual"],
        "fallback_used": source_payload["fallback_used"],
        "fallback_chain": source_payload["fallback_chain"],
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "data": source_payload["data"],
        "source_errors": source_payload.get("source_errors", {}),
        "source_elapsed_sec": source_payload.get("source_elapsed_sec", {}),
    }
    if timeframe == "realtime" and isinstance(payload["data"], dict):
        try:
            from .hkus_calendar import regular_session_state
        except ImportError:
            from hkus_calendar import regular_session_state
        try:
            state = regular_session_state(symbol_info["market"])
            payload["data"] = dict(payload["data"])
            payload["data"]["market_state_provider"] = payload["data"].get("market_state", "UNKNOWN")
            payload["data"]["regular_session_state"] = state
            if state in ("CLOSED", "BREAK") and payload["data"].get("market_state") == "REGULAR":
                payload["data"]["market_state"] = state
        except (ImportError, ValueError) as exc:
            payload["calendar_error"] = str(exc)
    if extra:
        payload.update(extra)
    return payload
