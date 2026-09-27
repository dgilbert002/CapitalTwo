#!/usr/bin/env python3
"""Structural-edge sleeves with FIXED textbook parameters (nothing tuned), as
daily mark-to-market return series at 1x notional, on Capital.com hourly
bid/ask data 2021-26.

Timing: signals use prices known at 15:00 ET (close of the 14:00 hourly
candle); positions change at ~16:00 (close of the 15:00 candle). The overnight
sleeve exits at 09:00 ET next day (open of the 09:00 candle).
Costs: half the actual bid/ask spread on every unit of position change, plus
Capital.com's own overnight funding (long/short rates; weekends 3 nights).

Sleeves
  overnight  long US100 / US500 from the close to 09:00 next day, every day
  rsi2       Connors RSI(2): long when RSI2 < 10 and price > 200-day SMA,
             exit when price > 5-day SMA (indices + large stocks)
  trend      multi-horizon time-series momentum: position = mean(sign of
             21/63/252-day returns), per market, long/short where allowed
  soxl_dip   the live bot's SOXL dip rule (hourly proxy) with its protections
  reversal   buy the worst 1-day loser among large stocks, hold one day
"""
import json
import os
import sqlite3

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
META = json.load(open(os.path.join(ROOT, 'Results', 'capital_market_meta.json')))
TRADEABLE = ['SOXL', 'TQQQ', 'TNA', 'UPRO', 'NVDA', 'TSLA', 'MSTR', 'COIN', 'SMCI', 'PLTR', 'AMD', 'META',
             'US100', 'US500', 'DE40', 'GOLD', 'BTCUSD', 'ETHUSD', 'SOLUSD']
LONG_ONLY = {'SOXL', 'TQQQ', 'TNA', 'UPRO'}
STOCKS = ['NVDA', 'TSLA', 'MSTR', 'COIN', 'SMCI', 'PLTR', 'AMD', 'META']
START = pd.Timestamp('2021-03-01')


def load(epic):
    h = pd.read_sql_query(f'SELECT * FROM {epic}_cap_1h ORDER BY timestamp',
                          sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
    h['t'] = pd.to_datetime(h['timestamp'])
    h = h[h['t'].dt.weekday < 5]
    h['date'] = h['t'].dt.normalize()
    h['hr'] = h['t'].dt.hour
    mid = lambda k: (h[f'bid_{k}'] + h[f'ask_{k}']) / 2
    h['mid_close'], h['mid_open'] = mid('close'), mid('open')
    h['spr'] = (h['ask_close'] - h['bid_close']) / h['mid_close']
    g = lambda hr, col: h[h['hr'] == hr].set_index('date')[col]
    d = pd.DataFrame({'sig': g(14, 'mid_close'), 'px': g(15, 'mid_close'), 'spr': g(15, 'spr'),
                      'open9': g(9, 'mid_open'), 'spr9': h[h['hr'] == 9].set_index('date')['spr']})
    d = d.dropna(subset=['sig', 'px'])
    d = d[d.index >= START - pd.Timedelta(days=420)]
    ov = META[epic]['overnight']
    d['f_long'] = -ov['longRate'] / 100          # cost per night (positive = pay)
    d['f_short'] = -ov['shortRate'] / 100
    return d


def mtm(d, pos):
    """Daily returns of holding `pos` (set at each day's ~16:00) until next day's ~16:00."""
    pos = pos.fillna(0.0)
    ret = d['px'].pct_change().shift(-1).fillna(0.0)        # 16:00 -> next 16:00
    nights = pd.Series(d.index, index=d.index).diff().shift(-1).dt.days.fillna(1)
    fund = np.where(pos > 0, pos * d['f_long'], -pos * d['f_short']) * nights
    cost = pos.diff().abs().fillna(pos.abs()) * d['spr'] / 2
    r = pos * ret - fund - cost
    return r.shift(1).fillna(0.0)   # book the P&L on the day it is realised


def rsi(c, n):
    dl = c.diff()
    return 100 - 100 / (1 + dl.clip(lower=0).rolling(n).mean() / (-dl.clip(upper=0)).rolling(n).mean())


def sleeve_overnight(D):
    out = {}
    for e in ('US100', 'US500'):
        d = D[e]
        nxt_open = d['open9'].shift(-1)
        nights = pd.Series(d.index, index=d.index).diff().shift(-1).dt.days.fillna(1)
        r = nxt_open / d['px'] - 1 - (d['spr'] + d['spr9'].shift(-1)) / 2 - d['f_long'] * nights
        out[f'overnight_{e}'] = r.shift(1).fillna(0.0)
    return out


def sleeve_rsi2(D):
    out = {}
    for e in ('US100', 'US500', 'DE40', 'NVDA', 'AMD', 'META', 'TSLA'):
        d = D[e]
        c = d['sig']
        ent = (rsi(c, 2) < 10) & (c > c.rolling(200).mean())
        ex = c > c.rolling(5).mean()
        pos, p = [], 0.0
        for a, b in zip(ent.to_numpy(), ex.to_numpy()):
            p = 1.0 if a else (0.0 if b else p)
            pos.append(p)
        out[f'rsi2_{e}'] = mtm(d, pd.Series(pos, index=d.index))
    return out


def sleeve_trend(D):
    out = {}
    for e in TRADEABLE:
        d = D[e]
        c = d['sig']
        s = sum(np.sign(c / c.shift(n) - 1) for n in (21, 63, 252)) / 3
        if e in LONG_ONLY:
            s = s.clip(lower=0)
        out[f'trend_{e}'] = mtm(d, s)
    return out


def sleeve_soxl_dip(D):
    """Daily proxy of the live SOXL rule: 1-day drop through the hourly proxy of
    the rule, protections applied at portfolio level. Uses the hourly proxy
    signal from protect_sweep (ROC12 < -2% and fast MACD hist < -0.1%)."""
    h = pd.read_sql_query('SELECT * FROM SOXL_cap_1h ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
    h['t'] = pd.to_datetime(h['timestamp'])
    h = h[(h.t.dt.weekday < 5) & (h.t.dt.hour >= 4) & (h.t.dt.hour < 20)].reset_index(drop=True)
    c = (h.bid_close + h.ask_close) / 2
    m = c.ewm(span=3, adjust=False).mean() - c.ewm(span=6, adjust=False).mean()
    sig = ((c / c.shift(12) - 1) * 100 < -2) & ((m - m.ewm(span=2, adjust=False).mean()) / c < -0.001)
    s14 = pd.Series(sig.to_numpy(), index=h['t']).loc[lambda x: x.index.hour == 14]
    s14.index = s14.index.normalize()
    d = D['SOXL']
    buy = s14.reindex(d.index).fillna(False).astype(float)
    below = (d['sig'] < d['sig'].rolling(200).mean()).astype(float)
    return {'soxl_dip': mtm(d, buy * (1 - 0.5 * below))}


def sleeve_reversal(D):
    closes = pd.DataFrame({e: D[e]['sig'] for e in STOCKS})
    r1 = closes.pct_change()
    worst = r1.idxmin(axis=1)
    rets = []
    for e in STOCKS:
        pos = (worst == e).astype(float)
        rets.append(mtm(D[e], pos.reindex(D[e].index).fillna(0.0)))
    return {'reversal_stocks': pd.concat(rets, axis=1).fillna(0.0).sum(axis=1)}


def all_sleeves():
    D = {e: load(e) for e in TRADEABLE}
    S = {}
    for f in (sleeve_overnight, sleeve_rsi2, sleeve_trend, sleeve_soxl_dip, sleeve_reversal):
        S.update(f(D))
    R = pd.DataFrame(S).fillna(0.0)
    return R[R.index >= START], D


def summary(R):
    rows = []
    for k in R:
        r = R[k]
        eq = (1 + r).cumprod()
        yrs = (r.index[-1] - r.index[0]).days / 365.25
        vol = r.std() * np.sqrt(252)
        rows.append({'sleeve': k, 'cagr_1x': eq.iloc[-1] ** (1 / yrs) - 1, 'vol': vol,
                     'sharpe': r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0,
                     'maxdd': (eq / eq.cummax() - 1).min(),
                     **{str(y): (1 + r[r.index.year == y]).prod() - 1 for y in range(2021, 2027)}})
    return pd.DataFrame(rows).sort_values('sharpe', ascending=False)


if __name__ == '__main__':
    R, _ = all_sleeves()
    R.to_pickle('/tmp/claude-0/sleeves.pkl')
    s = summary(R)
    pd.set_option('display.width', 250)
    fm = {c: '{:+.0%}'.format for c in ['cagr_1x', 'maxdd'] + [str(y) for y in range(2021, 2027)]}
    fm.update({'vol': '{:.0%}'.format, 'sharpe': '{:.2f}'.format})
    print(s.to_string(index=False, formatters=fm))
