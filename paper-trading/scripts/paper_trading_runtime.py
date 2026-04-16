#!/usr/bin/env python3
"""Runtime defaults and paths for HK+US paper trading service."""

from __future__ import annotations

import os
from pathlib import Path

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 18766
APP_NAME = "hk-us-market-paper-trading"
DB_FILENAME = "paper_trading.db"
LOG_FILENAME = "service.log"
PID_FILENAME = "service.pid"
CACHE_DIRNAME = "cache"
LAUNCH_AGENT_LABEL = "ai.openclaw.hk-us-market-paper-trading"


def get_app_data_dir() -> Path:
    custom = os.environ.get("HK_US_PAPER_TRADING_HOME")
    if custom:
        return Path(custom).expanduser()
    home = Path.home()
    if os.name == "posix" and "darwin" in os.uname().sysname.lower():
        return home / "Library" / "Application Support" / APP_NAME
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg).expanduser() / APP_NAME
    return home / ".local" / "share" / APP_NAME


def get_default_db_path() -> Path:
    return get_app_data_dir() / DB_FILENAME


def get_default_log_path() -> Path:
    return get_app_data_dir() / LOG_FILENAME


def get_default_pid_path() -> Path:
    return get_app_data_dir() / PID_FILENAME


def get_cache_dir() -> Path:
    return get_app_data_dir() / CACHE_DIRNAME


def get_quote_cache_path() -> Path:
    return get_cache_dir() / "quote_cache.json"


def get_launch_agents_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def ensure_runtime_dir(path: Path | None = None) -> Path:
    target = path or get_app_data_dir()
    target.mkdir(parents=True, exist_ok=True)
    get_cache_dir().mkdir(parents=True, exist_ok=True)
    return target
