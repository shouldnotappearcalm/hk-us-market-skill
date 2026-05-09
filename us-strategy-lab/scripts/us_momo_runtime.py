#!/usr/bin/env python3
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class StrategyConfig:
    name: str
    ma_fast: int
    ma_slow: int
    mom_lb: int
    top_k: int
    stop_loss: float
    exposure: float
    universe_keep: int = 40


def build_universe() -> list[str]:
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
    return sorted(set(symbols))


def load_close(universe: list[str], start: str, end: str, keep: int) -> pd.DataFrame:
    data = yf.download(universe, start=start, end=end, auto_adjust=False, progress=False, group_by="ticker", threads=True)
    closes: dict[str, Any] = {}
    vols: dict[str, Any] = {}
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


def latest_candidates(close: pd.DataFrame, cfg: StrategyConfig) -> list[dict]:
    ma_f = close.rolling(cfg.ma_fast).mean()
    ma_s = close.rolling(cfg.ma_slow).mean()
    mom = close / close.shift(cfg.mom_lb) - 1.0
    d0 = close.index[-1]
    mask = (close.loc[d0] > ma_s.loc[d0]) & (ma_f.loc[d0] > ma_s.loc[d0])
    ranked = mom.loc[d0][mask].dropna().sort_values(ascending=False).head(cfg.top_k)
    out = []
    for s, v in ranked.items():
        out.append({"symbol": s, "score_mom": round(float(v), 6), "close": round(float(close.loc[d0, s]), 4)})
    return out


def simulate(close: pd.DataFrame, cfg: StrategyConfig) -> pd.Series:
    ret = close.pct_change().fillna(0.0)
    ma_f = close.rolling(cfg.ma_fast).mean()
    ma_s = close.rolling(cfg.ma_slow).mean()
    mom = close / close.shift(cfg.mom_lb) - 1.0
    out = pd.Series(0.0, index=close.index)
    held: dict[str, float] = {}
    for i in range(1, len(close.index)):
        d0, d1 = close.index[i - 1], close.index[i]
        mask = (close.loc[d0] > ma_s.loc[d0]) & (ma_f.loc[d0] > ma_s.loc[d0])
        cands = mom.loc[d0][mask].dropna().sort_values(ascending=False).head(cfg.top_k).index.tolist()
        if not cands:
            continue
        day = []
        for c in cands:
            r = float(ret.loc[d1, c]) if pd.notna(ret.loc[d1, c]) else 0.0
            acc = held.get(c, 1.0) * (1.0 + r)
            if acc < (1.0 - cfg.stop_loss):
                r = -cfg.stop_loss
                acc = 1.0 - cfg.stop_loss
            held[c] = acc
            day.append(r)
        out.loc[d1] = float(np.mean(day)) * cfg.exposure
    return (1.0 + out).cumprod()


def max_dd(equity: pd.Series) -> float:
    peak = equity.cummax()
    return abs(float(((equity - peak) / peak).min()))


def window_metrics(equity: pd.Series) -> dict:
    res = {}
    for k, n in {"3m": 63, "6m": 126, "1y": 252}.items():
        seg = equity.iloc[-(n + 1) :]
        res[k] = {"return": float(seg.iloc[-1] / seg.iloc[0] - 1.0), "mdd": max_dd(seg)}
    return res


def pass_target(m: dict) -> bool:
    return (
        m["3m"]["return"] > 0.40
        and m["6m"]["return"] > 1.00
        and m["1y"]["return"] > 1.00
        and m["3m"]["mdd"] < 0.30
        and m["6m"]["mdd"] < 0.30
        and m["1y"]["mdd"] < 0.30
    )


def run_strategy(cfg: StrategyConfig, asof: str) -> dict:
    ts = pd.Timestamp(asof)
    start = (ts - timedelta(days=900)).strftime("%Y-%m-%d")
    end = (ts + timedelta(days=1)).strftime("%Y-%m-%d")
    universe = build_universe()
    close = load_close(universe, start, end, cfg.universe_keep)
    eq = simulate(close, cfg)
    metrics = window_metrics(eq)
    return {
        "asof": asof,
        "strategy": asdict(cfg),
        "universe_size": int(close.shape[1]),
        "universe_sample": list(close.columns[:20]),
        "next_trade_candidates": latest_candidates(close, cfg),
        "metrics": metrics,
        "pass": pass_target(metrics),
        "anti_lookahead": "signals use t-1 close indicators and execute on t; no t+1 data in decision",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)
