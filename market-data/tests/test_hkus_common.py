import pytest

from scripts.hkus_common import build_fallback_chain, normalize_symbol, pick_first_available


def test_normalize_us_symbol_plain_ticker():
    info = normalize_symbol("aapl")
    assert info["market"] == "US"
    assert info["normalized"] == "NASDAQ:AAPL"
    assert info["yahoo_symbol"] == "AAPL"


def test_normalize_hk_symbol_short_code():
    info = normalize_symbol("700")
    assert info["market"] == "HK"
    assert info["normalized"] == "0700.HK"
    assert info["yahoo_symbol"] == "0700.HK"


def test_build_fallback_chain_for_us_history():
    chain = build_fallback_chain("US", "history")
    assert chain == [
        "tencent_history",
        "sina_history",
        "yfinance",
        "yahooquery_history",
        "yahoo_chart",
    ]


def test_build_fallback_chain_for_us_realtime():
    chain = build_fallback_chain("US", "realtime")
    assert chain[0] == "tencent_quote"
    assert chain[1] == "sina_quote"
    assert "yahooquery_realtime" in chain


def test_normalize_symbol_includes_source_codes():
    us = normalize_symbol("AAPL")
    assert us["tencent_code"] == "usAAPL"
    assert us["tencent_kline_code"] == "usAAPL.OQ"
    assert us["sina_code"] == "gb_aapl"
    hk = normalize_symbol("0700.HK")
    assert hk["tencent_code"] == "hk00700"
    assert hk["tencent_kline_code"] == "hk00700"
    assert hk["sina_code"] == "hk00700"


def test_pick_first_available_marks_fallback():
    data_map = {
        "yfinance": None,
        "yahooquery_history": {"close": [1, 2, 3]},
        "yahoo_chart": {"close": [2, 3, 4]},
    }
    chosen = pick_first_available(data_map, ["yfinance", "yahooquery_history", "yahoo_chart"])
    assert chosen["source_actual"] == "yahooquery_history"
    assert chosen["fallback_used"] is True
    assert chosen["fallback_chain"] == ["yfinance", "yahooquery_history"]


def test_pick_first_available_raise_when_all_failed():
    with pytest.raises(ValueError):
        pick_first_available({"yfinance": None}, ["yfinance", "yahooquery_history"])
