#!/usr/bin/env python3
"""Company/industry keyword news. Return source records without semantic filtering."""
import argparse
import json
import time
import queue
import threading
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

try:
    from .hkus_common import normalize_symbol, call_source
    from .hkus_data_sources import _http_session
    from .hkus_runtime import submit_source
except ImportError:
    from hkus_common import normalize_symbol, call_source
    from hkus_data_sources import _http_session
    from hkus_runtime import submit_source

TZ=ZoneInfo("Asia/Shanghai")


def fetch_news(keyword, days=7, limit=100, pages=2):
    now=datetime.now(TZ)
    start=(now-timedelta(days=days-1)).replace(hour=0,minute=0,second=0,microsecond=0)
    rows=[];errors=[];truncated=False
    session=_http_session()
    for page in range(1,pages+1):
        param={"uid":"","keyword":keyword,"type":["cmsArticleWebOld"],
               "client":"web","clientType":"web","clientVersion":"curr",
               "param":{"cmsArticleWebOld":{"searchScope":"default","sort":"time",
                         "pageIndex":page,"pageSize":50,"preTag":"","postTag":""}}}
        try:
            response=session.get("https://search-api-web.eastmoney.com/search/jsonp",
                                 params={"cb":"jQuery","param":json.dumps(param,ensure_ascii=False)},timeout=6)
            response.raise_for_status()
            text=response.text.strip()
            obj=json.loads(text if text.startswith("{") else text[text.index("(")+1:text.rindex(")")])
            batch=obj["result"]["cmsArticleWebOld"]
            if not isinstance(batch,list):raise ValueError("upstream news schema changed")
        except Exception as exc:
            errors.append(f"{type(exc).__name__}: {str(exc)[:220]}");break
        before_window=False
        for item in batch:
            try:
                stamp=datetime.fromisoformat(item["date"]).replace(tzinfo=TZ)
            except (ValueError,KeyError,TypeError):
                continue
            if stamp < start:before_window=True
            if start <= stamp <= now:rows.append(item)
        truncated=len(batch)>=50
        if before_window or not truncated:
            truncated=False;break
    status="partial" if errors and rows else "unavailable" if errors else "ok" if rows else "empty"
    return {"status":status,"source":"eastmoney_search","keyword":keyword,
            "meta":{"window_start":start.isoformat(),"window_end":now.isoformat(),
                    "fetched_at":datetime.now(TZ).isoformat(),"count":min(limit,len(rows)),
                    "coverage_limited":truncated or len(rows)>limit,"errors":errors,
                    "notes":"data retains upstream fields/title/content; no semantic filtering, classification or sentiment. content is a search snippet."},
            "data":rows[:limit]}



def fetch_yahoo_news(yahoo_symbol, limit=100):
    import yfinance as yf
    return yf.Search(yahoo_symbol, max_results=0, news_count=limit, timeout=6, raise_errors=True).news


def _news_time(item):
    content=item.get("content",item)
    raw=content.get("pubDate") or content.get("displayTime") or item.get("providerPublishTime")
    try:
        if isinstance(raw,(int,float)):
            return datetime.fromtimestamp(raw,TZ)
        parsed=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
        return parsed.replace(tzinfo=TZ) if parsed.tzinfo is None else parsed.astimezone(TZ)
    except (TypeError,ValueError,OverflowError):
        return None


def run(symbol=None,keyword=None,days=7,limit=100,pages=2,max_seconds=20,source="all"):
    now=datetime.now(TZ)
    start=(now-timedelta(days=days-1)).replace(hour=0,minute=0,second=0,microsecond=0)
    info=normalize_symbol(symbol) if symbol else None
    jobs={}
    if info and source in ("all","yahoo"):
        jobs["yahoo_news"]=lambda:fetch_yahoo_news(info["yahoo_symbol"],limit)
    if keyword and source in ("all","eastmoney"):
        jobs["eastmoney_search"]=lambda:fetch_news(keyword,days,limit,pages)
    if not jobs:raise ValueError("Yahoo requires --symbol; Eastmoney requires --keyword")
    finished=queue.Queue();deadline=time.monotonic()+max_seconds
    def worker(name,fn):
        started=time.monotonic()
        try:
            payload=fn()
            if name=="eastmoney_search":
                rows=payload["data"]
                diagnostic={"source":name,"status":payload["status"],"coverage_limited":payload["meta"]["coverage_limited"],"errors":payload["meta"]["errors"]}
            else:
                if not isinstance(payload,list):raise ValueError("Yahoo news schema changed")
                # Unknown timestamps are retained and flagged, rather than silently dropped.
                rows=[item for item in payload if (stamp:=_news_time(item)) is None or start<=stamp<=now]
                diagnostic={"source":name,"status":"ok" if rows else "empty","fetched":len(payload),"coverage_limited":True,"coverage_reason":"Yahoo search is a bounded candidate set, not a complete news archive",
                            "unknown_timestamps":sum(_news_time(item) is None for item in rows)}
        except Exception as exc:
            rows=[];diagnostic={"source":name,"status":"unavailable","error":f"{type(exc).__name__}: {str(exc)[:240]}"}
        diagnostic["elapsed_sec"]=round(time.monotonic()-started,3)
        finished.put((name,rows,diagnostic))
    futures={name:submit_source(lambda name=name,fn=fn:worker(name,fn)) for name,fn in jobs.items()}
    pending=set(jobs);data=[];diagnostics=[]
    while pending:
        try:name,rows,diagnostic=finished.get(timeout=max(0,deadline-time.monotonic()))
        except queue.Empty:break
        pending.remove(name)
        data.extend({"source":name,"raw":item} for item in rows)
        diagnostics.append(diagnostic)
    for name in pending:futures[name].cancel()
    diagnostics.extend({"source":name,"status":"timeout","error":"overall deadline exceeded"} for name in sorted(pending))
    diagnostics.sort(key=lambda item:item["source"])
    failed=any(item["status"] in ("unavailable","partial","timeout") for item in diagnostics)
    success=any(item["status"] in ("ok","empty","partial") for item in diagnostics)
    status="partial" if failed and success else "unavailable" if failed else "ok" if data else "empty"
    return {"status":status,"symbol":info["normalized"] if info else None,"keyword":keyword,
            "meta":{"window_start":start.isoformat(),"window_end":now.isoformat(),"fetched_at":datetime.now(TZ).isoformat(),
                    "count":len(data),"limit_per_source":limit,"sources":diagnostics,
                    "notes":"data contains unmodified provider records under raw; no semantic filtering, classification, deduplication or sentiment. Content may be snippets; source/page limits apply."},
            "data":data}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--keyword",help="Explicit company/industry keyword for Eastmoney; no automatic aliases")
    parser.add_argument("--symbol",help="Yahoo security identity, e.g. 09988.HK or NYSE:BABA")
    parser.add_argument("--source",choices=["all","yahoo","eastmoney"],default="all")
    parser.add_argument("--days",type=int,default=7)
    parser.add_argument("--limit",type=int,default=100)
    parser.add_argument("--pages",type=int,default=2)
    parser.add_argument("--max-seconds",type=float,default=20)
    parser.add_argument("--json",action="store_true")
    args=parser.parse_args()
    if not (args.keyword or args.symbol) or not 1<=args.days<=366 or not 1<=args.limit<=200 or not 1<=args.pages<=5 or not 1<=args.max_seconds<=60:
        parser.error("symbol or keyword required; days=1..366, limit=1..200, pages=1..5, max-seconds=1..60")
    try:
        result=run(args.symbol,args.keyword,args.days,args.limit,args.pages,args.max_seconds,args.source)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False))
    if result["status"]=="unavailable":raise SystemExit(1)


if __name__=="__main__":main()
