from __future__ import annotations

import re
import threading
from zoneinfo import ZoneInfo
from datetime import datetime, timedelta
from io import StringIO
from typing import Dict, List, Optional

import pandas as pd
import requests


SECTOR_ETF_MAP = {
    "technology": "XLK",
    "tech": "XLK",
    "金融": "XLF",
    "financials": "XLF",
    "healthcare": "XLV",
    "医疗": "XLV",
    "energy": "XLE",
    "能源": "XLE",
    "semiconductor": "SOXX",
    "半导体": "SOXX",
    "biotech": "XBI",
    "生物技术": "XBI",
    "cloud": "SKYY",
    "云计算": "SKYY",
    "ai": "AIQ",
    "人工智能": "AIQ",
    "cybersecurity": "HACK",
    "网络安全": "HACK",
    "real estate": "XLRE",
    "房地产": "XLRE",
}

FRED_SERIES = {
    "DGS2": "2Y Treasury",
    "DGS10": "10Y Treasury",
    "FEDFUNDS": "Fed Funds",
    "CPIAUCSL": "CPI",
    "UNRATE": "Unemployment Rate",
    "GDPC1": "Real GDP",
}

TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
TENCENT_DAY_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
TENCENT_MINUTE_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"
SINA_QUOTE_URL = "https://hq.sinajs.cn/list="
SINA_KLINE_URL = "https://quotes.sina.cn/cn/api/json_v2.php/CN_MarketDataService.getKLineData"
SINA_HK_MINLINE_URL = "https://quotes.sina.cn/hk/api/openapi.php/HK_MinlineService.getMinline"

TENCENT_INTERVAL_MAP = {"1d": "day", "1wk": "week", "1mo": "month"}
TENCENT_MINUTE_INTERVALS = {"1m", "5m", "15m", "30m", "60m"}
SINA_SCALE_MAP = {"1d": 240, "1wk": 1200, "1mo": 7200}

_TENCENT_US_STATUS = {
    "100": "PRE",
    "101": "PRE",
    "102": "PRE",
    "200": "REGULAR",
    "300": "POST",
    "400": "CLOSED",
}


_HTTP = threading.local()


def _http_session() -> requests.Session:
    if hasattr(_HTTP, "session"):
        return _HTTP.session
    session = requests.Session()
    session.trust_env = False
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": "https://finance.sina.com.cn/",
        }
    )
    _HTTP.session = session
    return session


def _safe_float(value) -> Optional[float]:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _market_state_from_sina_us_time(quote_time: Optional[str]) -> str:
    if not quote_time or " " not in quote_time:
        return "UNKNOWN"
    try:
        clock = quote_time.split(" ")[1]
        hour, minute = [int(x) for x in clock.split(":")[:2]]
        mins = hour * 60 + minute
        if 16 * 60 <= mins < 21 * 60 + 30:
            return "PRE"
        if mins >= 21 * 60 + 30 or mins < 4 * 60:
            return "REGULAR"
        if 4 * 60 <= mins < 8 * 60:
            return "POST"
        return "CLOSED"
    except Exception:
        return "UNKNOWN"


def _market_state_from_tencent(status_code: str, market: str) -> str:
    code = str(status_code or "").strip()
    if market == "US":
        return _TENCENT_US_STATUS.get(code, "UNKNOWN")
    if code in {"100", "400"}:
        return "CLOSED"
    if code == "200":
        return "REGULAR"
    if code in {"101", "102"}:
        return "PRE"
    if code == "300":
        return "POST"
    return "UNKNOWN"


def _build_realtime_payload(
    *,
    price: float,
    prev_close: float,
    open_v: Optional[float],
    high: Optional[float],
    low: Optional[float],
    volume: Optional[int],
    market_state: str = "UNKNOWN",
    premarket: Optional[Dict] = None,
    name: Optional[str] = None,
    currency: Optional[str] = None,
    quote_time: Optional[str] = None,
) -> Dict:
    change = price - prev_close
    change_pct = (change / prev_close * 100) if prev_close else 0.0
    payload = {
        "price": round(price, 4),
        "open": open_v,
        "high": high,
        "low": low,
        "previous_close": round(prev_close, 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 4),
        "volume": volume,
        "market_state": market_state,
        "premarket": premarket,
    }
    if name:
        payload["name"] = name
    if currency:
        payload["currency"] = currency
    if quote_time:
        payload["quote_time"] = quote_time
    return payload


def _ensure_yfinance():
    import yfinance as yf

    return yf


def _to_records(df: pd.DataFrame, limit: Optional[int] = None) -> List[Dict]:
    if df is None or df.empty:
        return []
    out = df.copy()
    if limit:
        out = out.tail(limit)
    out = out.reset_index()
    rename_map = {out.columns[0]: "time"}
    out = out.rename(columns=rename_map)
    if "time" in out.columns:
        out["time"] = pd.to_datetime(out["time"], errors="coerce").dt.strftime("%Y-%m-%d %H:%M:%S")
    numeric_cols = [c for c in out.columns if c != "time"]
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.astype(object).where(pd.notna(out), None).to_dict(orient="records")


def fetch_yfinance_history(yahoo_symbol: str, interval: str, days: int) -> Optional[List[Dict]]:
    yf = _ensure_yfinance()
    ticker = yf.Ticker(yahoo_symbol)
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    hist = ticker.history(start=start, interval=interval, auto_adjust=False)
    if hist is None or hist.empty:
        return None
    cols = ["Open", "High", "Low", "Close", "Volume"]
    hist = hist[cols].rename(columns=str.lower)
    return _to_records(hist)


def fetch_stooq_history(yahoo_symbol: str, days: int) -> Optional[List[Dict]]:
    try:
        from pandas_datareader import data as pdr
    except Exception:
        return None
    symbol = yahoo_symbol
    if symbol.endswith(".HK"):
        return None
    start = datetime.now() - timedelta(days=days)
    end = datetime.now()
    try:
        df = pdr.DataReader(symbol, "stooq", start=start, end=end)
        if df is None or df.empty:
            return None
        df = df.sort_index()
        df = df.rename(columns=str.lower)
        return _to_records(df[["open", "high", "low", "close", "volume"]])
    except Exception:
        return None


def fetch_yahoo_chart_history(yahoo_symbol: str, interval: str, days: int) -> Optional[List[Dict]]:
    period2 = int(datetime.now().timestamp())
    period1 = int((datetime.now() - timedelta(days=days)).timestamp())
    params = {"interval": interval, "period1": period1, "period2": period2}
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json,text/plain,*/*"}
    hosts = ["query1.finance.yahoo.com", "query2.finance.yahoo.com"]
    payload = None
    for host in hosts:
        try:
            url = f"https://{host}/v8/finance/chart/{yahoo_symbol}"
            resp = requests.get(url, params=params, headers=headers, timeout=15)
            resp.raise_for_status()
            payload = resp.json()
            if payload:
                break
        except Exception:
            payload = None
            continue
    if payload is None:
        return None
    try:
        result = ((payload or {}).get("chart", {}).get("result") or [None])[0]
        if not result:
            return None
        ts = result.get("timestamp") or []
        quote = ((result.get("indicators", {}).get("quote") or [None])[0]) or {}
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        vols = quote.get("volume") or []
        size = min(len(ts), len(opens), len(highs), len(lows), len(closes), len(vols))
        out = []
        for idx in range(size):
            t = ts[idx]
            open_v = opens[idx]
            high_v = highs[idx]
            low_v = lows[idx]
            close_v = closes[idx]
            vol_v = vols[idx]
            if close_v is None:
                continue
            out.append(
                {
                    "time": datetime.fromtimestamp(t).strftime("%Y-%m-%d %H:%M:%S"),
                    "open": open_v,
                    "high": high_v,
                    "low": low_v,
                    "close": close_v,
                    "volume": vol_v,
                }
            )
        return out or None
    except Exception:
        return None


def fetch_yahooquery_history(yahoo_symbol: str, interval: str, days: int) -> Optional[List[Dict]]:
    try:
        from yahooquery import Ticker
    except Exception:
        return None
    start = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    try:
        ticker = Ticker(yahoo_symbol)
        df = ticker.history(start=start, interval=interval)
        if df is None or len(df) == 0:
            return None
        if isinstance(df.index, pd.MultiIndex):
            symbol_level = df.index.get_level_values(0)
            time_level = df.index.get_level_values(1)
            df = df.copy()
            df["time"] = pd.to_datetime(time_level, errors="coerce")
            df["symbol"] = symbol_level
            df = df[df["symbol"] == yahoo_symbol]
            df = df.drop(columns=["symbol"])
            df = df.set_index("time")
        cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        if not cols:
            return None
        out = df[cols].copy().dropna(subset=["close"])
        return _to_records(out)
    except Exception:
        return None


def _extract_realtime_from_records(records: List[Dict]) -> Optional[Dict]:
    if not records:
        return None
    df = pd.DataFrame(records)
    if df.empty or "close" not in df.columns:
        return None
    df = df.dropna(subset=["close"])
    if len(df) < 1:
        return None
    latest = df.iloc[-1]
    prev_close = df.iloc[-2]["close"] if len(df) > 1 else latest["close"]
    change = float(latest["close"]) - float(prev_close)
    change_pct = (change / float(prev_close) * 100) if prev_close else 0.0
    return {
        "price": float(latest["close"]),
        "open": float(latest["open"]) if pd.notna(latest.get("open")) else None,
        "high": float(latest["high"]) if pd.notna(latest.get("high")) else None,
        "low": float(latest["low"]) if pd.notna(latest.get("low")) else None,
        "previous_close": float(prev_close),
        "change": round(change, 4),
        "change_pct": round(change_pct, 4),
        "volume": int(latest["volume"]) if pd.notna(latest.get("volume")) else None,
    }


def fetch_yfinance_realtime(yahoo_symbol: str) -> Optional[Dict]:
    intraday = fetch_yfinance_history(yahoo_symbol, "1d", 7)
    return _extract_realtime_from_records(intraday or [])


def fetch_yahoo_chart_realtime(yahoo_symbol: str) -> Optional[Dict]:
    intraday = fetch_yahoo_chart_history(yahoo_symbol, "1d", 7)
    return _extract_realtime_from_records(intraday or [])


def _parse_tencent_quote_line(line: str, market: str) -> Optional[Dict]:
    if "~" not in line:
        return None
    try:
        body = line.split('"', 1)[1].rsplit('"', 1)[0]
        arr = body.split("~")
        if len(arr) < 35:
            return None
        status_code = arr[0]
        name = arr[1] or None
        market_state = _market_state_from_tencent(status_code, market)
        if market == "HK":
            price = _safe_float(arr[3])
            prev_close = _safe_float(arr[4])
            open_v = _safe_float(arr[5])
            volume_raw = _safe_float(arr[6])
            high = _safe_float(arr[33])
            low = _safe_float(arr[34])
            currency = "HKD"
        else:
            price = _safe_float(arr[3])
            prev_close = _safe_float(arr[4])
            open_v = _safe_float(arr[5])
            volume_raw = _safe_float(arr[6])
            high = _safe_float(arr[33])
            low = _safe_float(arr[34])
            currency = arr[35] if len(arr) > 35 and arr[35] else "USD"
        if price is None or prev_close is None or price <= 0 or prev_close <= 0:
            return None
        volume = int(volume_raw) if volume_raw is not None else None
        quote_time = arr[30] if len(arr) > 30 and arr[30] else None
        if datetime.now(ZoneInfo("America/New_York" if market == "US" else "Asia/Hong_Kong")).weekday() >= 5:
            market_state = "CLOSED"
        premarket = None
        if market == "US" and market_state == "PRE":
            premarket = {
                "price": round(price, 4),
                "change": round(price - prev_close, 4),
                "change_pct": round((price - prev_close) / prev_close * 100, 4) if prev_close else 0.0,
                "time": quote_time,
            }
        return _build_realtime_payload(
            price=price,
            prev_close=prev_close,
            open_v=open_v,
            high=high,
            low=low,
            volume=volume,
            market_state=market_state,
            premarket=premarket,
            name=name,
            currency=currency,
            quote_time=quote_time,
        )
    except Exception:
        return None


def fetch_tencent_quote(symbol_info: Dict) -> Optional[Dict]:
    market = symbol_info["market"]
    code = symbol_info.get("tencent_code")
    if not code:
        if market == "HK":
            digits = re.sub(r"[^0-9]", "", symbol_info["yahoo_symbol"])
            code = f"hk{digits.zfill(5)}"
        else:
            code = f"us{symbol_info['yahoo_symbol']}"
    try:
        resp = _http_session().get(f"{TENCENT_QUOTE_URL}{code}", timeout=10)
        return _parse_tencent_quote_line(resp.text, market)
    except Exception:
        return None


def _hk_sina_quote_codes(symbol_info: Dict) -> List[str]:
    code = symbol_info.get("sina_code") or ""
    codes = []
    if code.startswith("hk"):
        codes.append(f"rt_{code}")
    if code:
        codes.append(code)
    return codes


def _parse_sina_quote_line(line: str, market: str) -> Optional[Dict]:
    if '="' not in line:
        return None
    try:
        body = line.split('="', 1)[1].rsplit('"', 1)[0]
        arr = body.split(",")
        if market == "HK":
            if len(arr) < 13:
                return None
            name = arr[1] or arr[0]
            price = _safe_float(arr[2])
            open_v = _safe_float(arr[3])
            high = _safe_float(arr[4])
            low = _safe_float(arr[5])
            prev_close = _safe_float(arr[6])
            volume_raw = _safe_float(arr[12])
            quote_time = f"{arr[17]} {arr[18]}" if len(arr) > 18 else None
            currency = "HKD"
            market_state = "REGULAR"
        else:
            if len(arr) < 11:
                return None
            name = arr[0]
            price = _safe_float(arr[1])
            prev_close = _safe_float(arr[5])
            open_v = _safe_float(arr[6])
            low = _safe_float(arr[7])
            high = _safe_float(arr[8])
            volume_raw = _safe_float(arr[10])
            quote_time = arr[3] if len(arr) > 3 else None
            currency = "USD"
            market_state = _market_state_from_sina_us_time(quote_time)
        if price is None or prev_close is None or price <= 0 or prev_close <= 0:
            return None
        volume = int(volume_raw) if volume_raw is not None else None
        change = _safe_float(arr[7]) if len(arr) > 7 else None
        change_pct = _safe_float(arr[8]) if len(arr) > 8 else None
        if market == "HK" and change is not None and change_pct is not None:
            payload_change = round(change, 4)
            payload_change_pct = round(change_pct, 4)
        else:
            payload_change = round(price - prev_close, 4)
            payload_change_pct = round((price - prev_close) / prev_close * 100, 4) if prev_close else 0.0
        premarket = None
        if market == "US" and market_state == "PRE":
            premarket = {
                "price": round(price, 4),
                "change": round(price - prev_close, 4),
                "change_pct": round((price - prev_close) / prev_close * 100, 4) if prev_close else 0.0,
                "time": quote_time,
            }
        payload = _build_realtime_payload(
            price=price,
            prev_close=prev_close,
            open_v=open_v,
            high=high,
            low=low,
            volume=volume,
            market_state=market_state,
            premarket=premarket,
            name=name,
            currency=currency,
            quote_time=quote_time,
        )
        payload["change"] = payload_change
        payload["change_pct"] = payload_change_pct
        return payload
    except Exception:
        return None


def fetch_sina_quote(symbol_info: Dict) -> Optional[Dict]:
    market = symbol_info.get("market")
    codes = _hk_sina_quote_codes(symbol_info) if market == "HK" else [symbol_info.get("sina_code")]
    for code in codes:
        if not code:
            continue
        try:
            resp = _http_session().get(f"{SINA_QUOTE_URL}{code}", timeout=10)
            parsed = _parse_sina_quote_line(resp.text, market)
            if parsed:
                return parsed
        except Exception:
            continue
    return None


def _resolve_tencent_kline_code(symbol_info: Dict) -> Optional[str]:
    market = symbol_info.get("market")
    if market == "HK":
        return symbol_info.get("tencent_code")
    preset = symbol_info.get("tencent_kline_code")
    quote_code = symbol_info.get("tencent_code") or f"us{symbol_info.get('yahoo_symbol', '')}"
    try:
        resp = _http_session().get(f"{TENCENT_QUOTE_URL}{quote_code}", timeout=10)
        line = resp.text
        if "~" not in line:
            return preset
        body = line.split('"', 1)[1].rsplit('"', 1)[0]
        arr = body.split("~")
        quote_sym = arr[2] if len(arr) > 2 and arr[2] else None
        if quote_sym:
            return f"us{quote_sym}"
    except Exception:
        pass
    return preset


def _extract_tencent_kline_rows(node: Dict, unit: str) -> List:
    if not isinstance(node, dict):
        return []
    rows = node.get(unit) or node.get(f"qfq{unit}") or []
    return rows if isinstance(rows, list) else []


def _records_from_tencent_kline(rows: List) -> List[Dict]:
    out = []
    for row in rows or []:
        if not isinstance(row, (list, tuple)) or len(row) < 6:
            continue
        day, open_v, close_v, high_v, low_v, vol = row[:6]
        if close_v in (None, ""):
            continue
        out.append(
            {
                "time": f"{day} 00:00:00" if len(str(day)) <= 10 else str(day),
                "open": _safe_float(open_v),
                "high": _safe_float(high_v),
                "low": _safe_float(low_v),
                "close": _safe_float(close_v),
                "volume": int(_safe_float(vol) or 0),
            }
        )
    return out


def _fetch_tencent_fqkline(code: str, unit: str, days: int) -> Optional[List[Dict]]:
    count = max(30, min(1023, days + 10))
    start_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    param_candidates = [
        f"{code},{unit},,,{count},qfq",
        f"{code},{unit},{start_date},,{count},qfq",
        f"{code},{unit},{start_date},{datetime.now().strftime('%Y-%m-%d')},{count},qfq",
    ]
    min_bars = 10 if unit == "day" else 4
    best: List[Dict] = []
    for param in param_candidates:
        try:
            resp = _http_session().get(f"{TENCENT_DAY_URL}?param={param}", timeout=15)
            payload = resp.json()
            node = (payload or {}).get("data", {}).get(code, {})
            rows = _extract_tencent_kline_rows(node, unit)
            records = _records_from_tencent_kline(rows)
            if len(records) > len(best):
                best = records
            if len(records) >= min_bars:
                return records
        except Exception:
            continue
    return best or None


def _records_from_tencent_minute(lines: List[str], trade_date: str) -> List[Dict]:
    out = []
    prev_cum_vol = 0
    for line in lines or []:
        parts = str(line).split()
        if len(parts) < 3:
            continue
        clock, price_raw, vol_raw = parts[0], parts[1], parts[2]
        if not clock.isdigit() or len(clock) < 3:
            continue
        price = _safe_float(price_raw)
        cum_vol = int(_safe_float(vol_raw) or 0)
        if price is None:
            continue
        minute_vol = max(cum_vol - prev_cum_vol, 0) if prev_cum_vol else cum_vol
        prev_cum_vol = cum_vol
        hh = clock.zfill(4)[:2]
        mm = clock.zfill(4)[2:4]
        day = trade_date
        if len(trade_date) == 8 and trade_date.isdigit():
            day = f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}"
        out.append(
            {
                "time": f"{day} {hh}:{mm}:00",
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": minute_vol,
            }
        )
    return out


def fetch_tencent_minute(symbol_info: Dict) -> Optional[List[Dict]]:
    code = symbol_info.get("tencent_code")
    if not code:
        return None
    try:
        resp = _http_session().get(f"{TENCENT_MINUTE_URL}?code={code}", timeout=15)
        payload = resp.json()
        node = (payload or {}).get("data", {}).get(code, {})
        minute_node = node.get("data") if isinstance(node, dict) else {}
        lines = minute_node.get("data") if isinstance(minute_node, dict) else []
        trade_date = str(minute_node.get("date") or datetime.now().strftime("%Y%m%d"))
        records = _records_from_tencent_minute(lines, trade_date)
        if records:
            return records
        if symbol_info.get("market") == "US" and len(lines) == 1:
            records = _records_from_tencent_minute(lines, datetime.now().strftime("%Y%m%d"))
            return records or None
        return None
    except Exception:
        return None


def fetch_tencent_history(symbol_info: Dict, interval: str, days: int) -> Optional[List[Dict]]:
    if interval in TENCENT_MINUTE_INTERVALS:
        return fetch_tencent_minute(symbol_info)
    unit = TENCENT_INTERVAL_MAP.get(interval)
    if not unit:
        return None
    code = _resolve_tencent_kline_code(symbol_info)
    if not code:
        return None
    records = _fetch_tencent_fqkline(code, unit, days)
    min_bars = 10 if interval == "1d" else 4
    if not records or len(records) < min_bars:
        return None
    return records


def _records_from_sina_kline(items: List[Dict]) -> List[Dict]:
    out = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        close_v = _safe_float(item.get("close"))
        if close_v is None:
            continue
        day = item.get("day") or item.get("date")
        out.append(
            {
                "time": str(day),
                "open": _safe_float(item.get("open")),
                "high": _safe_float(item.get("high")),
                "low": _safe_float(item.get("low")),
                "close": close_v,
                "volume": int(_safe_float(item.get("volume")) or 0),
            }
        )
    return out


def _fetch_sina_kline_api(symbol_code: str, interval: str, count: int) -> Optional[List[Dict]]:
    scale = SINA_SCALE_MAP.get(interval)
    if scale is None:
        return None
    params = {"symbol": symbol_code, "scale": scale, "datalen": min(1023, count), "ma": "no"}
    try:
        resp = _http_session().get(SINA_KLINE_URL, params=params, timeout=15)
        data = resp.json()
        if not data or isinstance(data, dict):
            return None
        return _records_from_sina_kline(data)
    except Exception:
        return None


def _fetch_sina_hk_minline_groups(symbol_digits: str, days: int) -> List:
    params = {"symbol": symbol_digits, "day": max(5, min(60, days // 5 + 5))}
    try:
        resp = _http_session().get(SINA_HK_MINLINE_URL, params=params, timeout=20)
        payload = resp.json()
        return ((payload or {}).get("result") or {}).get("data") or []
    except Exception:
        return []


def _records_from_sina_hk_minline(groups: List, trade_day: Optional[str] = None) -> List[Dict]:
    out = []
    for day_rows in groups or []:
        if not day_rows:
            continue
        first = day_rows[0]
        day = first.get("date")
        if trade_day and day != trade_day:
            continue
        for row in day_rows:
            clock = str(row.get("m") or "")
            price = _safe_float(row.get("price"))
            minute_vol = int(_safe_float(row.get("volume")) or 0)
            if not clock or price is None:
                continue
            out.append(
                {
                    "time": f"{day} {clock}",
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "volume": minute_vol,
                }
            )
    return out


def _aggregate_hk_minline_to_daily(symbol_digits: str, days: int) -> Optional[List[Dict]]:
    groups = _fetch_sina_hk_minline_groups(symbol_digits, days)
    if not groups:
        return None
    bars = []
    try:
        for day_rows in groups:
            if not day_rows:
                continue
            first = day_rows[0]
            day = first.get("date")
            if not day:
                continue
            prices = [_safe_float(x.get("price")) for x in day_rows]
            vols = [int(_safe_float(x.get("volume")) or 0) for x in day_rows]
            prices = [p for p in prices if p is not None]
            if not prices:
                continue
            bars.append(
                {
                    "time": f"{day} 00:00:00",
                    "open": prices[0],
                    "high": max(prices),
                    "low": min(prices),
                    "close": prices[-1],
                    "volume": sum(vols),
                }
            )
        return bars or None
    except Exception:
        return None


def _hk_symbol_digits(symbol_info: Dict) -> Optional[str]:
    digits = re.sub(r"[^0-9]", "", symbol_info.get("yahoo_symbol", ""))
    if not digits:
        return None
    return digits.zfill(5)


def fetch_sina_hk_minute(symbol_info: Dict, days: int) -> Optional[List[Dict]]:
    digits = _hk_symbol_digits(symbol_info)
    if not digits:
        return None
    groups = _fetch_sina_hk_minline_groups(digits, days)
    records = _records_from_sina_hk_minline(groups)
    return records or None


def fetch_sina_history(symbol_info: Dict, interval: str, days: int) -> Optional[List[Dict]]:
    code = symbol_info.get("sina_code")
    if not code:
        return None
    if symbol_info["market"] == "HK" and interval in TENCENT_MINUTE_INTERVALS:
        records = fetch_sina_hk_minute(symbol_info, days)
        return records if records else None
    count = max(30, min(1023, days + 10))
    min_bars = 10 if interval == "1d" else 4
    records = _fetch_sina_kline_api(code, interval, count)
    if records and len(records) >= min_bars:
        return records
    if symbol_info["market"] == "HK" and interval == "1d":
        digits = _hk_symbol_digits(symbol_info)
        if not digits:
            return None
        aggregated = _aggregate_hk_minline_to_daily(digits, days)
        if aggregated and len(aggregated) >= 3:
            return aggregated
    return None


def fetch_yahooquery_realtime(yahoo_symbol: str) -> Optional[Dict]:
    try:
        from yahooquery import Ticker
    except Exception:
        return None
    try:
        ticker = Ticker(yahoo_symbol, asynchronous=False)
        prices = ticker.price
        data = prices.get(yahoo_symbol) if isinstance(prices, dict) else None
        if not isinstance(data, dict):
            return None
        market_state = str(data.get("marketState") or "UNKNOWN").upper()
        pre_price = _safe_float(data.get("preMarketPrice"))
        prev_close = _safe_float(data.get("regularMarketPreviousClose") or data.get("previousClose"))
        regular_price = _safe_float(data.get("regularMarketPrice"))
        post_price = _safe_float(data.get("postMarketPrice"))

        if market_state == "PRE" and pre_price is not None and prev_close:
            price = pre_price
        elif market_state == "POST" and post_price is not None and prev_close:
            price = post_price
        elif regular_price is not None:
            price = regular_price
        elif pre_price is not None:
            price = pre_price
            market_state = "PRE"
        else:
            return None

        if prev_close is None or prev_close <= 0:
            return None

        premarket = None
        if pre_price is not None and prev_close:
            premarket = {
                "price": round(pre_price, 4),
                "change": round(pre_price - prev_close, 4),
                "change_pct": round((pre_price - prev_close) / prev_close * 100, 4),
                "time": str(data.get("preMarketTime") or ""),
            }

        open_v = _safe_float(data.get("regularMarketOpen") or data.get("preMarketOpen"))
        high = _safe_float(data.get("regularMarketDayHigh") or data.get("preMarketDayHigh"))
        low = _safe_float(data.get("regularMarketDayLow") or data.get("preMarketDayLow"))
        volume_raw = data.get("regularMarketVolume") or data.get("preMarketVolume")
        volume = int(volume_raw) if volume_raw not in (None, 0) else None
        quote_time = data.get("regularMarketTime") or data.get("preMarketTime")

        return _build_realtime_payload(
            price=price,
            prev_close=prev_close,
            open_v=open_v,
            high=high,
            low=low,
            volume=volume,
            market_state=market_state,
            premarket=premarket,
            name=data.get("shortName") or data.get("longName"),
            currency=data.get("currency"),
            quote_time=str(quote_time) if quote_time else None,
        )
    except Exception:
        return None


def enrich_realtime_premarket(data: Optional[Dict], yahoo_symbol: str) -> Optional[Dict]:
    if not data:
        return data
    if data.get("premarket"):
        return data
    yq = fetch_yahooquery_realtime(yahoo_symbol)
    if yq and yq.get("premarket"):
        merged = dict(data)
        merged["premarket"] = yq["premarket"]
        if merged.get("market_state") in {None, "", "UNKNOWN"} and yq.get("market_state"):
            merged["market_state"] = yq["market_state"]
        return merged
    return data


def fetch_yfinance_fundamental(yahoo_symbol: str) -> Optional[Dict]:
    yf = _ensure_yfinance()
    ticker = yf.Ticker(yahoo_symbol)
    info = ticker.info or {}
    try:
        holders = ticker.institutional_holders
    except Exception:
        holders = None
    top_holders = []
    if holders is not None and not holders.empty:
        for _, row in holders.head(15).iterrows():
            top_holders.append(
                {
                    "holder": row.get("Holder"),
                    "shares": row.get("Shares"),
                    "date_reported": str(row.get("Date Reported")),
                    "percent_out": row.get("% Out"),
                }
            )
    data = {
        "currency": info.get("currency"),
        "market_cap": info.get("marketCap"),
        "pe_ttm": info.get("trailingPE"),
        "pe_forward": info.get("forwardPE"),
        "ps": info.get("priceToSalesTrailing12Months"),
        "pb": info.get("priceToBook"),
        "ev_ebitda": info.get("enterpriseToEbitda"),
        "peg": info.get("pegRatio"),
        "beta": info.get("beta"),
        "dividend_yield": info.get("dividendYield"),
        "sector": info.get("sector"),
        "industry": info.get("industry"),
        "institutional_holders": top_holders,
    }
    if all(v is None or v == [] for v in data.values()):
        return None
    return data


def fetch_yahooquery_fundamental(yahoo_symbol: str) -> Optional[Dict]:
    try:
        from yahooquery import Ticker
    except Exception:
        return None
    try:
        ticker = Ticker(yahoo_symbol)
        summary = ticker.summary_detail.get(yahoo_symbol) or {}
        profile = ticker.asset_profile.get(yahoo_symbol) or {}
        result = {
            "currency": summary.get("currency"),
            "market_cap": summary.get("marketCap"),
            "pe_ttm": summary.get("trailingPE"),
            "pe_forward": summary.get("forwardPE"),
            "ps": summary.get("priceToSalesTrailing12Months"),
            "pb": summary.get("priceToBook"),
            "beta": summary.get("beta"),
            "dividend_yield": summary.get("dividendYield"),
            "sector": profile.get("sector"),
            "industry": profile.get("industry"),
            "institutional_holders": [],
        }
        return result if any(v is not None and v != [] for v in result.values()) else None
    except Exception:
        return None


def fetch_sector_etf(sector_name: str, days: int = 30, etf_symbol: str = None) -> Optional[Dict]:
    key = (sector_name or "").strip().lower()
    etf = etf_symbol.strip().upper() if etf_symbol else SECTOR_ETF_MAP.get(key)
    if not etf:
        raise ValueError(f"unknown_sector: {sector_name}; provide --etf explicitly")
    try:
        from .hkus_common import normalize_symbol, build_fallback_chain, pick_first_available
    except ImportError:
        from hkus_common import normalize_symbol, build_fallback_chain, pick_first_available
    info = normalize_symbol(etf)
    chain = build_fallback_chain("US", "history")
    picked = pick_first_available({
        "tencent_history": lambda: fetch_tencent_history(info, "1d", days),
        "sina_history": lambda: fetch_sina_history(info, "1d", days),
        "yfinance": lambda: fetch_yfinance_history(etf, "1d", days),
        "yahooquery_history": lambda: fetch_yahooquery_history(etf, "1d", days),
        "yahoo_chart": lambda: fetch_yahoo_chart_history(etf, "1d", days),
    }, chain)
    bars = picked["data"]
    df = pd.DataFrame(bars).dropna(subset=["close"])
    if df.empty:
        return None
    start_close = float(df.iloc[0]["close"])
    end_close = float(df.iloc[-1]["close"])
    ret = ((end_close - start_close) / start_close * 100) if start_close else 0.0
    return {
        "sector_name": sector_name,
        "mapped_etf": etf,
        "proxy_type": "US ETF proxy, not actual industry constituents",
        "source_metadata": {k:v for k,v in picked.items() if k != "data"},
        "period_days": days,
        "period_return_pct": round(ret, 4),
        "bars": df.tail(60).to_dict(orient="records"),
    }


def _fred_reader_fetch(series_id: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    try:
        from pandas_datareader import data as pdr
    except Exception:
        return None
    try:
        df = pdr.DataReader(series_id, "fred", start, end)
        if df is None or df.empty:
            return None
        df = df.rename(columns={series_id: "value"})
        return df
    except Exception:
        return None


def _fred_csv_fetch(series_id: str, start: datetime, end: datetime) -> Optional[pd.DataFrame]:
    url = "https://fred.stlouisfed.org/graph/fredgraph.csv"
    try:
        resp = requests.get(
            url,
            params={
                "id": series_id,
                "cosd": start.strftime("%Y-%m-%d"),
                "coed": end.strftime("%Y-%m-%d"),
            },
            timeout=20,
        )
        resp.raise_for_status()
        df = pd.read_csv(StringIO(resp.text))
        if df.empty:
            return None
        date_col = "DATE" if "DATE" in df.columns else "observation_date"
        if date_col not in df.columns:
            return None
        value_col = [c for c in df.columns if c != date_col][0]
        df = df.rename(columns={date_col: "date", value_col: "value"})
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["date"])
        return df.set_index("date")
    except Exception:
        return None


def fetch_fred_series(series_id: str, lookback_days: int) -> Dict[str, Optional[List[Dict]]]:
    end = datetime.now()
    start = end - timedelta(days=lookback_days)
    # Keep the public source->records map, but query only until one source works.
    try:
        from .hkus_common import pick_first_available
    except ImportError:
        from hkus_common import pick_first_available
    def records(fn):
        df = fn(series_id, start, end)
        return _to_records(df, limit=500) if df is not None and not df.empty else None
    picked = pick_first_available({"fred_reader": lambda: records(_fred_reader_fetch),
                                   "fred_csv": lambda: records(_fred_csv_fetch)},
                                  ["fred_reader", "fred_csv"])
    return {"fred_reader": None, "fred_csv": None, picked["source_actual"]: picked["data"]}
