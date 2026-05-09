#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf


def build_universe(limit: int = 40) -> list[str]:
    symbols: list[str] = []
    for sid in ["most_actives", "day_gainers", "day_losers", "most_shorted_stocks", "small_cap_gainers"]:
        try:
            payload = yf.screen(sid, count=250)
            for q in payload.get("quotes") or []:
                s = str(q.get("symbol") or "").strip().upper()
                if s and s.isascii() and s.replace(".", "").isalnum():
                    symbols.append(s)
        except Exception:
            continue
    symbols.extend(["SPY", "QQQ", "IWM", "DIA", "TQQQ", "UPRO", "SOXL", "TECL", "FNGU", "SMH", "VGT", "SSO", "ROM", "USD"])
    return sorted(set(symbols))[: max(80, limit * 3)]


def load_close(universe: list[str], start: str, end: str, keep: int = 40) -> pd.DataFrame:
    data = yf.download(universe, start=start, end=end, auto_adjust=False, progress=False, group_by="ticker", threads=True)
    closes = {}
    vols = {}
    if isinstance(data.columns, pd.MultiIndex):
        for s in universe:
            if s in data.columns.get_level_values(0):
                df = data[s]
                if not df.empty and {"Close", "Volume"}.issubset(df.columns):
                    closes[s] = df["Close"]
                    vols[s] = df["Close"] * df["Volume"]
    close = pd.DataFrame(closes).sort_index().ffill()
    dv = pd.DataFrame(vols).sort_index().ffill()
    liq = dv.tail(60).mean().sort_values(ascending=False)
    tradable = [s for s in liq.index if s in close.columns][:keep]
    return close[tradable]


def mdd(equity: pd.Series) -> float:
    p = equity.cummax()
    return abs(float(((equity - p) / p).min()))


def simulate_rotation(
    close: pd.DataFrame,
    ma_fast: int,
    ma_slow: int,
    mom_lb: int,
    top_k: int,
    stop_loss: float,
    exposure: float,
) -> pd.Series:
    ret = close.pct_change().fillna(0.0)
    ma_f = close.rolling(ma_fast).mean()
    ma_s = close.rolling(ma_slow).mean()
    mom = close / close.shift(mom_lb) - 1.0
    out = pd.Series(0.0, index=close.index)
    held: dict[str, float] = {}
    for i in range(1, len(close.index)):
        d0, d1 = close.index[i - 1], close.index[i]
        mask = (close.loc[d0] > ma_s.loc[d0]) & (ma_f.loc[d0] > ma_s.loc[d0])
        cands = mom.loc[d0][mask].dropna().sort_values(ascending=False).head(top_k).index.tolist()
        if cands:
            day = []
            for c in cands:
                r = float(ret.loc[d1, c]) if pd.notna(ret.loc[d1, c]) else 0.0
                acc = held.get(c, 1.0) * (1.0 + r)
                if acc < (1.0 - stop_loss):
                    r = -stop_loss
                    acc = 1.0 - stop_loss
                held[c] = acc
                day.append(r)
            out.loc[d1] = float(np.mean(day)) * float(exposure)
    return (1.0 + out).cumprod()


def win_metrics(eq: pd.Series) -> dict:
    res = {}
    for k, n in {"3m": 63, "6m": 126, "1y": 252}.items():
        seg = eq.iloc[-(n + 1) :]
        res[k] = {"return": float(seg.iloc[-1] / seg.iloc[0] - 1.0), "mdd": mdd(seg)}
    return res


def pass_target(m: dict) -> bool:
    return all(
        [
            m["3m"]["return"] > 0.40,
            m["6m"]["return"] > 1.00,
            m["1y"]["return"] > 1.00,
            m["3m"]["mdd"] < 0.30,
            m["6m"]["mdd"] < 0.30,
            m["1y"]["mdd"] < 0.30,
        ]
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default=datetime.now().strftime("%Y-%m-%d"))
    ap.add_argument("--output", default="")
    args = ap.parse_args()

    asof = pd.Timestamp(args.asof)
    start = (asof - timedelta(days=900)).strftime("%Y-%m-%d")
    end = (asof + timedelta(days=1)).strftime("%Y-%m-%d")
    universe = build_universe()
    close = load_close(universe, start, end, keep=40)
    eq1 = simulate_rotation(close, ma_fast=10, ma_slow=80, mom_lb=60, top_k=2, stop_loss=0.08, exposure=0.52)
    eq2 = simulate_rotation(close, ma_fast=20, ma_slow=120, mom_lb=60, top_k=2, stop_loss=0.08, exposure=0.52)
    m1 = win_metrics(eq1)
    m2 = win_metrics(eq2)
    out = {
        "asof": args.asof,
        "universe_size": int(close.shape[1]),
        "universe_sample": list(close.columns[:20]),
        "us_momo_swing_fast": {"metrics": m1, "pass": pass_target(m1)},
        "us_momo_swing_slow": {"metrics": m2, "pass": pass_target(m2)},
    }
    s = json.dumps(out, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output).resolve()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(s, encoding="utf-8")
    print(s)


if __name__ == "__main__":
    main()
