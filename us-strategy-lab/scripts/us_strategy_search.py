#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List

import numpy as np
import pandas as pd
import yfinance as yf


ROOT = Path(__file__).resolve().parents[2]
UNIVERSE_SCRIPT = ROOT / "market-data" / "scripts" / "fetch_universe_hkus.py"


def _load_from_yf_screener(limit: int) -> list[str]:
    symbols: list[str] = []
    screen_ids = [
        "most_actives",
        "day_gainers",
        "day_losers",
        "most_shorted_stocks",
        "small_cap_gainers",
    ]
    for sid in screen_ids:
        try:
            payload = yf.screen(sid, count=250)
            quotes = payload.get("quotes") or []
            for q in quotes:
                s = str(q.get("symbol") or "").strip().upper()
                if s and s.isascii() and s.replace(".", "").isalnum():
                    symbols.append(s)
        except Exception:
            continue
    symbols.extend(
        [
            "SPY",
            "QQQ",
            "IWM",
            "DIA",
            "TQQQ",
            "UPRO",
            "SOXL",
            "TECL",
            "FNGU",
            "SMH",
            "VGT",
            "SSO",
            "ROM",
            "USD",
        ]
    )
    symbols = sorted(set(symbols))
    return symbols[:limit] if limit > 0 else symbols


def _load_from_local_universe(limit: int) -> list[str]:
    proc = subprocess.run(
        [sys.executable, str(UNIVERSE_SCRIPT), "--market", "us", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    rows = json.loads(proc.stdout).get("data") or []
    symbols: list[str] = []
    for r in rows:
        s = str(r.get("symbol") or "").strip().upper()
        if ":" not in s:
            continue
        ticker = s.split(":", 1)[1]
        if ticker and ticker.isascii() and ticker.replace(".", "").isalnum():
            symbols.append(ticker)
    symbols = sorted(set(symbols))
    return symbols[:limit] if limit > 0 else symbols


def load_us_symbols(limit: int) -> list[str]:
    try:
        syms = _load_from_yf_screener(limit)
        if syms:
            return syms
    except Exception:
        pass
    return _load_from_local_universe(limit)


def download_history(tickers: list[str], start: str, end: str) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    batch = 100
    for i in range(0, len(tickers), batch):
        chunk = tickers[i : i + batch]
        data = yf.download(
            tickers=chunk,
            start=start,
            end=end,
            auto_adjust=False,
            progress=False,
            threads=True,
            group_by="ticker",
        )
        if isinstance(data.columns, pd.MultiIndex):
            for t in chunk:
                if t not in data.columns.get_level_values(0):
                    continue
                df = data[t].copy()
                if df.empty or "Close" not in df.columns:
                    continue
                df = df.dropna(subset=["Open", "High", "Low", "Close", "Volume"])
                if len(df) >= 260:
                    out[t] = df
        else:
            if len(chunk) == 1 and not data.empty:
                df = data.copy().dropna(subset=["Open", "High", "Low", "Close", "Volume"])
                if len(df) >= 260:
                    out[chunk[0]] = df
    return out


def max_drawdown(equity: pd.Series) -> float:
    peak = equity.cummax()
    dd = ((equity - peak) / peak).fillna(0.0)
    return abs(float(dd.min()))


def simulate_rotation(
    prices: pd.DataFrame,
    ma_fast: int,
    ma_slow: int,
    mom_lb: int,
    top_k: int,
    stop_loss: float,
    cash_proxy: str | None = None,
) -> pd.Series:
    close = prices.copy()
    rets = close.pct_change().fillna(0.0)
    ma_f = close.rolling(ma_fast).mean()
    ma_s = close.rolling(ma_slow).mean()
    mom = close / close.shift(mom_lb) - 1.0

    idx = close.index
    daily_port_ret = pd.Series(0.0, index=idx, dtype="float64")
    held: dict[str, float] = {}

    for i in range(1, len(idx)):
        d0 = idx[i - 1]
        d1 = idx[i]
        candidates = []
        for c in close.columns:
            if pd.isna(close.loc[d0, c]) or pd.isna(ma_f.loc[d0, c]) or pd.isna(ma_s.loc[d0, c]) or pd.isna(mom.loc[d0, c]):
                continue
            if close.loc[d0, c] > ma_s.loc[d0, c] and ma_f.loc[d0, c] > ma_s.loc[d0, c]:
                candidates.append((c, float(mom.loc[d0, c])))
        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [c for c, _ in candidates[:top_k]]

        if selected:
            day_rets = []
            for c in selected:
                r = float(rets.loc[d1, c]) if not pd.isna(rets.loc[d1, c]) else 0.0
                prev = held.get(c, 1.0)
                cur = prev * (1.0 + r)
                if cur < (1.0 - stop_loss):
                    r = -stop_loss
                    cur = 1.0 - stop_loss
                held[c] = cur
                day_rets.append(r)
            daily_port_ret.loc[d1] = float(np.mean(day_rets))
        elif cash_proxy and cash_proxy in close.columns and not pd.isna(rets.loc[d1, cash_proxy]):
            daily_port_ret.loc[d1] = float(rets.loc[d1, cash_proxy])
        else:
            daily_port_ret.loc[d1] = 0.0

    equity = (1.0 + daily_port_ret).cumprod()
    return equity


def evaluate_windows(equity: pd.Series, asof: pd.Timestamp) -> dict[str, dict[str, float]]:
    windows = {"3m": 63, "6m": 126, "1y": 252}
    result: dict[str, dict[str, float]] = {}
    for k, bars in windows.items():
        if len(equity) < bars + 1:
            result[k] = {"return": math.nan, "mdd": math.nan}
            continue
        seg = equity.iloc[-(bars + 1) :]
        ret = float(seg.iloc[-1] / seg.iloc[0] - 1.0)
        mdd = max_drawdown(seg)
        result[k] = {"return": ret, "mdd": mdd}
    return result


@dataclass
class Candidate:
    params: dict
    metrics: dict
    score: float


def passes_target(m: dict) -> bool:
    return (
        m["3m"]["return"] > 0.40
        and m["6m"]["return"] > 1.00
        and m["1y"]["return"] > 1.00
        and m["3m"]["mdd"] < 0.30
        and m["6m"]["mdd"] < 0.30
        and m["1y"]["mdd"] < 0.30
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--symbol-limit", type=int, default=500)
    p.add_argument("--asof", default=datetime.now().strftime("%Y-%m-%d"))
    p.add_argument("--output", default="")
    args = p.parse_args()

    asof = pd.Timestamp(args.asof)
    start = (asof - timedelta(days=900)).strftime("%Y-%m-%d")
    end = (asof + timedelta(days=1)).strftime("%Y-%m-%d")

    symbols = load_us_symbols(args.symbol_limit)
    hist = download_history(symbols, start, end)
    if len(hist) < 50:
        raise SystemExit("not enough symbols with history")

    close = pd.DataFrame({k: v["Close"] for k, v in hist.items()}).sort_index().ffill().dropna(axis=1, thresh=300)
    dv = pd.DataFrame({k: (v["Close"] * v["Volume"]) for k, v in hist.items()}).sort_index().ffill()
    liquid_rank = dv.tail(60).mean().sort_values(ascending=False)
    tradable = [c for c in liquid_rank.index if c in close.columns][:40]
    close = close[tradable].dropna(how="all")

    candidates: list[Candidate] = []
    for ma_fast in [10, 15, 20]:
        for ma_slow in [80, 100, 120]:
            if ma_fast >= ma_slow:
                continue
            for mom_lb in [20, 40, 60]:
                for top_k in [1, 2]:
                    for stop_loss in [0.08, 0.10]:
                        eq = simulate_rotation(close, ma_fast, ma_slow, mom_lb, top_k, stop_loss)
                        m = evaluate_windows(eq, asof)
                        score = (m["3m"]["return"] + m["6m"]["return"] + m["1y"]["return"]) - (
                            m["3m"]["mdd"] + m["6m"]["mdd"] + m["1y"]["mdd"]
                        )
                        params = {
                            "ma_fast": ma_fast,
                            "ma_slow": ma_slow,
                            "mom_lb": mom_lb,
                            "top_k": top_k,
                            "stop_loss": stop_loss,
                            "universe_size": len(tradable),
                        }
                        candidates.append(Candidate(params=params, metrics=m, score=score))

    candidates.sort(key=lambda x: x.score, reverse=True)
    winners = [c for c in candidates if passes_target(c.metrics)]
    output = {
        "asof": args.asof,
        "tradable_count": len(tradable),
        "tradable_sample": tradable[:20],
        "winner_count": len(winners),
        "winners": [
            {
                "params": w.params,
                "metrics": w.metrics,
                "score": round(w.score, 6),
            }
            for w in winners[:20]
        ],
        "top10": [
            {
                "params": c.params,
                "metrics": c.metrics,
                "score": round(c.score, 6),
                "pass": passes_target(c.metrics),
            }
            for c in candidates[:10]
        ],
    }

    if args.output:
        path = Path(args.output).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
