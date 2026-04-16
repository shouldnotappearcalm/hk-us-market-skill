#!/usr/bin/env python3
import argparse
import json

import pandas as pd

try:
    from scripts.hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from scripts.hkus_data_sources import fetch_yahooquery_history, fetch_yahoo_chart_history, fetch_yfinance_history
except Exception:
    from hkus_common import build_fallback_chain, build_response, normalize_symbol, pick_first_available
    from hkus_data_sources import fetch_yahooquery_history, fetch_yahoo_chart_history, fetch_yfinance_history


def _get_history(symbol_info, days: int, interval: str):
    chain = build_fallback_chain(symbol_info["market"], "technical")
    data_map = {
        "yfinance": fetch_yfinance_history(symbol_info["yahoo_symbol"], interval, days),
        "yahooquery_history": fetch_yahooquery_history(symbol_info["yahoo_symbol"], interval, days),
        "yahoo_chart": fetch_yahoo_chart_history(symbol_info["yahoo_symbol"], interval, days),
    }
    return pick_first_available(data_map, chain)


def _calc_indicators(df: pd.DataFrame):
    df = df.copy()
    for ma in [5, 20, 60]:
        df[f"ma_{ma}"] = df["close"].rolling(ma).mean()

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    dif = ema12 - ema26
    dea = dif.ewm(span=9, adjust=False).mean()
    macd = dif - dea
    df["macd_dif"] = dif
    df["macd_dea"] = dea
    df["macd_hist"] = macd

    delta = df["close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / loss.replace(0, pd.NA)
    df["rsi_14"] = 100 - (100 / (1 + rs))

    mid = df["close"].rolling(20).mean()
    std = df["close"].rolling(20).std()
    df["boll_mid"] = mid
    df["boll_up"] = mid + 2 * std
    df["boll_low"] = mid - 2 * std

    low_n = df["low"].rolling(9).min()
    high_n = df["high"].rolling(9).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, pd.NA) * 100
    df["kdj_k"] = rsv.ewm(alpha=1 / 3, adjust=False).mean()
    df["kdj_d"] = df["kdj_k"].ewm(alpha=1 / 3, adjust=False).mean()
    df["kdj_j"] = 3 * df["kdj_k"] - 2 * df["kdj_d"]
    return df


def _signals(df: pd.DataFrame):
    if df.empty:
        return []
    last = df.iloc[-1]
    prev = df.iloc[-2] if len(df) > 1 else None
    out = []
    if pd.notna(last.get("ma_5")) and pd.notna(last.get("ma_20")) and pd.notna(last.get("ma_60")):
        if last["ma_5"] > last["ma_20"] > last["ma_60"]:
            out.append("均线多头排列")
        elif last["ma_5"] < last["ma_20"] < last["ma_60"]:
            out.append("均线空头排列")
    if prev is not None and pd.notna(prev.get("macd_dif")) and pd.notna(prev.get("macd_dea")):
        if prev["macd_dif"] <= prev["macd_dea"] and last["macd_dif"] > last["macd_dea"]:
            out.append("MACD 金叉")
        if prev["macd_dif"] >= prev["macd_dea"] and last["macd_dif"] < last["macd_dea"]:
            out.append("MACD 死叉")
    if pd.notna(last.get("rsi_14")):
        if last["rsi_14"] > 70:
            out.append("RSI 超买")
        elif last["rsi_14"] < 30:
            out.append("RSI 超卖")
    return out


def run(symbol: str, days: int, interval: str):
    symbol_info = normalize_symbol(symbol)
    picked = _get_history(symbol_info, days, interval)
    data = picked["data"] or []
    df = pd.DataFrame(data)
    if df.empty:
        raise ValueError("source_unavailable: 无可用K线数据")
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["time", "close"]).sort_values("time")
    calc_df = _calc_indicators(df)
    tail = calc_df.tail(120).copy()
    tail["time"] = tail["time"].dt.strftime("%Y-%m-%d %H:%M:%S")
    picked["data"] = {
        "series": tail.to_dict(orient="records"),
        "latest": tail.iloc[-1].to_dict() if not tail.empty else {},
        "signals": _signals(tail),
    }
    return build_response(symbol_info, interval, picked)


def main():
    parser = argparse.ArgumentParser(description="HK+US 技术指标（多渠道兜底）")
    parser.add_argument("symbol", help="标的，如 AAPL 或 0700.HK")
    parser.add_argument("--days", type=int, default=180)
    parser.add_argument("--interval", default="1d", choices=["1d", "1wk", "1mo"])
    parser.add_argument("--json", action="store_true", dest="output_json")
    args = parser.parse_args()

    result = run(args.symbol, args.days, args.interval)
    if args.output_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    latest = result["data"]["latest"]
    print(f"【{result['symbol']} 技术指标】source={result['source_actual']} fallback={result['fallback_used']}")
    print(f"close={latest.get('close')} ma_20={latest.get('ma_20')} rsi_14={latest.get('rsi_14')}")
    print("signals:", ",".join(result["data"]["signals"]) or "无")


if __name__ == "__main__":
    main()
