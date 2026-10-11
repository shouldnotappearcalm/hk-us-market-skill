import json
import time
from datetime import datetime
from unittest.mock import Mock

import pytest

from scripts import hkus_common as common, hkus_data_sources as sources
from scripts import fetch_realtime_hkus as realtime
from scripts import fetch_fundamental_hkus as fundamental
from scripts.fetch_universe_hkus import _normalize_hk_symbol


def test_hk_zero_padding_and_spreadsheet_numbers():
    assert common.normalize_symbol("09988.HK")["yahoo_symbol"] == "9988.HK"
    assert common.normalize_symbol("00700")["yahoo_symbol"] == "0700.HK"
    assert _normalize_hk_symbol(700.0) == "0700.HK"


def test_hk_quote_fields_match_original_protocol():
    arr=[""]*40
    arr[0],arr[1],arr[2]="100","Alibaba","09988"
    arr[3],arr[4],arr[5],arr[6]="107","104.3","104.5","100"
    arr[30],arr[33],arr[34]="2026/10/09 16:08:14","108","103"
    row=sources._parse_tencent_quote_line('v_hk09988="'+"~".join(arr)+'";',"HK")
    assert row["price"]==107
    assert row["previous_close"]==104.3
    assert row["open"]==104.5
    assert row["change_pct"]==pytest.approx(2.5887)


def test_lazy_fallback_skips_unused_and_disabled_callbacks(monkeypatch):
    primary=Mock(return_value={"price":107})
    secondary=Mock(return_value={"price":108})
    result=common.pick_first_available({"primary":primary,"secondary":secondary},["primary","secondary"])
    assert result["source_actual"]=="primary"
    secondary.assert_not_called()
    monkeypatch.setenv("HKUS_DISABLE_SOURCES","primary")
    primary.reset_mock()
    result=common.pick_first_available({"primary":primary,"secondary":secondary},["primary","secondary"])
    primary.assert_not_called()
    assert result["source_actual"]=="secondary"


def test_source_failure_does_not_block_fallback():
    result=common.pick_first_available({"bad":lambda:1/0,"empty":lambda:[],"ok":lambda:{"price":1}},["bad","empty","ok"])
    assert result["source_actual"]=="ok"
    assert "ZeroDivisionError" in result["source_errors"]["bad"]


def test_source_timeout_preserves_quick_fallback(monkeypatch):
    monkeypatch.setenv("HKUS_SOURCE_TIMEOUT","0.1")
    start=time.monotonic()
    result=common.pick_first_available({"slow":lambda:time.sleep(.4),"ok":lambda:{"price":1}},["slow","ok"])
    assert time.monotonic()-start < .3
    assert result["source_actual"]=="ok"
    assert "TimeoutError" in result["source_errors"]["slow"]


def test_realtime_does_not_call_yahoo_when_tencent_works(monkeypatch):
    monkeypatch.setattr(realtime,"fetch_tencent_quote",lambda _: {"price":107})
    unused=Mock(side_effect=AssertionError("unused fallback called"))
    for name in ["fetch_sina_quote","fetch_yahooquery_realtime","fetch_yfinance_realtime","fetch_yahoo_chart_realtime","enrich_realtime_premarket"]:
        monkeypatch.setattr(realtime,name,unused)
    assert realtime.fetch_symbol_realtime("9988.HK")["data"]["price"]==107
    unused.assert_not_called()


def test_fundamental_falls_back_after_primary_exception(monkeypatch):
    monkeypatch.setattr(fundamental,"fetch_yfinance_fundamental",Mock(side_effect=RuntimeError("unavailable")))
    monkeypatch.setattr(fundamental,"fetch_yahooquery_fundamental",lambda _: {"sector":"Technology"})
    assert fundamental.run("9988.HK")["source_actual"]=="yahooquery"


def test_unknown_sector_never_masquerades_as_spy():
    with pytest.raises(ValueError,match="unknown_sector"):
        sources.fetch_sector_etf("nonexistent industry")


def test_news_preserves_raw_provider_record_and_empty_source(monkeypatch):
    from scripts import fetch_news_hkus as news
    raw={"title":"An industry-wide story","content":"No local company-name match","date":"2026-10-11 00:00:00","extra_upstream_field":42}
    monkeypatch.setattr(news,"fetch_yahoo_news",lambda *a: [])
    monkeypatch.setattr(news,"fetch_news",lambda *a: {"status":"ok","data":[raw],"meta":{"coverage_limited":False,"errors":[]}})
    result=news.run("09988.HK","Alibaba",days=366)
    assert result["data"]==[{"source":"eastmoney_search","raw":raw}]
    assert result["status"]=="ok"
    assert any(s["status"]=="empty" for s in result["meta"]["sources"])


def test_news_source_failure_keeps_other_source_raw_output(monkeypatch):
    from scripts import fetch_news_hkus as news
    raw={"title":"Original title","providerPublishTime":int(datetime.now().timestamp())}
    monkeypatch.setattr(news,"fetch_yahoo_news",lambda *a: [raw])
    monkeypatch.setattr(news,"fetch_news",Mock(side_effect=RuntimeError("upstream unavailable")))
    result=news.run("NYSE:BABA","Alibaba")
    assert result["status"]=="partial"
    assert result["data"]==[{"source":"yahoo_news","raw":raw}]


def test_technical_warmup_values_are_strict_json(monkeypatch):
    from scripts import fetch_technical_hkus as technical
    rows=[{"time":f"2026-10-{day:02d}","open":1.,"high":2.,"low":.5,"close":1.5,"volume":100} for day in range(1,10)]
    monkeypatch.setattr(technical,"_get_history",lambda *a:{"source_primary":"fake","source_actual":"fake","fallback_used":False,"fallback_chain":["fake"],"data":rows})
    result=technical.run("AAPL",30,"1d")
    json.dumps(result,allow_nan=False)
    assert result["data"]["series"][0]["ma_60"] is None


def test_unknown_us_exchange_is_not_invented():
    assert common.normalize_symbol("BABA")["normalized"]=="US:BABA"
    assert common.normalize_symbol("NYSE:BABA")["normalized"]=="NYSE:BABA"
