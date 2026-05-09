#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LAB = ROOT / "us-strategy-lab" / "scripts"
if str(LAB) not in sys.path:
    sys.path.insert(0, str(LAB))

from us_momo_runtime import StrategyConfig, dumps, run_strategy


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default="2026-05-09")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    cfg = StrategyConfig(
        name="us_momo_swing_fast",
        ma_fast=15,
        ma_slow=120,
        mom_lb=80,
        top_k=6,
        stop_loss=0.06,
        exposure=1.30,
        universe_keep=40,
    )
    payload = run_strategy(cfg, asof=args.asof)
    out = {
        "asof": payload["asof"],
        "strategy": payload["strategy"]["name"],
        "next_trade_candidates": payload["next_trade_candidates"],
        "anti_lookahead": payload["anti_lookahead"],
    }
    print(dumps(out))


if __name__ == "__main__":
    main()
