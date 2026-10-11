#!/usr/bin/env python3
"""Vendor security search with raw candidate rows; no guessed ticker aliases."""
import argparse
import json

try:
    from .hkus_data_sources import _http_session
except ImportError:
    from hkus_data_sources import _http_session


def search(keyword):
    response=_http_session().get('https://smartbox.gtimg.cn/s3/',params={'v':'2','t':'all','c':'1','q':keyword},timeout=6)
    response.raise_for_status()
    text=response.text.strip()
    if not text.startswith('v_hint='):raise ValueError('Tencent search schema changed')
    encoded=text.split('=',1)[1].strip().rstrip(';')
    value=json.loads(encoded)
    original_rows=encoded.strip(chr(34)).split('^')
    rows=[]
    for original,record in zip(original_rows,value.split('^')):
        fields=record.split('~')
        if len(fields)<3:continue
        market,code,name=fields[:3]
        if market not in ('hk','us'):continue
        # Strip the exchange suffix, retaining class-share periods (BRK.B.N -> BRK.B).
        ticker=code.rsplit('.',1)[0] if market=='us' and code.rsplit('.',1)[-1].upper() in ('N','OQ','A') else code
        name=json.loads(chr(34)+name.replace(chr(34),'\\'+chr(34))+chr(34))
        rows.append({'market':market.upper(),'code':ticker.upper() if market=='us' else ticker,'name':name,'raw':original})
    return {'status':'ok' if rows else 'empty','data':rows,'meta':{'source':'Tencent smartbox','keyword':keyword,'count':len(rows),'coverage_limited':True}}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('keyword');p.add_argument('--json',action='store_true');args=p.parse_args()
    try:result=search(args.keyword)
    except Exception as exc:
        print(json.dumps({'status':'unavailable','error':str(exc),'data':[]},ensure_ascii=False));raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
