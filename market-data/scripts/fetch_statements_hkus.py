#!/usr/bin/env python3
"""Provider-native financial statements and SEC XBRL facts with filing-date as-of queries."""
import argparse
from datetime import date
import json

try:
    from .hkus_common import normalize_symbol, pick_first_available
    from .hkus_runtime import cached_fetch
    from .fetch_disclosures_hkus import resolve_cik, request_json
except ImportError:
    from hkus_common import normalize_symbol, pick_first_available
    from hkus_runtime import cached_fetch
    from fetch_disclosures_hkus import resolve_cik, request_json


def select_facts(obj, as_of=None, start=None, end=None):
    rows = []
    for taxonomy, concepts in obj.get('facts', {}).items():
        for concept, details in concepts.items():
            for unit, facts in details.get('units', {}).items():
                for fact in facts:
                    if as_of and (not fact.get('filed') or fact['filed'] > as_of):
                        continue
                    if start and fact.get('end', '') < start:
                        continue
                    if end and fact.get('end', '') > end:
                        continue
                    rows.append({'taxonomy':taxonomy,'concept':concept,'label':details.get('label'),
                                 'unit':unit,'raw':fact})
    return rows


def sec_facts(symbol=None, cik=None, as_of=None, start=None, end=None, no_cache=False):
    for value in (as_of, start, end):
        if value:
            date.fromisoformat(value)
    identity = resolve_cik(symbol, cik)
    obj, cache = cached_fetch(f'sec-facts:{identity}', lambda _: request_json(
        f'https://data.sec.gov/api/xbrl/companyfacts/CIK{identity}.json',sec=True), 3600, no_cache)
    rows = select_facts(obj, as_of, start, end)
    return {'status':'ok' if rows else 'empty','data':rows,'meta':dict(cache, source='SEC companyfacts',
        cik=identity, issuer_name=obj.get('entityName'), as_of=as_of, count=len(rows),
        time_basis='SEC filed date, day precision; not an intraday availability guarantee',
        coverage_note='Standard-taxonomy entity-wide XBRL facts only; custom taxonomy/untagged statements may be absent. Versions and units are retained; no fabricated statement mapping.')}


def yahoo_statements(symbol, kind='income', period='annual', no_cache=False):
    if kind not in ('income','balance','cashflow') or period not in ('annual','quarterly'):
        raise ValueError('kind=income/balance/cashflow; period=annual/quarterly')
    info = normalize_symbol(symbol)
    def fetch(_):
        import yfinance as yf
        ticker = yf.Ticker(info['yahoo_symbol'])
        methods = {'income':ticker.get_income_stmt,'balance':ticker.get_balance_sheet,'cashflow':ticker.get_cashflow}
        frame = methods[kind](freq='yearly' if period == 'annual' else 'quarterly')
        if frame is None or frame.empty:
            raise ValueError('Yahoo returned no statement')
        # Line-item names and values remain provider-native. Currency is deliberately not inferred.
        rows = [{'period_end':stamp.date().isoformat(), 'raw':json.loads(frame[[stamp]].T.to_json(orient='records'))[0]} for stamp in frame.columns]
        return {'status':'ok','symbol':info['normalized'],'data':rows,'meta':{
            'source':'yfinance','kind':kind,'period':period,'currency':None,'unit':'provider_native',
            'as_of_supported':False,'coverage_note':'Current vendor statement snapshot; publication dates and historical revisions are not established.'}}
    result, cache = cached_fetch(f'yahoo-statements:{info["normalized"]}:{kind}:{period}',lambda old: pick_first_available(
        {'yfinance':lambda:fetch(old)},['yfinance'],health_scope='statements')['data'],3600,no_cache)
    result['meta'].update(cache)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--symbol')
    parser.add_argument('--cik')
    parser.add_argument('--source',choices=['yahoo','sec'],default='yahoo')
    parser.add_argument('--kind',choices=['income','balance','cashflow'],default='income')
    parser.add_argument('--period',choices=['annual','quarterly'],default='annual')
    parser.add_argument('--as-of',help='SEC only: filed date cutoff YYYY-MM-DD')
    parser.add_argument('--start',help='SEC fact period-end lower bound')
    parser.add_argument('--end',help='SEC fact period-end upper bound')
    parser.add_argument('--no-cache',action='store_true')
    parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:
        if args.source=='sec':
            result=sec_facts(args.symbol,args.cik,args.as_of,args.start,args.end,args.no_cache)
        else:
            if args.as_of or args.start or args.end:
                raise ValueError('Historical visibility/period filtering requires --source sec; Yahoo has no verified filing timestamps')
            if not args.symbol:
                raise ValueError('--symbol required')
            result=yahoo_statements(args.symbol,args.kind,args.period,args.no_cache)
    except Exception as exc:
        print(json.dumps({'status':'unavailable','error':f'{type(exc).__name__}: {exc}','data':[]},ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':main()
