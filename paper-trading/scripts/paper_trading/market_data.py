#!/usr/bin/env python3
"""HK+US market data provider with local cache."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
import requests

from paper_trading_runtime import ensure_runtime_dir, get_quote_cache_path


@dataclass
class Quote:
    symbol: str
    name: str
    market: str
    price: float
    open: float
    high: float
    low: float
    prev_close: float
    volume: int
    change_pct: float
    timestamp: str
    source: str
    currency: str


def _now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _to_ts(v) -> str:
    return pd.to_datetime(v, errors="coerce").strftime("%Y-%m-%d %H:%M:%S")


class MarketDataProvider:
    def __init__(self, quote_cache_ttl_seconds: int = 20) -> None:
        ensure_runtime_dir()
        self._session = requests.Session()
        self._session.trust_env = False
        self._session.headers.update({"User-Agent": "Mozilla/5.0"})
        self._quote_cache_ttl_seconds = quote_cache_ttl_seconds
        self._quote_cache_path = get_quote_cache_path()

    def normalize_symbol(self, symbol: str) -> str:
        raw = (symbol or "").strip().upper()
        if not raw:
            raise ValueError("symbol is required")
        if raw.endswith(".HK") or raw.isdigit():
            digits = "".join(ch for ch in raw if ch.isdigit())
            if not digits:
                raise ValueError(f"invalid hk symbol: {symbol}")
            return f"{digits.zfill(4)}.HK"
        if ":" in raw:
            ex, ticker = raw.split(":", 1)
            ticker = ticker.strip().upper()
            ex = ex.strip().upper()
            if not ticker:
                raise ValueError(f"invalid us symbol: {symbol}")
            return f"{ex}:{ticker}"
        ticker = "".join(ch for ch in raw if ch.isalpha())
        if not ticker:
            raise ValueError(f"invalid symbol: {symbol}")
        return f"NASDAQ:{ticker}"

    def _market_of(self, symbol: str) -> str:
        return "HK" if symbol.endswith(".HK") else "US"

    def _yahoo_symbol(self, symbol: str) -> str:
        return symbol if symbol.endswith(".HK") else symbol.split(":")[1]

    def _read_quote_cache(self) -> Dict:
        p = Path(self._quote_cache_path)
        if not p.exists():
            return {}
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _write_quote_cache(self, cache: Dict) -> None:
        p = Path(self._quote_cache_path)
        p.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    def _get_cached_quote(self, symbol: str) -> Optional[Quote]:
        cache = self._read_quote_cache()
        item = cache.get(symbol)
        if not item:
            return None
        try:
            cached_at = pd.to_datetime(item.get("cached_at"))
        except Exception:
            return None
        if (datetime.now() - cached_at.to_pydatetime()).total_seconds() > self._quote_cache_ttl_seconds:
            return None
        try:
            q = item.get("quote") or {}
            return Quote(**q)
        except Exception:
            return None

    def _set_cached_quote(self, quote: Quote) -> None:
        cache = self._read_quote_cache()
        cache[quote.symbol] = {"cached_at": _now_str(), "quote": quote.__dict__}
        self._write_quote_cache(cache)

    def _get_quote_hk_tencent(self, normalized: str) -> Optional[Quote]:
        digits = "".join(ch for ch in normalized if ch.isdigit()).zfill(5)
        url = f"https://qt.gtimg.cn/q=hk{digits}"
        try:
            text = self._session.get(url, timeout=10).text
            if "~" not in text:
                return None
            body = text.split('"', 1)[1].rsplit('"', 1)[0]
            arr = body.split("~")
            if len(arr) < 10:
                return None
            price = float(arr[3]) if arr[3] else 0.0
            prev_close = float(arr[4]) if arr[4] else 0.0
            if price <= 0 or prev_close <= 0:
                return None
            open_v = float(arr[5]) if arr[5] else price
            high = float(arr[6]) if arr[6] else max(price, open_v)
            low = float(arr[7]) if arr[7] else min(price, open_v)
            change_pct = (price - prev_close) / prev_close * 100
            return Quote(
                symbol=normalized,
                name=arr[1] or normalized,
                market="HK",
                price=round(price, 4),
                open=round(open_v, 4),
                high=round(high, 4),
                low=round(low, 4),
                prev_close=round(prev_close, 4),
                volume=0,
                change_pct=round(change_pct, 4),
                timestamp=_now_str(),
                source="tencent_quote",
                currency="HKD",
            )
        except Exception:
            return None

    def _get_quote_yahooquery(self, normalized: str) -> Optional[Quote]:
        try:
            from yahooquery import Ticker
        except Exception:
            return None
        ticker = self._yahoo_symbol(normalized)
        try:
            tq = Ticker(ticker, asynchronous=True)
            data = tq.price.get(ticker) if isinstance(tq.price, dict) else None
            if not isinstance(data, dict):
                return None
            price = data.get("regularMarketPrice")
            prev_close = data.get("regularMarketPreviousClose")
            if price in (None, 0) or prev_close in (None, 0):
                return None
            open_v = data.get("regularMarketOpen") or price
            high = data.get("regularMarketDayHigh") or max(price, open_v)
            low = data.get("regularMarketDayLow") or min(price, open_v)
            volume = int(data.get("regularMarketVolume") or 0)
            change_pct = (float(price) - float(prev_close)) / float(prev_close) * 100
            name = data.get("shortName") or data.get("longName") or normalized
            currency = data.get("currency") or ("HKD" if normalized.endswith(".HK") else "USD")
            return Quote(
                symbol=normalized,
                name=name,
                market=self._market_of(normalized),
                price=round(float(price), 4),
                open=round(float(open_v), 4),
                high=round(float(high), 4),
                low=round(float(low), 4),
                prev_close=round(float(prev_close), 4),
                volume=volume,
                change_pct=round(change_pct, 4),
                timestamp=_now_str(),
                source="yahooquery_price",
                currency=currency,
            )
        except Exception:
            return None

    def _get_quote_yfinance(self, normalized: str) -> Optional[Quote]:
        try:
            import yfinance as yf
        except Exception:
            return None
        ticker = self._yahoo_symbol(normalized)
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="7d", interval="1d", auto_adjust=False)
            if hist is None or hist.empty:
                return None
            hist = hist.dropna(subset=["Close"])
            if hist.empty:
                return None
            last = hist.iloc[-1]
            prev = hist.iloc[-2] if len(hist) > 1 else hist.iloc[-1]
            close = float(last["Close"])
            prev_close = float(prev["Close"]) if float(prev["Close"]) != 0 else close
            open_v = float(last["Open"]) if pd.notna(last["Open"]) else close
            high = float(last["High"]) if pd.notna(last["High"]) else max(close, open_v)
            low = float(last["Low"]) if pd.notna(last["Low"]) else min(close, open_v)
            volume = int(last["Volume"]) if pd.notna(last["Volume"]) else 0
            change_pct = (close - prev_close) / prev_close * 100 if prev_close else 0.0
            return Quote(
                symbol=normalized,
                name=normalized,
                market=self._market_of(normalized),
                price=round(close, 4),
                open=round(open_v, 4),
                high=round(high, 4),
                low=round(low, 4),
                prev_close=round(prev_close, 4),
                volume=volume,
                change_pct=round(change_pct, 4),
                timestamp=_now_str(),
                source="yfinance",
                currency="HKD" if normalized.endswith(".HK") else "USD",
            )
        except Exception:
            return None

    def get_quote(self, symbol: str) -> Quote:
        normalized = self.normalize_symbol(symbol)
        cached = self._get_cached_quote(normalized)
        if cached:
            return cached

        quote = None
        if normalized.endswith(".HK"):
            quote = self._get_quote_hk_tencent(normalized)
        if quote is None:
            quote = self._get_quote_yahooquery(normalized)
        if quote is None:
            quote = self._get_quote_yfinance(normalized)
        if quote is None:
            raise ValueError(f"quote unavailable for {normalized}")

        self._set_cached_quote(quote)
        return quote

    def get_quotes(self, symbols: List[str]) -> Dict[str, Quote]:
        out = {}
        for symbol in symbols:
            normalized = self.normalize_symbol(symbol)
            out[normalized] = self.get_quote(normalized)
        return out

    def get_history(self, symbol: str, start: str | None = None, end: str | None = None, count: int = 240) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception as exc:
            raise ValueError("yfinance is required for history") from exc

        normalized = self.normalize_symbol(symbol)
        ticker = self._yahoo_symbol(normalized)
        if not start:
            start = (datetime.now() - timedelta(days=max(120, count * 2))).strftime("%Y-%m-%d")
        if not end:
            end = datetime.now().strftime("%Y-%m-%d")

        hist = yf.Ticker(ticker).history(start=start, end=end, interval="1d", auto_adjust=False)
        if hist is None or hist.empty:
            raise ValueError(f"history unavailable for {normalized}")
        hist = hist.reset_index()
        hist = hist.rename(columns={"Date": "time", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        hist["time"] = pd.to_datetime(hist["time"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            hist[col] = pd.to_numeric(hist[col], errors="coerce")
        hist = hist.dropna(subset=["time", "close"]).sort_values("time")
        return hist[["time", "open", "high", "low", "close", "volume"]].tail(count).reset_index(drop=True)

    def get_intraday_bars(self, symbol: str, freq: str = "1m", count: int = 240) -> pd.DataFrame:
        try:
            import yfinance as yf
        except Exception:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])

        normalized = self.normalize_symbol(symbol)
        ticker = self._yahoo_symbol(normalized)
        interval = "1m" if freq == "1m" else "5m"
        hist = yf.Ticker(ticker).history(period="5d", interval=interval, auto_adjust=False)
        if hist is None or hist.empty:
            return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
        out = hist.reset_index()
        out = out.rename(columns={out.columns[0]: "time", "Open": "open", "High": "high", "Low": "low", "Close": "close", "Volume": "volume"})
        out["time"] = pd.to_datetime(out["time"], errors="coerce")
        for col in ["open", "high", "low", "close", "volume"]:
            out[col] = pd.to_numeric(out[col], errors="coerce")
        out = out.dropna(subset=["time", "close"]).sort_values("time").tail(count)
        return out[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)
