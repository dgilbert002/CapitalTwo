#!/usr/bin/env python3
"""Wider honest SOXL search: signals x trend filters x direction x exit time
x leverage x stop-loss. Same no-look-ahead rules and real Capital.com costs as
soxl_sweep.py; vectorised so ~100k settings run in minutes.

Decision/entry: 15:55 ET bar (what the live bot sees at 15:59:45).
Exit: next trading day at one of EXIT_TIMES (first bar at/after that time).
Stops are checked only while the position is open; gaps fill at the bar open.
"""
import itertools
import sqlite3
import sys

import numpy as np
import pandas as pd

TABLE = sys.argv[1] if len(sys.argv) > 1 else 'SOXL_merged_5min'
SPLIT = pd.Timestamp('2025-10-22')
SPREAD_RT = 0.00215          # measured on Capital.com near the close
FUND_LONG = 0.000222         # per night, charged
FUND_SHORT = 0.0000153       # per night, charged
START, INVEST = 500.0, 0.99
DECISION = pd.Timestamp('15:55').time()
EXIT_TIMES = ['09:30', '10:30', '12:00', '15:55']
LEVS = [1, 2, 3, 4, 5]
SLS = [2, 3, 4, 5, 6, 8, 10, 15, None]


def rsi(c, n):
    d = c.diff()
    return 100 - 100 / (1 + d.clip(lower=0).rolling(n).mean() / (-d.clip(upper=0)).rolling(n).mean())


def macd_hist(c, f, s, g):
    m = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    return m - m.ewm(span=g, adjust=False).mean()


def load():
    df = pd.read_sql_query(f'SELECT * FROM {TABLE}', sqlite3.connect('database_av.db'))
    df['t'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('t').reset_index(drop=True)
    df['date'] = df['t'].dt.date
    return df


def decision_bars(df):
    dec = df[df['t'].dt.time <= DECISION].groupby('date').tail(1)
    return dec[dec['t'].dt.weekday < 5]


def bar_signals(df):
    """Intraday-bar signals evaluated at the decision bar. name -> (bool array, direction)."""
    c, h, l = df['close'], df['high'], df['low']
    out = {'always': (np.ones(len(df), bool), 0)}  # direction 0 = both variants
    for n, th in itertools.product([2, 3, 5, 7, 14], [10, 15, 20, 25, 30, 35]):
        r = rsi(c, n)
        out[f'rsi{n}<{th}'] = (r < th, 1)
        out[f'rsi{n}>{100-th}'] = (r > 100 - th, -1)
    for n, k in itertools.product([10, 20, 40, 78], [1.0, 1.5, 2.0, 2.5, 3.0]):
        m, s = c.rolling(n).mean(), c.rolling(n).std()
        out[f'bb{n}<-{k}sd'] = (c < m - k * s, 1)
        out[f'bb{n}>+{k}sd'] = (c > m + k * s, -1)
    for n, th in itertools.product([6, 10, 20, 40, 78, 156], [1, 2, 3, 5, 8]):
        roc = (c / c.shift(n) - 1) * 100
        out[f'roc{n}<-{th}%'] = (roc < -th, 1)
        out[f'roc{n}>+{th}%'] = (roc > th, -1)
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    for n, k in itertools.product([10, 20, 40], [1.0, 1.5, 2.0, 3.0]):
        e, a = c.ewm(span=n, adjust=False).mean(), tr.rolling(n).mean()
        out[f'kelt{n}<-{k}'] = (c < e - k * a, 1)
        out[f'kelt{n}>+{k}'] = (c > e + k * a, -1)
    for (f, s, g), th in itertools.product([(5, 18, 4), (8, 18, 4), (12, 26, 9)], [0.0, 0.001, 0.002]):
        mh = macd_hist(c, f, s, g)
        out[f'macd{f}/{s}/{g}<-{th*100:.1f}%'] = (mh < -th * c, 1)
        out[f'macd{f}/{s}/{g}>+{th*100:.1f}%'] = (mh > th * c, -1)
    return {k: (np.nan_to_num(np.asarray(v, dtype=float)) > 0, d) for k, (v, d) in out.items()}


def day_filters(dec):
    """Daily regime filters from decision-bar closes (known at decision time)."""
    dc = dec['close'].reset_index(drop=True)
    f = {'none': np.ones(len(dc), bool)}
    for n in [10, 20, 50, 100]:
        sma = dc.rolling(n).mean()
        f[f'>sma{n}d'] = (dc > sma).to_numpy()
        f[f'<sma{n}d'] = (dc < sma).to_numpy()
    for n in [1, 3, 5]:
        ch = dc.pct_change(n)
        f[f'down{n}d'] = (ch < 0).to_numpy()
        f[f'up{n}d'] = (ch > 0).to_numpy()
    return f


def day_returns(df, dec, exit_time, sl, direction):
    """Per-day price return of a trade entered at the decision bar, exit next day."""
    idx = dec.index.to_numpy()
    et = pd.Timestamp(exit_time).time()
    t, o, lo, hi, cl = df['t'].to_numpy(), df['open'].to_numpy(), df['low'].to_numpy(), df['high'].to_numpy(), df['close'].to_numpy()
    times = df['t'].dt.time.to_numpy()
    rets, nights = np.full(len(idx), np.nan), np.zeros(len(idx))
    for i in range(len(idx) - 1):
        a, b = idx[i], idx[i + 1]
        nd = df['date'].iat[b]
        # first bar on the next trading day at/after exit time (<= that day's decision bar)
        j0 = np.searchsorted(t, np.datetime64(pd.Timestamp.combine(nd, et)))
        e = min(max(j0, a + 1), b)
        entry = cl[a]
        px = cl[e] if exit_time == '15:55' else o[e]
        last = e if exit_time == '15:55' else e - 1   # bars fully held
        if sl is not None and last > a:
            if direction == 1:
                stop = entry * (1 - sl / 100)
                hit = np.nonzero(lo[a + 1:last + 1] <= stop)[0]
                if hit.size:
                    px = min(stop, o[a + 1 + hit[0]])
            else:
                stop = entry * (1 + sl / 100)
                hit = np.nonzero(hi[a + 1:last + 1] >= stop)[0]
                if hit.size:
                    px = max(stop, o[a + 1 + hit[0]])
        rets[i] = direction * (px / entry - 1)
        nights[i] = (pd.Timestamp(nd) - pd.Timestamp(df['date'].iat[a])).days
    return rets, nights


def equity(mask, r, nights, lev, direction):
    fund = FUND_LONG if direction == 1 else FUND_SHORT
    g = np.where(mask, 1 + INVEST * lev * (r - SPREAD_RT - fund * nights), 1.0)
    g = np.maximum(np.nan_to_num(g, nan=1.0), 0.0)
    eq = START * np.cumprod(g)
    dd = (eq / np.maximum.accumulate(np.maximum(eq, START)) - 1).min()
    return eq[-1] if len(eq) else START, dd


def main():
    df = load()
    dec = decision_bars(df)
    dates = dec['t'].reset_index(drop=True)
    tr_m = (dates < SPLIT).to_numpy()
    te_m = ~tr_m
    yrs_tr = (SPLIT - dates.iloc[0]).days / 365.25
    yrs_te = (dates.iloc[-1] - SPLIT).days / 365.25
    yrs_all = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    bars = bar_signals(df)
    filters = day_filters(dec)
    idx = dec.index.to_numpy()
    print(f'{len(bars)} signals x {len(filters)} filters x {len(EXIT_TIMES)} exits x {len(LEVS)} lev x {len(SLS)} SL')

    cache = {}
    for ex, sl, d in itertools.product(EXIT_TIMES, SLS, [1, -1]):
        cache[(ex, sl, d)] = day_returns(df, dec, ex, sl, d)
    print('returns cached')

    rows = []
    for (sname, (sig, sdir)), (fname, filt) in itertools.product(bars.items(), filters.items()):
        base = sig[idx] & filt
        for d in ([1, -1] if sdir == 0 else [sdir]):
            ntr, nte = int((base & tr_m).sum()), int((base & te_m).sum())
            if ntr < 25 or nte < 12:
                continue
            for ex, sl in itertools.product(EXIT_TIMES, SLS):
                r, nights = cache[(ex, sl, d)]
                for lev in LEVS:
                    ftr, ddtr = equity(base & tr_m, r, nights, lev, d)
                    fte, ddte = equity(base & te_m, r, nights, lev, d)
                    fall, ddall = equity(base, r, nights, lev, d)
                    rows.append((sname, fname, 'long' if d == 1 else 'short', ex, lev, sl or 0,
                                 ntr, ftr, ddtr, nte, fte, ddte, fall, ddall))
    r = pd.DataFrame(rows, columns=['signal', 'filter', 'side', 'exit', 'lev', 'sl', 'train_n', 'train_final',
                                    'train_dd', 'test_n', 'test_final', 'test_dd', 'all_final', 'all_dd'])
    for p, y in [('train', yrs_tr), ('test', yrs_te), ('all', yrs_all)]:
        r[f'{p}_cagr'] = 100 * ((r[f'{p}_final'] / START) ** (1 / y) - 1)
    r['min_cagr'] = r[['train_cagr', 'test_cagr']].min(axis=1)
    r.sort_values('min_cagr', ascending=False).head(5000).to_csv(
        'Results/soxl_sweep2_top5000.tsv', sep='\t', index=False, float_format='%.3f')

    pd.set_option('display.width', 260)
    cols = ['signal', 'filter', 'side', 'exit', 'lev', 'sl', 'train_n', 'train_final', 'train_dd',
            'test_n', 'test_final', 'test_dd', 'all_final', 'all_dd']
    fmt = {c: '{:,.0f}'.format for c in ['train_final', 'test_final', 'all_final']}
    fmt.update({c: '{:.0%}'.format for c in ['train_dd', 'test_dd', 'all_dd']})
    show = lambda x: print(x[cols].to_string(index=False, formatters=fmt))
    print(f'\n{len(r):,} settings. Period: {dates.iloc[0].date()} -> {dates.iloc[-1].date()} ({yrs_all:.1f} yrs), split {SPLIT.date()}')
    print('\nA) Highest FULL-PERIOD balance (in-sample, the "most profitable backtest"):')
    show(r.sort_values('all_final', ascending=False).head(10))
    print('\nB) Picked on TRAIN only -> result on unseen TEST:')
    show(r.sort_values('train_final', ascending=False).head(10))
    print('\nC) Best in BOTH halves (ranked by the weaker half), train DD better than -60%:')
    show(r[r['train_dd'] > -0.6].sort_values('min_cagr', ascending=False).head(15))
    r.to_pickle('/tmp/claude-0/sweep2.pkl')


if __name__ == '__main__':
    main()
