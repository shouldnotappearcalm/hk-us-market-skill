#!/usr/bin/env python3
"""Offline smoke checks for HK+US paper trading functionality."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import pandas as pd


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from paper_trading.engine import OrderRequest, PaperTradingEngine  # noqa: E402
from paper_trading.market_data import Quote  # noqa: E402
from paper_trading_runtime import get_quote_cache_path  # noqa: E402


class FakeMarketData:
    def normalize_symbol(self, symbol: str) -> str:
        s = str(symbol).upper()
        if s.endswith(".HK"):
            return s
        if ":" in s:
            return s
        if s.isalpha():
            return f"NASDAQ:{s}"
        if s.isdigit():
            return f"{s.zfill(4)}.HK"
        return s

    def get_quote(self, symbol: str) -> Quote:
        normalized = self.normalize_symbol(symbol)
        if normalized.endswith(".HK"):
            return Quote(
                symbol=normalized,
                name="TENCENT",
                market="HK",
                price=320.5,
                open=319.0,
                high=322.0,
                low=318.5,
                prev_close=318.0,
                volume=1000000,
                change_pct=0.78,
                timestamp="2026-04-16 10:00:00",
                source="fake",
                currency="HKD",
            )
        return Quote(
            symbol=normalized,
            name="APPLE",
            market="US",
            price=198.2,
            open=197.5,
            high=199.0,
            low=196.8,
            prev_close=196.0,
            volume=800000,
            change_pct=1.12,
            timestamp="2026-04-16 10:00:00",
            source="fake",
            currency="USD",
        )

    def get_quotes(self, symbols):
        return {self.normalize_symbol(symbol): self.get_quote(symbol) for symbol in symbols}

    def get_intraday_bars(self, symbol: str, freq: str = "1m", count: int = 240):
        return pd.DataFrame(
            [
                {"time": pd.Timestamp("2026-04-16 09:59:00"), "open": 197.8, "high": 198.0, "low": 197.3, "close": 197.9, "volume": 1000},
                {"time": pd.Timestamp("2026-04-16 10:00:00"), "open": 198.0, "high": 198.5, "low": 197.7, "close": 198.2, "volume": 1200},
            ]
        )

    def get_history(self, symbol: str, start: str | None = None, end: str | None = None, count: int = 240):
        dates = pd.date_range("2025-01-01", periods=200, freq="B")
        return pd.DataFrame(
            {
                "time": dates,
                "open": [100 + i * 0.1 for i in range(len(dates))],
                "high": [101 + i * 0.1 for i in range(len(dates))],
                "low": [99 + i * 0.1 for i in range(len(dates))],
                "close": [100 + i * 0.15 for i in range(len(dates))],
                "volume": [100000 + i * 10 for i in range(len(dates))],
            }
        ).tail(count).reset_index(drop=True)


def _assert(expr: bool, message: str) -> None:
    if not expr:
        raise AssertionError(message)


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def run_engine_checks() -> None:
    fake_data = FakeMarketData()
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "smoke.db")
        engine = PaperTradingEngine(db_path, market_data=fake_data)
        acct = engine.create_account("alpha", 500000)
        _assert(acct["cash"] == 500000.0, "create_account cash mismatch")

        us_buy = engine.place_order(OrderRequest(account_id="alpha", symbol="AAPL", side="buy", qty=20, order_type="market"))
        _assert(us_buy["status"] == "filled", "us market buy not filled")
        hk_buy = engine.place_order(OrderRequest(account_id="alpha", symbol="700", side="buy", qty=100, order_type="limit", limit_price=320.5))
        _assert(hk_buy["status"] == "open", "hk limit buy not open")
        processed = engine.process_orders()
        _assert(processed["filled"] >= 1, "process_orders did not fill hk order")

        positions = engine.get_positions("alpha")
        symbols = {p["symbol"] for p in positions}
        _assert("NASDAQ:AAPL" in symbols and "0700.HK" in symbols, "positions symbol mismatch")

        sell = engine.place_order(OrderRequest(account_id="alpha", symbol="AAPL", side="sell", qty=10, order_type="market"))
        _assert(sell["status"] == "filled", "us sell not filled")

        snapshots = engine.snapshot_accounts()
        _assert(snapshots["snapshots"] >= 1, "snapshot missing")
        bt = engine.run_backtest("AAPL", "sma_cross", "2025-01-01", "2025-12-31", 100000)
        _assert(bt["symbol"] == "NASDAQ:AAPL", "backtest symbol mismatch")


def run_cache_path_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        os.environ["HK_US_PAPER_TRADING_HOME"] = str(Path(tmp) / "hkus-home")
        cache_path = get_quote_cache_path()
        _assert("hk-us-market-paper-trading" in str(cache_path) or "hkus-home" in str(cache_path), "cache path should use hk-us market runtime home")
        _assert("a-share-paper-trading" not in str(cache_path), "cache path should be isolated from a-share")


def run_service_cli_checks() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "service.db")
        home_path = str(Path(tmp) / "runtime-home")
        port = _free_port()
        base = f"http://127.0.0.1:{port}"
        service_cmd = [
            sys.executable,
            str(SCRIPT_DIR / "paper_trading_service.py"),
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--db-path",
            db_path,
            "--match-interval",
            "1",
        ]
        env = os.environ.copy()
        env["HK_US_PAPER_TRADING_HOME"] = home_path
        proc = subprocess.Popen(service_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
        try:
            deadline = time.time() + 15
            while time.time() < deadline:
                try:
                    with urllib.request.urlopen(f"{base}/health", timeout=2) as resp:
                        body = json.loads(resp.read().decode("utf-8"))
                        if body.get("status") == "ok":
                            break
                except Exception:
                    time.sleep(0.2)
            else:
                raise AssertionError("service did not start")

            cli = [sys.executable, str(SCRIPT_DIR / "paper_trade_cli.py"), "--base-url", base]
            subprocess.run(cli + ["create-account", "svc", "--cash", "200000"], check=True, capture_output=True, text=True, env=env)
            list_out = subprocess.run(cli + ["list-accounts"], check=True, capture_output=True, text=True, env=env).stdout
            _assert("svc" in list_out, "list-accounts CLI failed")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)


def main() -> None:
    run_engine_checks()
    run_cache_path_check()
    run_service_cli_checks()
    print("PASS full_function_smoke_check")


if __name__ == "__main__":
    main()
