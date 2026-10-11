"""Exchange schedules with explicit offsets; cache schedules separately from market data."""
from datetime import datetime, timezone
from importlib.metadata import version
import pandas as pd

try:
    from .hkus_runtime import cached_fetch
except ImportError:
    from hkus_runtime import cached_fetch


def _schedule(market,year):
    name='XHKG' if market=='HK' else 'XNYS'
    def load(_):
        import exchange_calendars as xcals
        cal=xcals.get_calendar(name,start=f'{year-1}-01-01',end=f'{year+1}-12-31')
        rows=[]
        for label,row in cal.schedule.iterrows():
            rows.append({'date':label.date().isoformat(),**{key:stamp.isoformat() if pd.notna(stamp) else None for key,stamp in row.items()}})
        return rows
    rows,_=cached_fetch(f'exchange-schedule:{name}:{year}:{version("exchange-calendars")}',load,86400)
    return rows


def latest_completed_session(market, now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    if now.tzinfo is None:raise ValueError('now must have an explicit timezone')
    rows=_schedule(market,now.year)
    complete=[row['date'] for row in rows if pd.Timestamp(row['close'])<=now]
    if not complete:raise ValueError('calendar has no completed session in its coverage')
    return max(complete)


def freshness(trade_date,market):
    try:
        expected=latest_completed_session(market)
        return {'expected_completed_session':expected,'stale':trade_date<expected,'data_time':trade_date,'calendar':'XHKG' if market=='HK' else 'XNYS'}
    except (ImportError,ValueError) as exc:
        return {'data_time':trade_date,'stale':None,'calendar_error':str(exc)}


def regular_session_state(market,now=None):
    now=pd.Timestamp(now or datetime.now(timezone.utc))
    day=now.tz_convert('Asia/Hong_Kong' if market=='HK' else 'America/New_York').date().isoformat()
    row=next((row for row in _schedule(market,now.year) if row['date']==day),None)
    if row is None or not pd.Timestamp(row['open'])<=now<pd.Timestamp(row['close']):return 'CLOSED'
    if row.get('break_start') and pd.Timestamp(row['break_start'])<=now<pd.Timestamp(row['break_end']):return 'BREAK'
    return 'REGULAR'
