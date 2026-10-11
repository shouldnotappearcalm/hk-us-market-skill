#!/usr/bin/env python3
"""Official HKEX/SEC disclosures and explicitly supplied company RSS; no semantic filtering."""
import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import re
from pathlib import Path
from hashlib import sha256
from urllib.parse import urljoin, urlparse
from zoneinfo import ZoneInfo

try:
    from .hkus_common import normalize_symbol
    from .hkus_data_sources import _http_session
    from .hkus_runtime import cached_fetch, call_source
except ImportError:
    from hkus_common import normalize_symbol
    from hkus_data_sources import _http_session
    from hkus_runtime import cached_fetch, call_source

SEC_AGENT = 'stock-data-skill/1.0 (+https://github.com/shouldnotappearcalm/hk-us-market-skill)'


def request_json(url, params=None, sec=False):
    headers = {'User-Agent': os.environ.get('SEC_USER_AGENT', SEC_AGENT)} if sec else {}
    response = _http_session().get(url, params=params, headers=headers, timeout=6)
    response.raise_for_status()
    text = response.text.strip()
    # HKEX predictive stock lookup uses its documented JSONP callback wrapper.
    if text.startswith('callback('):
        text = text[len('callback('):text.rindex(')')]
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError('unexpected upstream schema')
    return value


def resolve_cik(symbol, cik=None):
    if cik:
        value = str(cik).removeprefix('CIK')
        if not value.isdigit() or not 0 < int(value) < 10**10:
            raise ValueError('CIK must be 1..10 digits')
        return str(int(value)).zfill(10)
    info = normalize_symbol(symbol)
    if info['market'] != 'US':
        raise ValueError('SEC requires a US symbol or explicit --cik')
    def lookup(_):
        try:
            mapping = request_json('https://www.sec.gov/files/company_tickers.json', sec=True)
            matches = [item for item in mapping.values() if item.get('ticker', '').replace('.', '-') == info['yahoo_symbol']]
            if len(matches) == 1:
                return str(matches[0]['cik_str']).zfill(10)
        except Exception:
            pass
        # Yahoo is only an identity discovery fallback; disclosure data still comes from SEC.
        import yfinance as yf
        filings = yf.Ticker(info['yahoo_symbol']).sec_filings
        candidates = set()
        for item in filings or []:
            for link in (item.get('edgarUrl'), *(item.get('exhibits') or {}).values()):
                path = urlparse(str(link or '')).path
                match = re.search(r'/Archives/edgar/data/(\d+)/', path)
                if match:
                    candidates.add(match.group(1).zfill(10))
        if len(candidates) != 1:
            raise ValueError('CIK identity unavailable; provide --cik from the official issuer record')
        return candidates.pop()
    value, _ = cached_fetch(f'sec-cik:{info["yahoo_symbol"]}', lambda old: call_source(lambda: lookup(old), 15), 7*86400)
    return value


def sec_disclosures(symbol=None, cik=None, days=30, limit=100, forms=None, no_cache=False):
    identity = resolve_cik(symbol, cik)
    def fetch(_):
        obj = request_json(f'https://data.sec.gov/submissions/CIK{identity}.json', sec=True)
        recent = obj.get('filings', {}).get('recent')
        if not isinstance(recent, dict) or 'accessionNumber' not in recent:
            raise ValueError('SEC submissions schema changed')
        start = (datetime.now(timezone.utc) - timedelta(days=days-1)).date().isoformat()
        rows = []
        for index, accession in enumerate(recent['accessionNumber']):
            raw = {key: values[index] for key, values in recent.items() if isinstance(values, list) and index < len(values)}
            if raw.get('filingDate', '') < start or (forms and raw.get('form') not in forms):
                continue
            document = raw.get('primaryDocument') or ''
            url = f'https://www.sec.gov/Archives/edgar/data/{int(identity)}/{accession.replace("-", "")}/{document}'
            rows.append({'source': 'sec', 'url': url, 'raw': raw})
        return {'status': 'ok' if rows else 'empty', 'data': rows[:limit], 'meta': {
            'source': 'SEC submissions', 'cik': identity, 'issuer_name': obj.get('name'),
            'window_start': start, 'forms': forms, 'count': min(len(rows), limit),
            'coverage_limited': len(rows) > limit or bool(obj.get('filings', {}).get('files')),
            'coverage_note': 'Recent submissions only; older archive files are not fetched automatically. Raw filing fields retained.'}}
    result, cache = cached_fetch(f'sec-filings:{identity}:{days}:{limit}:{forms}', fetch, 120, no_cache)
    result['meta'].update(cache)
    return result


def hkex_disclosures(symbol, days=30, limit=100, no_cache=False, language='ZH'):
    info = normalize_symbol(symbol)
    if info['market'] != 'HK':
        raise ValueError('HKEX requires a Hong Kong symbol')
    code = str(int(info['yahoo_symbol'].split('.')[0])).zfill(5)
    language = language.upper()
    if language not in ('ZH', 'EN'):
        raise ValueError('language=ZH/EN')
    def fetch(_):
        stocks = request_json('https://www1.hkexnews.hk/search/prefix.do', {
            'lang': language, 'type': 'A', 'name': code, 'market': 'SEHK', 'callback': 'callback'})
        matches = [item for item in stocks.get('stockInfo', []) if str(item.get('code', '')).zfill(5) == code]
        if len(matches) != 1:
            raise ValueError('HKEX issuer identity unavailable or ambiguous')
        issuer = matches[0]
        now = datetime.now(ZoneInfo('Asia/Hong_Kong'))
        start = now - timedelta(days=days-1)
        obj = request_json('https://www1.hkexnews.hk/search/titleSearchServlet.do', {
            'sortDir': '1', 'sortByOptions': 'DateTime', 'category': '0', 'market': 'SEHK',
            'stockId': issuer['stockId'], 'documentType': '-1', 'fromDate': start.strftime('%Y%m%d'),
            'toDate': now.strftime('%Y%m%d'), 'title': '', 'searchType': '0', 't1code': '-2',
            't2Gcode': '-2', 't2code': '-2', 'rowRange': str(limit), 'lang': language})
        raw = obj.get('result')
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(rows, list):
            raise ValueError('HKEX disclosure schema changed')
        data = [{'source': 'hkex', 'url': urljoin('https://www1.hkexnews.hk', item.get('FILE_LINK') or ''), 'raw': item} for item in rows[:limit]]
        total = int(obj.get('recordCnt') or len(rows))
        return {'status': 'ok' if data else 'empty', 'symbol': info['normalized'], 'data': data, 'meta': {
            'source': 'HKEXnews', 'issuer': issuer, 'timezone': 'Asia/Hong_Kong',
            'window_start': start.date().isoformat(), 'window_end': now.date().isoformat(),
            'count': len(data), 'total': total, 'coverage_limited': total > len(data),
            'has_next_row': obj.get('hasNextRow'), 'language': language}}
    result, cache = cached_fetch(f'hkex:{code}:{days}:{limit}:{language}', fetch, 120, no_cache)
    result['meta'].update(cache)
    return result


def fetch_rss(url, days=30, limit=100, no_cache=False):
    if urlparse(url).scheme not in ('http', 'https'):
        raise ValueError('RSS requires an explicit HTTP(S) URL')
    def fetch(_):
        import feedparser
        import calendar
        response = _http_session().get(url, timeout=6)
        response.raise_for_status()
        if len(response.content) > 5*1024*1024:
            raise ValueError('RSS exceeds 5 MiB')
        feed = feedparser.parse(response.content)
        if feed.bozo and not feed.entries:
            raise ValueError(f'invalid RSS/Atom: {feed.bozo_exception}')
        start = datetime.now(timezone.utc) - timedelta(days=days)
        rows = []
        unknown = 0
        for entry in feed.entries:
            stamp = entry.get('published_parsed') or entry.get('updated_parsed')
            if stamp and datetime.fromtimestamp(calendar.timegm(stamp), timezone.utc) < start:
                continue
            if not stamp:
                unknown += 1
            rows.append({'source': 'company_rss', 'raw': dict(entry)})
        return {'status': 'ok' if rows else 'empty', 'data': rows[:limit], 'meta': {
            'source_url': url, 'count': min(len(rows), limit), 'unknown_timestamps': unknown,
            'coverage_limited': True, 'coverage_note': 'Feed contains its publisher-selected entries; no semantic filtering.',
            'raw_feed': response.text}}
    result, cache = cached_fetch(f'rss:{url}:{days}:{limit}', fetch, 120, no_cache)
    result['meta'].update(cache)
    return result


def fetch_document(url, output=None, max_bytes=5*1024*1024):
    if urlparse(url).scheme not in ("http", "https"):
        raise ValueError("document URL must use HTTP(S)")
    headers = {"User-Agent":os.environ.get("SEC_USER_AGENT",SEC_AGENT)} if urlparse(url).hostname in ("www.sec.gov","data.sec.gov") else {}
    with _http_session().get(url,headers=headers,timeout=6,stream=True) as response:
        response.raise_for_status()
        parts=[];size=0
        for chunk in response.iter_content(65536):
            size+=len(chunk)
            if size>max_bytes:raise ValueError("document exceeds requested size limit")
            parts.append(chunk)
        data=b"".join(parts)
        content_type=response.headers.get("Content-Type","")
        meta={"source_url":url,"resolved_url":response.url,"content_type":content_type,"bytes":size,"sha256":sha256(data).hexdigest()}
        if output:
            path=Path(output).expanduser().resolve()
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data);meta["output_path"]=str(path)
            return {"status":"ok","meta":meta,"data":[]}
        if "text" not in content_type and "xml" not in content_type and "json" not in content_type:
            raise ValueError("binary document requires --output; use the original attachment without lossy extraction")
        return {"status":"ok","meta":meta,"data":{"raw":data.decode(response.encoding or "utf-8",errors="replace")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--document-url',help='Explicit original article/filing/attachment URL')
    parser.add_argument('--output',help='Save original document bytes; required for PDF/binary attachments')
    parser.add_argument('--symbol')
    parser.add_argument('--cik', help='Explicit SEC CIK; avoids dependence on ticker discovery')
    parser.add_argument('--rss-url', help='Explicit company IR/RSS/Atom URL')
    parser.add_argument('--days', type=int, default=30)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--forms', help='Explicit SEC form types, comma separated; default retains every type')
    parser.add_argument('--language', choices=['ZH','EN'], default='ZH')
    parser.add_argument('--no-cache', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.days <= 365 or not 1 <= args.limit <= 1000:
        parser.error('days=1..365; limit=1..1000')
    try:
        if args.document_url:
            result = fetch_document(args.document_url,args.output)
        elif args.rss_url:
            result = fetch_rss(args.rss_url, args.days, args.limit, args.no_cache)
        elif args.cik or (args.symbol and normalize_symbol(args.symbol)['market'] == 'US'):
            result = sec_disclosures(args.symbol, args.cik, args.days, args.limit, args.forms.split(',') if args.forms else None, args.no_cache)
        elif args.symbol:
            result = hkex_disclosures(args.symbol, args.days, args.limit, args.no_cache, args.language)
        else:
            parser.error('provide --symbol, --cik or --rss-url')
    except Exception as exc:
        print(json.dumps({'status':'unavailable','error':f'{type(exc).__name__}: {exc}','data':[]},ensure_ascii=False))
        raise SystemExit(1)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == '__main__':
    main()
