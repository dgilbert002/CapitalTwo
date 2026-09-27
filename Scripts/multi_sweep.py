#!/usr/bin/env python3
"""Multi-symbol, multi-method honest sweep on Capital.com hourly bid/ask data.

Daily decision at 15:00 ET using prices known then (close of the 14:00 hourly
candle); orders fill at the 15:00 candle's close (~16:00) at ASK (buy) / BID
(sell) - a deliberate one-hour delay so nothing can peek ahead. Stops and
trailing stops trigger on hourly BID lows (longs) / ASK highs (shorts); gaps
fill at the candle open. Funding per night from Capital.com's own rates.
Leverage capped by each market's margin (shares 5x, indices 20x, crypto 2x).

Methods (long, and short mirrors where sensible):
  dip      N-day drop of more than k x recent volatility -> hold H days
  rsi2     RSI(2) < th, optionally only above the 100/200-day average -> exit RSI(2) > 70 or after D days
  brk      close above the N-day high -> exit below the M-day low
  ma       close above SMA(n) -> exit below it
  xma      SMA(fast) above SMA(slow) -> exit when it crosses back
  mom      N-day return > th -> exit when it turns negative
Each also with an optional trailing stop. Scored on 2021-02..2023-12 (includes
the 2022 crash) and 2024-01..2026-09 separately.
"""
import itertools
import json
import os
import sqlite3
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPLIT = pd.Timestamp('2024-01-01')
START_EQ = 1.0
META = json.load(open(os.path.join(ROOT, 'Results', 'capital_market_meta.json')))


# ---------------------------------------------------------------- data
def daily(epic):
    h = pd.read_sql_query(f'SELECT * FROM {epic}_cap_1h ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
    h['t'] = pd.to_datetime(h['timestamp'])
    h = h[h['t'].dt.weekday < 5].reset_index(drop=True)
    ex = np.nonzero((h['t'].dt.hour == 15).to_numpy())[0]
    ex = ex[ex > 0]
    sig_ix = ex - 1
    ok = (h['t'].iloc[sig_ix].dt.hour.to_numpy() == 14)
    ex, sig_ix = ex[ok], sig_ix[ok]
    d = pd.DataFrame({
        'date': h['t'].iloc[ex].dt.normalize().to_numpy(),
        'sig': ((h['bid_close'] + h['ask_close']) / 2).iloc[sig_ix].to_numpy(),
        'ask': h['ask_close'].iloc[ex].to_numpy(), 'bid': h['bid_close'].iloc[ex].to_numpy(),
        'ex': ex})
    d = d[d['date'] >= pd.Timestamp('2021-02-22')].reset_index(drop=True)
    arrays = {k: h[k].to_numpy() for k in ('bid_open', 'bid_low', 'ask_open', 'ask_high', 'bid_high', 'ask_low')}
    return d, arrays


def rsi(c, n):
    dl = c.diff()
    return 100 - 100 / (1 + dl.clip(lower=0).rolling(n).mean() / (-dl.clip(upper=0)).rolling(n).mean())


# ---------------------------------------------------------------- rules -> entry/exit boolean arrays
def rules(d):
    c = d['sig']
    r1 = c.pct_change()
    vol = r1.rolling(20).std()
    out = {}
    for n, k, hold in itertools.product([1, 2, 3], [1.0, 1.5, 2.0, 2.5], [1, 2, 5]):
        chg = c.pct_change(n)
        out[f'dip|{n}d<-{k}sd hold{hold}'] = (chg < -k * vol * np.sqrt(n), None, hold, 1)
    for th, trend, days in itertools.product([5, 10, 20], [0, 100, 200], [3, 7]):
        r2 = rsi(c, 2)
        ent = r2 < th
        if trend:
            ent &= c > c.rolling(trend).mean()
        out[f'rsi2|<{th} trend{trend} max{days}'] = (ent, r2 > 70, days, 1)
    for n, m in itertools.product([10, 20, 55, 100], [5, 10, 20]):
        if m >= n:
            continue
        hi, lo = c.rolling(n).max().shift(), c.rolling(m).min().shift()
        out[f'brk|{n}/{m}'] = (c > hi, c < lo, 9999, 1)
        out[f'brkS|{n}/{m}'] = (c < c.rolling(n).min().shift(), c > c.rolling(m).max().shift(), 9999, -1)
    for n in [10, 20, 50, 100, 200]:
        s = c.rolling(n).mean()
        out[f'ma|{n}'] = (c > s, c < s, 9999, 1)
        out[f'maS|{n}'] = (c < s, c > s, 9999, -1)
    for f, s_ in [(5, 20), (10, 50), (20, 100), (50, 200)]:
        a, b = c.rolling(f).mean(), c.rolling(s_).mean()
        out[f'xma|{f}/{s_}'] = (a > b, a < b, 9999, 1)
        out[f'xmaS|{f}/{s_}'] = (a < b, a > b, 9999, -1)
    for n, th in itertools.product([5, 10, 20, 60], [0.0, 0.05, 0.10, 0.20]):
        m_ = c.pct_change(n)
        out[f'mom|{n}d>{th:.0%}'] = (m_ > th, m_ < 0, 9999, 1)
        out[f'momS|{n}d<-{th:.0%}'] = (m_ < -th, m_ > 0, 9999, -1)
    return {k: (np.nan_to_num(e.to_numpy(dtype=float)) > 0,
                None if x is None else np.nan_to_num(x.to_numpy(dtype=float)) > 0, hold, side)
            for k, (e, x, hold, side) in out.items()}


# ---------------------------------------------------------------- trades
def trades(d, A, ent, exi, hold, side, trail):
    """Unlevered trades: list of (entry_day, exit_day, ret, worst_excursion)."""
    out = []
    ex, ask, bid = d['ex'].to_numpy(), d['ask'].to_numpy(), d['bid'].to_numpy()
    bo, bl, ao, ah = A['bid_open'], A['bid_low'], A['ask_open'], A['ask_high']
    n = len(d)
    i = 0
    while i < n - 1:
        if not ent[i]:
            i += 1
            continue
        e_px = ask[i] if side == 1 else bid[i]
        best = e_px
        j = i + 1
        exit_px, worst = None, 0.0
        while j < n:
            a, b = ex[j - 1] + 1, ex[j] + 1           # hourly bars held between decisions
            if side == 1:
                lows = bl[a:b]
                for k_, lo in enumerate(lows):
                    worst = min(worst, lo / e_px - 1)
                    if trail and lo <= best * (1 - trail):
                        exit_px = min(best * (1 - trail), bo[a + k_])
                        break
                    best = max(best, A['bid_high'][a + k_])
            else:
                highs = ah[a:b]
                for k_, hi in enumerate(highs):
                    worst = min(worst, e_px / hi - 1)
                    if trail and hi >= best * (1 + trail):
                        exit_px = max(best * (1 + trail), ao[a + k_])
                        break
                    best = min(best, A['ask_low'][a + k_])
            if exit_px is not None:
                break
            held = j - i
            if held >= hold or (exi is not None and exi[j]) or j == n - 1:
                exit_px = bid[j] if side == 1 else ask[j]
                break
            j += 1
        ret = (exit_px / e_px - 1) if side == 1 else (e_px / exit_px - 1)
        out.append((i, j, ret, worst))
        i = j if (exi is not None or hold < 9999) else j   # can re-enter next day
        if i == j and not ent[j]:
            i = j + 1
    return out


def equity(tr, d, lev, fund, brake, lo=None, hi=None):
    dates = d['date'].to_numpy()
    eq, peak, mdd, cool_until, n = 1.0, 1.0, 0.0, -1, 0
    for i, j, ret, worst in tr:
        if lo is not None and dates[i] < lo or hi is not None and dates[i] >= hi:
            continue
        if i <= cool_until:
            continue
        nights = (dates[j] - dates[i]).astype('timedelta64[D]').astype(int)
        if lev * worst <= -0.8:                      # margin close-out before the planned exit
            g = max(1 + lev * worst, 0.0)
        else:
            g = max(1 + lev * (ret - fund * nights), 0.0)
        eq *= g
        n += 1
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        if brake and eq / peak - 1 < -brake:
            cool_until, peak = j + 20, eq
        if eq <= 0:
            break
    return eq, mdd, n


def run_symbol(epic):
    d, A = daily(epic)
    mt = META[epic]
    maxlev = min(100 / float(mt['margin_pct']), 20)
    levs = [l for l in (1, 2, 3, 5, 10, 20) if l <= maxlev]
    fl = abs(mt['overnight']['longRate']) / 100
    fs = max(-mt['overnight']['shortRate'], 0) / 100
    yrs_tr = (SPLIT - d['date'].iloc[0]).days / 365.25
    yrs_te = (d['date'].iloc[-1] - SPLIT).days / 365.25
    bh_tr = d['sig'][d['date'] < SPLIT].iloc[-1] / d['sig'].iloc[0]
    bh_te = d['sig'].iloc[-1] / d['sig'][d['date'] >= SPLIT].iloc[0]
    rows = []
    for name, (ent, exi, hold, side) in rules(d).items():
        for trail in (None, 0.08, 0.15, 0.25):
            if hold < 9999 and trail:
                continue
            tr = trades(d, A, ent, exi, hold, side, trail)
            if len(tr) < 8:
                continue
            fund = fl if side == 1 else fs
            for lev, brake in itertools.product(levs, (None, 0.2, 0.3)):
                a = equity(tr, d, lev, fund, brake, hi=SPLIT)
                b = equity(tr, d, lev, fund, brake, lo=SPLIT)
                al = equity(tr, d, lev, fund, brake)
                rows.append((epic, name, trail or 0, lev, brake or 0, len(tr), a[0], a[1], b[0], b[1], al[0], al[1]))
    df = pd.DataFrame(rows, columns=['epic', 'rule', 'trail', 'lev', 'brake', 'trades', 'tr_x', 'tr_dd', 'te_x', 'te_dd', 'all_x', 'all_dd'])
    df['tr_cagr'] = df['tr_x'] ** (1 / yrs_tr) - 1
    df['te_cagr'] = df['te_x'] ** (1 / yrs_te) - 1
    df['bh_tr'], df['bh_te'] = bh_tr, bh_te
    print(f'{epic:7s} {len(df):6,} settings  buy&hold 2021-23 {bh_tr-1:+.0%}  2024-26 {bh_te-1:+.0%}', flush=True)
    return df


def main():
    epics = sys.argv[1:] or list(META)
    with Pool(os.cpu_count()) as p:
        dfs = p.map(run_symbol, epics)
    df = pd.concat(dfs, ignore_index=True)
    df.to_pickle('/tmp/claude-0/multi.pkl')
    print(f'\nTotal {len(df):,} settings across {len(epics)} markets')


if __name__ == '__main__':
    main()
