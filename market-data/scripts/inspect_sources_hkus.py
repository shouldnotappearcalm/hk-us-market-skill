#!/usr/bin/env python3
"""Provider capabilities and explicit per-source diagnostics, inspired by stock-api."""
import argparse
import json
import time

try:
    from . import hkus_data_sources as sources
    from .hkus_common import normalize_symbol
    from .hkus_runtime import call_source
except ImportError:
    import hkus_data_sources as sources
    from hkus_common import normalize_symbol
    from hkus_runtime import call_source

CAPABILITIES={
    'tencent_history': {'markets':['HK','US'],'adjust':['raw','qfq'],'intervals':['1d','1wk','1mo'],'intraday_note':'raw minute feed; only available upstream dates'},
    'sina_history': {'markets':['HK','US'],'adjust':['raw'],'intervals':['1d','1wk','1mo'],'note':'Availability varies by market; does not synthesize daily OHLC from sampled minute prices'},
    'yfinance': {'markets':['HK','US'],'adjust':['split_adjusted','total_return'],'intervals':['1d','1wk','1mo','1m','5m','15m','30m','60m']},
    'yahooquery_history': {'markets':['HK','US'],'adjust':['split_adjusted','total_return'],'intervals':['1d','1wk','1mo','1m','5m','15m','30m','60m']},
    'yahoo_chart': {'markets':['HK','US'],'adjust':['split_adjusted'],'intervals':['1d','1wk','1mo','1m','5m','15m','30m','60m']},
}


def history_callbacks(info, interval='1d', days=30, adjust='raw'):
    return {
        'tencent_history':lambda:sources.fetch_tencent_history(info,interval,days,adjust),
        'sina_history':lambda:sources.fetch_sina_history(info,interval,days,adjust),
        'yfinance':lambda:sources.fetch_yfinance_history(info['yahoo_symbol'],interval,days,adjust),
        'yahooquery_history':lambda:sources.fetch_yahooquery_history(info['yahoo_symbol'],interval,days,adjust),
        'yahoo_chart':lambda:sources.fetch_yahoo_chart_history(info['yahoo_symbol'],interval,days,adjust)}


def inspect(symbol,source='all',adjust='raw',days=30):
    info=normalize_symbol(symbol)
    rows=[]
    for name,fn in history_callbacks(info,days=days,adjust=adjust).items():
        if source not in ('all',name):continue
        start=time.monotonic()
        if adjust not in CAPABILITIES[name]['adjust']:
            rows.append({'source':name,'status':'unsupported','adjust':adjust});continue
        try:
            data=call_source(fn,6)
            rows.append({'source':name,'status':'ok' if data else 'empty','count':len(data or []),
                         'elapsed_sec':round(time.monotonic()-start,3),'data':data})
        except Exception as exc:
            rows.append({'source':name,'status':'unavailable','error':str(exc),'elapsed_sec':round(time.monotonic()-start,3)})
    return {'symbol':info['normalized'],'adjust':adjust,'capabilities':CAPABILITIES,'sources':rows}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--symbol');p.add_argument('--source',choices=['all',*CAPABILITIES],default='all')
    p.add_argument('--adjust',choices=['raw','qfq','split_adjusted','total_return'],default='raw')
    p.add_argument('--days',type=int,default=30);p.add_argument('--json',action='store_true')
    args=p.parse_args()
    result=inspect(args.symbol,args.source,args.adjust,args.days) if args.symbol else {'capabilities':CAPABILITIES}
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':main()
