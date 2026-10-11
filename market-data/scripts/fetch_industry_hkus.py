#!/usr/bin/env python3
"""Yahoo taxonomy directory and paginated, market-scoped industry members (not ETF proxies)."""
import argparse
import json

try:
    from .hkus_runtime import cached_fetch, call_source
except ImportError:
    from hkus_runtime import cached_fetch, call_source


def industry_catalog():
    import yfinance as yf
    from yfinance.const import SECTOR_INDUSTY_MAPPING
    def slug(value):return value.lower().replace(' ', '-')
    rows=[{'sector':sector,'sector_key':slug(sector),'industry':industry,'industry_key':slug(industry)}
          for sector,industries in SECTOR_INDUSTY_MAPPING.items() for industry in sorted(industries)]
    return rows, yf.__version__


def query_industry(action='directory',market='US',industry='',sector='',pages=4,no_cache=False):
    if action not in ('directory','members','profile') or market not in ('US','HK') or not 1<=pages<=20:
        raise ValueError('invalid action/market/pages')
    catalog,version=industry_catalog()
    selected=[item for item in catalog if (not industry or industry in (item['industry'],item['industry_key'])) and (not sector or sector in (item['sector'],item['sector_key']))]
    if not selected:
        raise ValueError('unknown provider taxonomy key; query --action directory first')
    if action!='directory' and (not industry or len(selected)!=1):
        raise ValueError('members/profile requires one exact --industry key')
    if action=='directory':
        return {'status':'ok','data':selected,'meta':{'taxonomy':'Yahoo sector/industry','taxonomy_version':None,
            'source':'yfinance SDK taxonomy catalog','sdk_version':version,'market':market,'count':len(selected),
            'coverage_note':'Taxonomy directory, not evidence that every industry has listed companies in this market.'}}
    def fetch(_):
        import yfinance as yf
        item=selected[0]
        if action=='profile':
            domain=yf.Industry(item['industry_key'],region=market)
            overview=domain.overview
            if not overview:raise ValueError('Yahoo returned no industry profile')
            frame=domain.top_companies
            data={'overview':overview,'top_companies':json.loads(frame.reset_index().to_json(orient='records')) if frame is not None else []}
            return {'status':'ok','data':data,'meta':{'taxonomy':'Yahoo sector/industry','industry':item,
                'market':market,'source':'Yahoo Industry','coverage_limited':True,'coverage_note':'Top companies only; use members for paginated screener membership.'}}
        query=yf.EquityQuery('and',[yf.EquityQuery('eq',['region',market.lower()]),yf.EquityQuery('eq',['industry',item['industry']])])
        rows=[];total=None;offset=0
        for _page in range(pages):
            response=yf.screen(query,size=250,offset=offset,sortField='ticker',sortAsc=True)
            if not isinstance(response,dict) or not isinstance(response.get('quotes'),list):
                raise ValueError('Yahoo screener schema changed')
            batch=response['quotes'];total=response.get('total',total)
            rows.extend(batch);offset+=len(batch)
            if not batch or (total is not None and offset>=total):break
        return {'status':'ok' if rows else 'empty','data':[{'source':'yahoo_screener','raw':row} for row in rows],
            'meta':{'source':'Yahoo Equity Screener','taxonomy':'Yahoo sector/industry','industry':item,'market':market,
                    'count':len(rows),'total':total,'coverage_limited':total is None or len(rows)<total,
                    'effective_at':None,'membership_basis':'current vendor classification; no historical membership guarantee'}}
    value,cache=cached_fetch(f'industry:{action}:{market}:{industry}:{sector}:{pages}',lambda old:call_source(lambda:fetch(old),25),3600,no_cache)
    value['meta'].update(cache)
    return value


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action',choices=['directory','members','profile'],default='directory')
    parser.add_argument('--market',choices=['US','HK'],default='US')
    parser.add_argument('--industry',default='');parser.add_argument('--sector',default='')
    parser.add_argument('--pages',type=int,default=4)
    parser.add_argument('--no-cache',action='store_true');parser.add_argument('--json',action='store_true')
    args=parser.parse_args()
    try:result=query_industry(args.action,args.market,args.industry,args.sector,args.pages,args.no_cache)
    except Exception as exc:
        print(json.dumps({'status':'unavailable','error':f'{type(exc).__name__}: {exc}','data':[]},ensure_ascii=False));raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False,allow_nan=False,indent=2))


if __name__=='__main__':main()
