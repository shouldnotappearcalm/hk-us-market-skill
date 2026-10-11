import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import threading
import time
from unittest.mock import Mock

import pandas as pd
import pytest

from scripts import hkus_common as common, hkus_data_sources as sources, hkus_runtime as runtime
from scripts import fetch_history_hkus as history, fetch_disclosures_hkus as disclosures
from scripts import fetch_statements_hkus as statements


@pytest.fixture(autouse=True)
def isolate_cache(tmp_path,monkeypatch):
    monkeypatch.setenv('HKUS_CACHE_DIR',str(tmp_path))
    runtime._HEALTH.clear()


@pytest.mark.parametrize('raw',['BRK.B','BRK-B','NYSE:BRK.B'])
def test_class_shares_keep_provider_identity(raw):
    row=common.normalize_symbol(raw)
    assert row['yahoo_symbol']=='BRK-B'
    assert row['tencent_code']=='usBRK.B'
    assert row['sina_code']=='gb_brk.b'


@pytest.mark.parametrize('raw',['AAPL???','NYSE:','BAD EXCHANGE:AAPL','BAD.HK'])
def test_invalid_symbol_is_rejected_instead_of_rewritten(raw):
    with pytest.raises(ValueError):common.normalize_symbol(raw)


def test_tencent_adjustment_never_falls_back_to_different_node():
    block={'day':[[1]],'qfqday':[[2]]}
    assert sources._extract_tencent_kline_rows(block,'day','raw')==[[1]]
    assert sources._extract_tencent_kline_rows(block,'day','qfq')==[[2]]
    assert sources._extract_tencent_kline_rows({'day':[[1]]},'day','qfq')==[]
    with pytest.raises(ValueError):sources.fetch_sina_history(common.normalize_symbol('AAPL'),'1d',30,'qfq')


def test_exchange_offsets_and_daily_session_dates_survive_serialization():
    frame=pd.DataFrame({'close':[100]},index=pd.DatetimeIndex(['2026-10-09 09:30'],tz='America/New_York'))
    rows=sources._to_records(frame)
    assert rows[0]['time'].endswith('-04:00')
    out=common.normalize_history_records(rows,'US','1d')[0]
    assert out['trade_date']=='2026-10-09'
    assert out['time']=='2026-10-09T00:00:00-04:00'
    bars=common.normalize_history_records([dict(time='2026-01-05T14:30:00+00:00',close=100)],'US','1m')
    assert bars[0]['time']=='2026-01-05T09:30:00-05:00'


def test_date_end_filter_includes_last_intraday_bar():
    rows=[{'time':'2026-10-09T15:59:00-04:00','trade_date':'2026-10-09'}]
    assert history._filter_and_trim(rows,'2026-10-09','2026-10-09',10)==rows


def test_invalid_ohlc_falls_back_with_diagnostic():
    bad=[{'open':10,'high':9,'low':8,'close':11}]
    good=[{'open':10,'high':12,'low':8,'close':11}]
    picked=common.pick_first_available({'bad':lambda:bad,'good':lambda:good},['bad','good'],validator=history.validate_bars)
    assert picked['source_actual']=='good'
    assert 'OHLC' in picked['source_errors']['bad']


def test_cache_singleflight_and_copies(monkeypatch):
    monkeypatch.delenv('HKUS_NO_CACHE',raising=False)
    calls=[]
    def load(_):
        calls.append(1);time.sleep(.03);return {'data':[1]}
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:runtime.cached_fetch('same',load,60),range(4)))
    assert len(calls)==1
    results[0][0]['data'].append(2)
    later,meta=runtime.cached_fetch('same',load,60)
    assert later['data']==[1] and meta['cache_hit'] is True
    runtime.cached_fetch('same',load,60,no_cache=True)
    assert len(calls)==2


def test_expired_cache_is_not_silently_served(monkeypatch):
    monkeypatch.delenv('HKUS_NO_CACHE',raising=False)
    runtime.cached_fetch('expired',lambda _:{'data':[1]},60)
    path=runtime._cache_path('expired');value=json.loads(path.read_text());value['created']=0;path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError):runtime.cached_fetch('expired',lambda _:(_ for _ in ()).throw(RuntimeError('down')),60)


def test_source_workers_stay_bounded_after_timeouts():
    pool=runtime.SourcePool(workers=1,backlog=1)
    release=threading.Event()
    with pytest.raises(TimeoutError):pool.call(lambda:release.wait(1),.01)
    with pytest.raises(TimeoutError):pool.call(lambda:1,.01)
    with pytest.raises(RuntimeError,match='capacity'):pool.call(lambda:2,.01)
    release.set()


def test_three_failures_open_scoped_circuit():
    fn=Mock(side_effect=ValueError('down'))
    for _ in range(3):
        with pytest.raises(ValueError):common.pick_first_available({'bad':fn},['bad'],health_scope='a')
    with pytest.raises(ValueError,match='circuit_open'):common.pick_first_available({'bad':fn},['bad'],health_scope='a')
    assert fn.call_count==3
    picked=common.pick_first_available({'bad':lambda:[1]},['bad'],health_scope='b')
    assert picked['data']==[1]


def test_sec_rows_preserve_original_fields_and_archive_limit(monkeypatch):
    monkeypatch.setattr(disclosures,'request_json',lambda *a,**kw:{'name':'issuer','filings':{'recent':{
        'accessionNumber':['0000000001-26-000001'],'filingDate':['2099-01-01'],'form':['6-K'],'primaryDocument':['a.htm'],'extra':[42]},'files':[{'name':'older.json'}]}})
    result=disclosures.sec_disclosures(cik='1',no_cache=True)
    assert result['data'][0]['raw']['extra']==42
    assert result['meta']['coverage_limited'] is True
    assert '/1/000000000126000001/a.htm' in result['data'][0]['url']


def test_hkex_uses_exact_stock_identity_and_preserves_raw(monkeypatch):
    raw={'FILE_LINK':'/a.pdf','TITLE':'untouched title','extra':42}
    def fetch(url,params=None,**kw):
        if 'prefix' in url:return {'stockInfo':[{'stockId':10,'code':'09988','name':'issuer'}]}
        assert params['stockId']==10
        return {'result':json.dumps([raw]),'recordCnt':2,'hasNextRow':True}
    monkeypatch.setattr(disclosures,'request_json',fetch)
    result=disclosures.hkex_disclosures('09988.HK',no_cache=True)
    assert result['data'][0]['raw']==raw
    assert result['meta']['coverage_limited'] is True


def test_financial_asof_retains_units_and_excludes_later_revision():
    old={'end':'2025-12-31','filed':'2026-02-01','val':10}
    revised={'end':'2025-12-31','filed':'2026-05-01','val':12}
    obj={'facts':{'us-gaap':{'Revenue':{'label':'Revenue','units':{'USD':[old,revised]}}}}}
    rows=statements.select_facts(obj,as_of='2026-03-01')
    assert rows==[{'taxonomy':'us-gaap','concept':'Revenue','label':'Revenue','unit':'USD','raw':old}]


def test_new_york_holiday_and_dst_calendar():
    from scripts.hkus_calendar import latest_completed_session
    assert latest_completed_session('US',datetime.fromisoformat('2026-07-03T22:00:00+00:00'))=='2026-07-02'
    assert latest_completed_session('US',datetime.fromisoformat('2026-03-09T19:00:00+00:00'))=='2026-03-06'


def test_sina_hk_and_us_fields_match_raw_provider_protocol():
    hk=['']*25
    for index,value in {0:'BABA-W',1:'阿里巴巴',2:'104.5',3:'104.3',4:'107.3',5:'104.3',6:'107',7:'2.7',8:'2.589',12:'72349748',17:'2026/10/09',18:'16:08:12'}.items():hk[index]=value
    row=sources._parse_sina_quote_line('var hq_str_rt_hk09988="'+','.join(hk)+'";','HK')
    assert (row['price'],row['previous_close'],row['open'])==(107,104.3,104.5)
    assert row['quote_time']=='2026-10-09T16:08:12+08:00'
    us=['']*36
    for index,value in {0:'Apple',1:'336.64',3:'2026-10-10 09:48:00',5:'331.695',6:'338.61',7:'330.7',10:'37881199',26:'340.42'}.items():us[index]=value
    row=sources._parse_sina_quote_line('var hq_str_gb_aapl="'+','.join(us)+'";','US')
    assert (row['price'],row['previous_close'],row['open'],row['high'],row['low'])==(336.64,340.42,331.695,338.61,330.7)
    assert row['trade_date']=='2026-10-09'
    assert row['quote_time']=='2026-10-09T21:48:00-04:00'


def test_industry_members_are_market_scoped_and_paginated(monkeypatch):
    from scripts import fetch_industry_hkus as industry
    import yfinance as yf
    upstream={'symbol':'NVDA','extra':42}
    screen=Mock(side_effect=[{'quotes':[upstream],'total':2},{'quotes':[{'symbol':'AMD'}],'total':2}])
    monkeypatch.setattr(yf,'screen',screen)
    result=industry.query_industry('members','US','semiconductors',pages=2,no_cache=True)
    assert result['data'][0]['raw']==upstream
    assert result['meta']['coverage_limited'] is False
    assert screen.call_args_list[1].kwargs['offset']==1
    query=screen.call_args_list[0].args[0].to_dict()
    assert {'operator':'EQ','operands':['region','us']} in query['operands']


def test_yahoo_unadjusted_flag_is_not_misrepresented_as_nominal_raw(monkeypatch):
    unused=Mock(side_effect=AssertionError('unsupported source contacted'))
    monkeypatch.setattr(sources,'_ensure_yfinance',unused)
    with pytest.raises(ValueError,match='split-adjusted'):
        sources.fetch_yfinance_history('AAPL','1d',30,adjust='raw')
    unused.assert_not_called()


def test_history_incremental_cache_keeps_older_bars(monkeypatch):
    monkeypatch.delenv('HKUS_NO_CACHE',raising=False)
    monkeypatch.setattr(history,'freshness',lambda *a:{'stale':False})
    def bars(days):return [{'time':f'2026-10-{day:02d}','open':10,'high':12,'low':9,'close':11,'volume':100} for day in days]
    provider=Mock(side_effect=[bars([1,2,3]),bars([3,4])])
    monkeypatch.setattr(history,'fetch_tencent_history',provider)
    first=history.fetch_symbol_history('AAPL','1d',30,'','',3)
    path=next(runtime._cache_path('unused').parent.glob('*.json'))
    cache=json.loads(path.read_text());cache['created']=0;path.write_text(json.dumps(cache))
    second=history.fetch_symbol_history('AAPL','1d',30,'','',3)
    assert [row['trade_date'] for row in second['data']]==['2026-10-02','2026-10-03','2026-10-04']
    assert provider.call_args_list[1].args[2] < provider.call_args_list[0].args[2]
    assert second['incremental_refresh'] is True


def test_quote_batch_uses_one_vendor_request_and_recovers_only_missing(monkeypatch):
    from scripts import fetch_realtime_hkus as realtime, fetch_market_realtime_hkus as market
    rows={sym:{'symbol':sym,'price':10,'source_actual':'tencent_quote'} for sym in ['NASDAQ:AAPL','NASDAQ:MSFT']}
    batch=Mock(return_value=rows)
    unused=Mock(side_effect=AssertionError('unnecessary fallback'))
    monkeypatch.setattr(market,'_fetch_quotes_tencent',batch)
    monkeypatch.setattr(market,'_fetch_quotes_sina',unused)
    monkeypatch.setattr(realtime,'fetch_symbol_realtime',unused)
    result=realtime.run_batch(['AAPL','MSFT','AAPL'],workers=2,no_cache=True)
    assert result['meta']['success']==2 and batch.call_count==1
    assert [item['symbol'] for item in result['results']]==['AAPL','MSFT']
    unused.assert_not_called()


def test_market_scan_accepts_universe_exchange_prefixes_and_reuses_batch(monkeypatch):
    from scripts import fetch_market_realtime_hkus as market, fetch_realtime_hkus as realtime
    assert common.normalize_symbol('CBOE:TEST')['normalized']=='CBOE:TEST'
    monkeypatch.setattr(market,'_build_symbol_pool',lambda *a:(['CBOE:TEST'],[]))
    batch=Mock(return_value={'results':[{'ok':True,'symbol':'CBOE:TEST','result':{'source_actual':'tencent_quote','data':{'price':10,'change_pct':1}}}]})
    monkeypatch.setattr(realtime,'run_batch',batch)
    result=market.run('all','',1,2,10,'change_pct_desc')
    assert result['meta']['success']==1 and result['meta']['fail']==0
    batch.assert_called_once()


def test_symbol_search_decodes_names_but_keeps_original_row(monkeypatch):
    from scripts import search_symbols_hkus as search
    value=r'us~brk.b.n~\u4f2f\u514b~bk~GP'
    response=Mock();response.text='v_hint='+json.dumps(value)+';'
    session=Mock();session.get.return_value=response
    monkeypatch.setattr(search,'_http_session',lambda:session)
    row=search.search('伯克')["data"][0]
    assert row['code']=='BRK.B' and row['name']=='伯克'
    assert r'\\u4f2f' in row['raw']
