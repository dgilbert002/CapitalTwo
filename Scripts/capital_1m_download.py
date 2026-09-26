#!/usr/bin/env python3
"""Download Capital.com 1-minute bid/ask candles into database_av.db.

Table <EPIC>_cap_1min: timestamp (US/Eastern, bar start), bid/ask OHLC, volume.
Resumes from the last stored bar, so re-running just tops it up.

    python Scripts/capital_1m_download.py SOXL 2024-01-02
"""
import configparser
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

EPIC = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
FIRST = sys.argv[2] if len(sys.argv) > 2 else '2024-01-02'
DB = 'database_av.db'
TABLE = f'{EPIC}_cap_1min'
BASE = 'https://demo-api-capital.backend-capital.com/api/v1'
WINDOW = timedelta(hours=16)  # 960 one-minute bars < 1000 cap


def login():
    c = configparser.ConfigParser()
    c.read('settings.txt')
    cr = c['CREDENTIALS']
    r = requests.post(BASE + '/session', headers={'X-CAP-API-KEY': cr['api_key']},
                      json={'identifier': cr['email'], 'password': cr['password']}, timeout=30)
    r.raise_for_status()
    return {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}


def main():
    conn = sqlite3.connect(DB)
    conn.execute(f'''CREATE TABLE IF NOT EXISTS {TABLE} (timestamp TEXT PRIMARY KEY,
        bid_open REAL, bid_high REAL, bid_low REAL, bid_close REAL,
        ask_open REAL, ask_high REAL, ask_low REAL, ask_close REAL, volume REAL)''')
    last = conn.execute(f'SELECT MAX(timestamp) FROM {TABLE}').fetchone()[0]
    if last:
        cur = pd.Timestamp(last).tz_localize('America/New_York').tz_convert('UTC').tz_localize(None) + timedelta(minutes=1)
    else:
        cur = pd.Timestamp(FIRST)
    end = datetime.now(timezone.utc).replace(tzinfo=None)
    h, n = login(), 0
    while cur < end:
        nxt = min(cur + WINDOW, end)
        if cur.weekday() >= 5 and nxt.weekday() >= 5:
            cur = nxt
            continue
        r = requests.get(f'{BASE}/prices/{EPIC}', headers=h, timeout=30, params={
            'resolution': 'MINUTE', 'max': 1000,
            'from': cur.strftime('%Y-%m-%dT%H:%M:%S'), 'to': nxt.strftime('%Y-%m-%dT%H:%M:%S')})
        if r.status_code == 401:
            h = login()
            continue
        if r.status_code == 429:
            time.sleep(2)
            continue
        rows = []
        if r.ok:
            for p in r.json().get('prices', []):
                ts = pd.Timestamp(p['snapshotTimeUTC']).tz_localize('UTC').tz_convert('America/New_York')
                rows.append((ts.strftime('%Y-%m-%d %H:%M:%S'),
                             p['openPrice']['bid'], p['highPrice']['bid'], p['lowPrice']['bid'], p['closePrice']['bid'],
                             p['openPrice']['ask'], p['highPrice']['ask'], p['lowPrice']['ask'], p['closePrice']['ask'],
                             float(p.get('lastTradedVolume') or 0)))
        elif r.status_code != 404:
            print('warn', cur, r.status_code, r.text[:150], flush=True)
        conn.executemany(f'INSERT OR REPLACE INTO {TABLE} VALUES (?,?,?,?,?,?,?,?,?,?)', rows)
        n += len(rows)
        cur = nxt
        if cur.hour < 1:
            conn.commit()
            print(cur.date(), n, flush=True) if cur.day == 1 else None
        time.sleep(0.11)
    conn.commit()
    tot = conn.execute(f'SELECT COUNT(*), MIN(timestamp), MAX(timestamp) FROM {TABLE}').fetchone()
    print(f'{TABLE}: +{n:,} rows, total {tot[0]:,} ({tot[1]} -> {tot[2]})')


if __name__ == '__main__':
    main()
