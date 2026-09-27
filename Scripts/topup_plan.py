#!/usr/bin/env python3
"""Simulate the user's plan: start $1,000, add $100/month for up to 24 months,
stop adding once the account reaches $10,000. Every possible start month is
tried; results use realistic stop fills (gap price) for CapitalTwo2.0 trades."""
import json, sys, os
import numpy as np, pandas as pd, mysql.connector
sys.path.insert(0, 'Scripts'); sys.path.insert(0, '.')

def plan(ret_by_date, starts, end):
    out = []
    for s in starts:
        r = ret_by_date[ret_by_date.index >= s]
        bal, dep, months = 1000.0, 1000.0, 0
        cur = s.to_period('M')
        for d, x in r.items():
            p = d.to_period('M')
            while cur < p:
                cur += 1
                if months < 24 and bal < 10000:
                    bal += 100; dep += 100; months += 1
            bal = max(bal * (1 + x), 0.0)
        out.append((s, dep, bal))
    return pd.DataFrame(out, columns=['start', 'deposited', 'final'])

def app_strategy(cur, name, lev, sl, o):
    cur.execute("select trades from backtestResults where runId=2 and indicatorName=%s and leverage=%s and stopLoss=%s order by totalReturn desc limit 1", (name, lev, sl))
    t = pd.DataFrame(json.loads(cur.fetchone()['trades']))
    bb = t.balance_after - t.net_pnl; r = t.net_pnl / bb
    op = pd.to_datetime(t.exit_time).map(lambda x: o.get(x, np.nan))
    gap = (t.exit_reason == 'stop_loss') & (op < t.exit_price)
    fill = np.where(gap, op, t.exit_price)
    r2 = (r - t.contracts * (t.exit_price - fill) / bb).clip(lower=-1)
    return pd.Series(r2.values, index=pd.to_datetime(t.entry_time.str[:10])).groupby(level=0).apply(lambda x: np.prod(1 + x) - 1)

def main():
    c = mysql.connector.connect(user='ct', password='ctpass', database='capitaltwo'); cur = c.cursor(dictionary=True)
    cur.execute("select timestamp,(open_bid+open_ask)/2 o from candles where epic='SOXL' and timeframe='5m'")
    cd = pd.DataFrame(cur.fetchall()); cd['timestamp'] = pd.to_datetime(cd.timestamp); o = cd.set_index('timestamp').o.astype(float)
    S = {}
    for n, l, s in [('iftrsi_extreme_oversold', 5, 2), ('price_above_vwap', 4, 2.5), ('price_above_vwap', 3, 2), ('supertrend_bullish', 5, 2), ('adx_increasing', 3, 2)]:
        S[f'App: {n} {l}x SL{s}'] = app_strategy(cur, n, l, s, o)
    ex = pd.read_pickle('/tmp/claude-0/exact_portfolio.pkl')
    for lev in (3, 4, 5):
        r = ex['size_SOXL'].fillna(0) * lev * 0.95 * ex['pnl_SOXL'].fillna(0)
        S[f'SOXL dip bot {lev}x (exact 1-min)'] = r.clip(lower=-1)
    sl = pd.read_pickle('/tmp/claude-0/sleeves.pkl')['soxl_dip']
    for lev in (3, 5):
        S[f'SOXL dip bot {lev}x (hourly 2021-26, incl. 2022 crash)'] = (sl * lev * 0.95).clip(lower=-1)
    rows = []
    for k, r in S.items():
        r = r.sort_index()
        end = r.index[-1]
        starts = pd.date_range(r.index[0], end - pd.DateOffset(months=12), freq='MS')
        res = plan(r, starts, end)
        years = ((end - res.start).dt.days / 365.25)
        rows.append({'strategy': k, 'start months tried': len(res),
                     'median deposited': res.deposited.median(), 'median final': res.final.median(),
                     'worst final': res.final.min(), 'best final': res.final.max(),
                     'lost money': (res.final < res.deposited).mean(), 'reached $10k': (res.final >= 10000).mean(),
                     'reached $100k': (res.final >= 100000).mean(), 'avg years held': years.mean()})
    df = pd.DataFrame(rows)
    pd.set_option('display.width', 250)
    fm = {c: '${:,.0f}'.format for c in ['median deposited', 'median final', 'worst final', 'best final']}
    fm.update({c: '{:.0%}'.format for c in ['lost money', 'reached $10k', 'reached $100k']}); fm['avg years held'] = '{:.1f}'.format
    print(df.to_string(index=False, formatters=fm))
main()
