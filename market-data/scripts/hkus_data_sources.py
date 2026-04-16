from __future__ import annotations

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
    return out.to_dict(orient="records")


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


def fetch_tencent_quote(hk_symbol: str) -> Optional[Dict]:
    digits = hk_symbol.replace(".HK", "")
    code = digits.zfill(5)
    url = f"https://qt.gtimg.cn/q=hk{code}"
    try:
        resp = requests.get(url, timeout=10)
        text = resp.text
        if "~" not in text:
            return None
        body = text.split('"', 1)[1].rsplit('"', 1)[0]
        arr = body.split("~")
        if len(arr) < 10:
            return None
        price = float(arr[3])
        open_v = float(arr[5])
        high = float(arr[4])
        low = float(arr[6])
        prev_close = float(arr[4]) if float(arr[4]) else open_v
        change = price - prev_close
        change_pct = (change / prev_close * 100) if prev_close else 0.0
        return {
            "price": round(price, 4),
            "open": open_v,
            "high": high,
            "low": low,
            "previous_close": prev_close,
            "change": round(change, 4),
            "change_pct": round(change_pct, 4),
            "volume": None,
        }
    except Exception:
        return None


def fetch_yfinance_fundamental(yahoo_symbol: str) -> Optional[Dict]:
    yf = _ensure_yfinance()
    ticker = yf.Ticker(yahoo_symbol)
    info = ticker.info or {}
    holders = ticker.institutional_holders
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
        return {
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
    except Exception:
        return None


def fetch_sector_etf(sector_name: str, days: int = 30) -> Optional[Dict]:
    key = (sector_name or "").strip().lower()
    etf = SECTOR_ETF_MAP.get(key)
    if not etf:
        etf = "SPY"
    bars = fetch_yfinance_history(etf, "1d", days)
    if not bars:
        bars = fetch_yahoo_chart_history(etf, "1d", days)
    if not bars:
        return None
    df = pd.DataFrame(bars).dropna(subset=["close"])
    if df.empty:
        return None
    start_close = float(df.iloc[0]["close"])
    end_close = float(df.iloc[-1]["close"])
    ret = ((end_close - start_close) / start_close * 100) if start_close else 0.0
    return {
        "sector_name": sector_name,
        "mapped_etf": etf,
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
    reader_df = _fred_reader_fetch(series_id, start, end)
    csv_df = _fred_csv_fetch(series_id, start, end)
    result = {"fred_reader": None, "fred_csv": None}
    if reader_df is not None and not reader_df.empty:
        result["fred_reader"] = _to_records(reader_df, limit=500)
    if csv_df is not None and not csv_df.empty:
        result["fred_csv"] = _to_records(csv_df, limit=500)
    return result
