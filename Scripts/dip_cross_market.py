#!/usr/bin/env python3
"""Out-of-sample check of the SOXL dip rule on OTHER markets, unchanged.

The rule was found on SOXL 2024-26 5-min data. Here its hourly proxy (ROC over
12 hourly bars < -2% AND fast MACD(3/6/2) histogram < -0.1% of price, checked
at 15:00 ET, buy ~16:00 at ask, sell next day ~16:00 at bid, 15% stop) and a
volatility-scaled variant (drop threshold = 2% x market vol / SOXL vol) are
applied to every market with no re-tuning. Protection: half size below the
200-day average. Results at 1x notional.
"""
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edges as E  # noqa: E402

ROOT = E.ROOT


def hourly(epic):
    h = pd.read_sql_query(f'SELECT * FROM {epic}_cap_1h ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
    h['t'] = pd.to_datetime(h['timestamp'])
    return h[(h.t.dt.weekday < 5) & (h.t.dt.hour >= 4) & (h.t.dt.hour < 20)].reset_index(drop=True)


def signal(h, drop_pct):
    c = (h.bid_close + h.ask_close) / 2
    m = c.ewm(span=3, adjust=False).mean() - c.ewm(span=6, adjust=False).mean()
    s = ((c / c.shift(12) - 1) * 100 < -drop_pct) & ((m - m.ewm(span=2, adjust=False).mean()) / c < -0.001)
    s14 = pd.Series(s.to_numpy(), index=h['t']).loc[lambda x: x.index.hour == 14]
    s14.index = s14.index.normalize()
    return s14[~s14.index.duplicated()]


def main():
    ref_vol = hourly('SOXL').pipe(lambda h: ((h.bid_close + h.ask_close) / 2).pct_change(12).std())
    out = {}
    rows = []
    for e in E.TRADEABLE:
        h = hourly(e)
        d = E.load(e)
        vol12 = ((h.bid_close + h.ask_close) / 2).pct_change(12).std()
        below = (d['sig'] < d['sig'].rolling(200).mean()).astype(float)
        for name, drop in (('raw2%', 2.0), ('volscaled', 2.0 * vol12 / ref_vol)):
            buy = signal(h, drop).reindex(d.index).fillna(False).astype(float)
            if e in ('BTCUSD', 'ETHUSD', 'SOLUSD', 'GOLD', 'US100', 'US500', 'DE40'):
                pos = buy * (1 - 0.5 * below)
            else:
                pos = buy * (1 - 0.5 * below)
            r = E.mtm(d, pos)
            r = r[r.index >= E.START]
            out[f'dip_{name}_{e}'] = r
            n = int((pos.diff() > 0).sum())
            eq = (1 + r).cumprod()
            tr = r[r.index < '2024-01-01']
            te = r[r.index >= '2024-01-01']
            rows.append({'market': e, 'variant': name, 'drop%': drop, 'trades': n,
                         'sharpe': r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0,
                         '2021-23': (1 + tr).prod(), '2024-26': (1 + te).prod(), 'maxdd': (eq / eq.cummax() - 1).min()})
    df = pd.DataFrame(rows)
    pd.set_option('display.width', 200)
    print(df.sort_values(['variant', 'sharpe'], ascending=[True, False]).to_string(
        index=False, formatters={'drop%': '{:.2f}'.format, 'sharpe': '{:.2f}'.format, '2021-23': '{:.2f}x'.format,
                                 '2024-26': '{:.2f}x'.format, 'maxdd': '{:.0%}'.format}))
    for v in ('raw2%', 'volscaled'):
        x = df[(df.variant == v) & (df.trades >= 15)]
        print(f'\n{v}: {len(x)} markets with >=15 trades, profitable in 2021-23 AND 2024-26: '
              f'{((x["2021-23"] > 1) & (x["2024-26"] > 1)).sum()}, median Sharpe {x.sharpe.median():.2f}')
    pd.DataFrame(out).fillna(0.0).to_pickle('/tmp/claude-0/dip_sleeves.pkl')


if __name__ == '__main__':
    main()
