import os

import pytest

from scripts.hkus_common import pick_first_available


def test_disable_primary_source_with_env(monkeypatch):
    monkeypatch.setenv("HKUS_DISABLE_SOURCES", "yfinance")
    data_map = {
        "yfinance": {"value": 1},
        "yahooquery_history": {"value": 2},
        "yahoo_chart": {"value": 3},
    }
    picked = pick_first_available(data_map, ["yfinance", "yahooquery_history", "yahoo_chart"])
    assert picked["source_actual"] == "yahooquery_history"
    assert picked["fallback_used"] is True
    assert picked["fallback_chain"] == ["yfinance", "yahooquery_history"]


def test_disable_all_sources_raise(monkeypatch):
    monkeypatch.setenv("HKUS_DISABLE_SOURCES", "yfinance,yahooquery_history,yahoo_chart")
    data_map = {
        "yfinance": {"value": 1},
        "yahooquery_history": {"value": 2},
        "yahoo_chart": {"value": 3},
    }
    with pytest.raises(ValueError):
        pick_first_available(data_map, ["yfinance", "yahooquery_history", "yahoo_chart"])
