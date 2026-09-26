#!/usr/bin/env python3
"""Extend an Alpha Vantage 5-min table with Capital.com candles up to now.

Writes <SYMBOL>_merged_5min: the original AV rows plus Capital.com mid-price
candles (bid/ask average) after the last AV timestamp, in US/Eastern time,
04:00-20:00 only, to match the AV extended-hours format.
"""
import configparser
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

SYMBOL = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
DB = 'database_av.db'
BASE = 'https://demo-api-capital.backend-capital.com/api/v1'


def login():
    c = configparser.ConfigParser()
    c.read('settings.txt')
    cr = c['CREDENTIALS']
    r = requests.post(BASE + '/session', headers={'X-CAP-API-KEY': cr['api_key']},
                      json={'identifier': cr['email'], 'password': cr['password']}, timeout=30)
    r.raise_for_status()
    return {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}


def mid(p):
    return (p['bid'] + p['ask']) / 2


def main():
    conn = sqlite3.connect(DB)
    av = pd.read_sql_query(f'SELECT * FROM {SYMBOL}_av_5min', conn)
    last = pd.to_datetime(av['timestamp']).max()
    start = last.tz_localize('America/New_York').tz_convert('UTC').tz_localize(None) + timedelta(minutes=5)
    end = datetime.now(timezone.utc).replace(tzinfo=None)

    h = login()
    rows, cur = [], start
    while cur < end:
        nxt = min(cur + timedelta(days=3), end)  # 3 days * 288 bars < 1000 cap
        r = requests.get(f'{BASE}/prices/{SYMBOL}', headers=h, timeout=30, params={
            'resolution': 'MINUTE_5', 'max': 1000,
            'from': cur.strftime('%Y-%m-%dT%H:%M:%S'), 'to': nxt.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 401:
            h = login()
            continue
        if r.ok:
            for p in r.json().get('prices', []):
                rows.append({'utc': p['snapshotTimeUTC'], 'open': mid(p['openPrice']), 'high': mid(p['highPrice']),
                             'low': mid(p['lowPrice']), 'close': mid(p['closePrice']),
                             'volume': float(p.get('lastTradedVolume') or 0)})
        elif r.status_code != 404:  # 404 = no prices in window (weekend/holiday)
            print('warn', cur, r.status_code, r.text[:200])
        cur = nxt
        time.sleep(0.12)  # stay under ~10 req/s

    new = pd.DataFrame(rows).drop_duplicates('utc')
    et = pd.to_datetime(new['utc']).dt.tz_localize('UTC').dt.tz_convert('America/New_York').dt.tz_localize(None)
    new['timestamp'] = et.dt.strftime('%Y-%m-%d %H:%M:%S')
    t = et.dt.time
    new = new[(et.dt.weekday < 5) & (t >= pd.Timestamp('04:00').time()) & (t <= pd.Timestamp('20:00').time())]
    new = new[['timestamp', 'open', 'high', 'low', 'close', 'volume']]

    merged = pd.concat([av, new]).drop_duplicates('timestamp').sort_values('timestamp')
    merged.to_sql(f'{SYMBOL}_merged_5min', conn, if_exists='replace', index=False)
    conn.close()
    print(f'AV rows {len(av):,} (to {last}) + Capital rows {len(new):,} '
          f'(to {new["timestamp"].max() if len(new) else "-"}) -> {SYMBOL}_merged_5min')


if __name__ == '__main__':
    main()
