#!/usr/bin/env python3
"""Download Capital.com hourly bid/ask candles for many epics into database_av.db
(table <EPIC>_cap_1h, timestamps US/Eastern bar start) plus market metadata.

    python Scripts/capital_hourly_download.py SOXL TQQQ US100 BTCUSD ...
"""
import json
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from bot.capital_rest import CapitalREST  # noqa: E402
from bot.dip_bot import load_config  # noqa: E402

START = pd.Timestamp('2021-01-01')


def main(epics):
    c = load_config()
    api = CapitalREST(c['api_key'], c['email'], c['password'], 'demo')
    api.login()
    conn = sqlite3.connect(os.path.join(ROOT, 'database_av.db'))
    meta = {}
    for e in epics:
        m = api.market(e)
        meta[e] = {'type': m['instrument']['type'], 'margin_pct': m['instrument'].get('marginFactor'),
                   'name': m['instrument'].get('name'), 'min_size': m['dealingRules']['minDealSize']['value'],
                   'overnight': m['instrument'].get('overnightFee')}
        df = api.candles(e, START, pd.Timestamp.utcnow().tz_localize(None), 'HOUR', pd.Timedelta(days=40))
        if df.empty:
            print(e, 'no data', flush=True)
            continue
        df.insert(0, 'timestamp', df.pop('t').dt.strftime('%Y-%m-%d %H:%M:%S'))
        df.to_sql(f'{e}_cap_1h', conn, if_exists='replace', index=False)
        print(f"{e:8s} {len(df):6d} bars {df['timestamp'].iloc[0]} -> {df['timestamp'].iloc[-1]}  margin {meta[e]['margin_pct']}%",
              flush=True)
    with open(os.path.join(ROOT, 'Results', 'capital_market_meta.json'), 'w') as f:
        json.dump(meta, f, indent=1)


if __name__ == '__main__':
    main(sys.argv[1:])
