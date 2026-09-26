#!/usr/bin/env python3
"""Honest overnight-hold backtest + parameter sweep for SOXL.

Mirrors the live bot: at ~15:59:45 ET check a signal on the 5-min series, buy
at that price, hold overnight, sell ~15:59:30 ET next trading day, with an
intraday stop-loss. Differences from the repo's older backtests:
  * no look-ahead: signals and entry use the 15:55 bar, never post-close bars
  * stop checked only while the position is open; gap-downs fill at the open
  * real Capital.com costs: ~0.215% round-trip spread, 0.0222%/night funding
    (weekends count 3 nights), leverage capped at 5x (20% margin)
  * equity can go to zero (no negative balances carried forward)

Parameters are chosen on TRAIN (the original Alpha Vantage period) and then
reported on TEST (the new Capital.com candles), so results aren't curve-fit.
"""
import itertools
import sqlite3
import sys

import numpy as np
import pandas as pd

TABLE = sys.argv[1] if len(sys.argv) > 1 else 'SOXL_merged_5min'
SPLIT = pd.Timestamp('2025-10-22')
SPREAD_RT = 0.00215
FUNDING_NIGHT = 0.000222
START = 500.0
INVEST = 0.99
DECISION = pd.Timestamp('15:55').time()


def load():
    df = pd.read_sql_query(f'SELECT * FROM {TABLE}', sqlite3.connect('database_av.db'))
    df['t'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('t').reset_index(drop=True)
    df['date'] = df['t'].dt.date
    return df


# ---- indicators (same formulas as Brains/strategy_signals.py) ----
def rsi(c, n):
    d = c.diff()
    g = d.clip(lower=0).rolling(n).mean()
    l = (-d.clip(upper=0)).rolling(n).mean()
    return 100 - 100 / (1 + g / l)


def macd_hist(c, f, s, sig):
    m = c.ewm(span=f, adjust=False).mean() - c.ewm(span=s, adjust=False).mean()
    return m - m.ewm(span=sig, adjust=False).mean()


def keltner_lower(df, n, k):
    c, h, l = df['close'], df['high'], df['low']
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return c.ewm(span=n, adjust=False).mean() - k * tr.rolling(n).mean()


def signal_grid(df):
    c = df['close']
    out = {'always_long': pd.Series(True, index=df.index)}
    for n, th in itertools.product([2, 3, 5, 7, 14], [10, 15, 20, 25, 30, 35]):
        out[f'rsi_oversold p={n} th={th}'] = rsi(c, n) < th
    for n in [5, 7, 14]:
        r = rsi(c, n)
        out[f'rsi_cross50 p={n}'] = (r > 50) & (r.shift() <= 50)
    for n, k in itertools.product([10, 20, 40], [1.5, 2.0, 2.5, 3.0]):
        sma, sd = c.rolling(n).mean(), c.rolling(n).std()
        out[f'bb_lower p={n} sd={k}'] = c < sma - k * sd
    for n, th in itertools.product([10, 20, 40, 78], [-1, -2, -3, -5, -8]):
        out[f'roc_below p={n} th={th}%'] = (c / c.shift(n) - 1) * 100 < th
    for n, k in itertools.product([10, 20], [1.5, 2.0, 3.0]):
        out[f'keltner_lower p={n} k={k}'] = c < keltner_lower(df, n, k)
    for (f, s, sg), th in itertools.product([(5, 18, 4), (8, 18, 4), (12, 26, 9)], [0.0, -0.001, -0.002]):
        # threshold as fraction of price so it scales from $20 to $270 SOXL
        out[f'macd_hist_neg {f}/{s}/{sg} th={th*100:.1f}%'] = macd_hist(c, f, s, sg) < th * c
    for (f, s, sg) in [(12, 26, 9), (13, 30, 9)]:
        out[f'macd_hist_pos {f}/{s}/{sg}'] = macd_hist(c, f, s, sg) > 0
    return out


def build_days(df):
    """Per trading day: decision bar index, entry price, and the bars covering
    the hold window to the next day's decision bar."""
    reg = df[df['t'].dt.time <= DECISION]
    dec = reg.groupby('date').tail(1)
    dec = dec[dec['t'].dt.weekday < 5]
    idx = dec.index.to_numpy()
    days = []
    for i in range(len(idx) - 1):
        a, b = idx[i], idx[i + 1]
        w = df.iloc[a + 1:b + 1]
        nights = (dec['t'].iloc[i + 1].normalize() - dec['t'].iloc[i].normalize()).days
        days.append((a, dec['t'].iloc[i], df['close'].iat[a], w['open'].to_numpy(), w['low'].to_numpy(),
                     df['close'].iat[b], nights))
    return days


def simulate(days, fired, lev, sl, lo=None, hi=None):
    bal, peak, mdd, trades, wins = START, START, 0.0, 0, 0
    for a, t, entry, opens, lows, exitp, nights in days:
        if (lo is not None and t < lo) or (hi is not None and t >= hi):
            continue
        if not fired[a] or bal <= 0:
            continue
        px = exitp
        if sl is not None:
            stop = entry * (1 - sl / 100)
            hit = np.nonzero(lows <= stop)[0]
            if hit.size:
                px = min(stop, opens[hit[0]])
        notional = bal * INVEST * lev
        pnl = notional * (px / entry - 1) - notional * (SPREAD_RT + FUNDING_NIGHT * nights)
        bal = max(bal + pnl, 0.0)
        trades += 1
        wins += pnl > 0
        peak = max(peak, bal)
        mdd = min(mdd, bal / peak - 1)
    return bal, trades, wins, mdd


def main():
    df = load()
    days = build_days(df)
    sigs = signal_grid(df)
    first, last = days[0][1], days[-1][1]
    yrs_tr = (SPLIT - first).days / 365.25
    yrs_te = (last - SPLIT).days / 365.25

    bh = [d for d in days]
    p0, p_split = bh[0][2], next(d[2] for d in bh if d[1] >= SPLIT)
    print(f'Data {first.date()} -> {last.date()}  |  {len(days)} trading days  |  split {SPLIT.date()}')
    print(f'SOXL buy&hold (no leverage, no costs): train {p_split/p0-1:+.0%}, test {bh[-1][5]/p_split-1:+.0%}\n')

    rows = []
    for name, s in sigs.items():
        fired = s.fillna(False).to_numpy()
        for lev, sl in itertools.product([1, 2, 3, 4, 5], [2, 3, 4, 5, 6, 8, 10, 15, None]):
            tr = simulate(days, fired, lev, sl, hi=SPLIT)
            te = simulate(days, fired, lev, sl, lo=SPLIT)
            rows.append({'signal': name, 'lev': lev, 'sl': sl if sl else '-',
                         'train_final': tr[0], 'train_trades': tr[1], 'train_win%': 100 * tr[2] / max(tr[1], 1),
                         'train_mdd%': 100 * tr[3],
                         'test_final': te[0], 'test_trades': te[1], 'test_win%': 100 * te[2] / max(te[1], 1),
                         'test_mdd%': 100 * te[3]})
    r = pd.DataFrame(rows)
    r['train_cagr%'] = 100 * ((r['train_final'] / START) ** (1 / yrs_tr) - 1)
    r['test_cagr%'] = 100 * ((r['test_final'] / START) ** (1 / yrs_te) - 1)
    r.to_csv('Results/soxl_sweep.tsv', sep='\t', index=False, float_format='%.2f')

    cols = ['signal', 'lev', 'sl', 'train_final', 'train_trades', 'train_win%', 'train_mdd%',
            'test_final', 'test_trades', 'test_win%', 'test_mdd%']
    pd.set_option('display.width', 250)
    pd.set_option('display.max_colwidth', 40)
    fmt = lambda x: f'{x:,.0f}'
    elig = r[(r['train_trades'] >= 30) & (r['test_trades'] >= 15)]
    print(f'{len(r):,} settings tested. Top 15 picked on TRAIN only (>=30 train trades), with their unseen TEST result:')
    print(elig.sort_values('train_final', ascending=False).head(15)[cols].to_string(index=False, float_format=fmt))
    print('\nRobust picks: profitable in BOTH periods, train max drawdown better than -50%, ranked by worse-period CAGR:')
    rob = elig[(elig['train_final'] > START) & (elig['test_final'] > START) & (elig['train_mdd%'] > -50)].copy()
    rob['min_cagr%'] = rob[['train_cagr%', 'test_cagr%']].min(axis=1)
    print(rob.sort_values('min_cagr%', ascending=False).head(15)[cols + ['min_cagr%']].to_string(index=False, float_format=fmt))
    print(f"\nShare of settings profitable on test: {(r['test_final'] > START).mean():.0%}")

    live = r[(r['signal'] == 'rsi_oversold p=14 th=25') & (r['lev'] == 5) & (r['sl'] == 5)]
    print('\nClosest to the live bot today (test8 top pick rsi_oversold p14<25, capped at 5x, SL 5% ~ 4.5%):')
    print(live[cols].to_string(index=False, float_format=fmt))


if __name__ == '__main__':
    main()
