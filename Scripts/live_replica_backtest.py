#!/usr/bin/env python3
"""Backtest that replicates the live bot's close-of-day timing on 1-minute
Capital.com bid/ask data (table <EPIC>_cap_1min from capital_1m_download.py).

Live bot (bot/trader.py): T-30s close all positions; T-15s fetch 5-min candles,
run Brains/strategy_signals.get_strategy_analysis, open a position.

Replica:
  * 5-min candles are rebuilt from 1-min mid prices, with the 15:55 candle
    built only from 15:55-15:58 (what is visible at 15:59:45).
  * entry = ASK at ~15:59:45, exit = BID at ~15:59:30 next trading day
    (or BID at the 09:30 open for the open-exit variant).
  * stop-loss triggers on the 1-min BID low; gap fills at the bar's bid open.
  * funding 0.0222%/night on notional (3 nights over weekends).

Part 1 replays the bot's actual test8 brain (Results/global_top300__SOXL.tsv).
Part 2 re-runs the wide signal search on this data, split train/test.
"""
import itertools
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import soxl_sweep2 as S2  # noqa: E402  (signal/filter definitions)

EPIC = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
SPLIT = pd.Timestamp('2025-10-22')
FUND = 0.000222
START, INVEST = 500.0, 0.99


def load_1m():
    df = pd.read_sql_query(f'SELECT * FROM {EPIC}_cap_1min ORDER BY timestamp', sqlite3.connect('database_av.db'))
    df['t'] = pd.to_datetime(df['timestamp'])
    df = df[(df['t'].dt.weekday < 5) & (df['t'].dt.time >= pd.Timestamp('04:00').time())
            & (df['t'].dt.time < pd.Timestamp('20:00').time())].reset_index(drop=True)
    for k in ['open', 'high', 'low', 'close']:
        df[k] = (df[f'bid_{k}'] + df[f'ask_{k}']) / 2
    df['date'] = df['t'].dt.date
    return df


def five_min(m1):
    """5-min mid candles; the 15:55 candle excludes the 15:59 minute."""
    x = m1[m1['t'].dt.time != pd.Timestamp('15:59').time()].set_index('t')
    agg = x.resample('5min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna()
    agg = agg.reset_index()
    agg['date'] = agg['t'].dt.date
    agg['timestamp'] = agg['t'].dt.strftime('%Y-%m-%d %H:%M:%S')
    agg['closePrice'], agg['highPrice'], agg['lowPrice'] = agg['close'], agg['high'], agg['low']
    agg['lastTradedVolume'] = agg['volume']
    return agg


def trade_days(m1, m5):
    """Per trading day with a 15:59 minute: decision 5-min index, entry ask,
    and per exit mode the hold-window bid arrays + exit bid."""
    t59 = m1[m1['t'].dt.time == pd.Timestamp('15:59').time()]
    dec5 = m5[m5['t'].dt.time == pd.Timestamp('15:55').time()].set_index('date')
    days = [d for d in t59['date'] if d in dec5.index]
    t59 = t59.set_index('date')
    tarr = m1['t'].to_numpy()
    bo, bl = m1['bid_open'].to_numpy(), m1['bid_low'].to_numpy()
    out = []
    for i in range(len(days) - 1):
        d, nd = days[i], days[i + 1]
        r = t59.loc[d]
        entry = r['ask_open'] + 0.75 * (r['ask_close'] - r['ask_open'])
        a = np.searchsorted(tarr, np.datetime64(pd.Timestamp.combine(d, pd.Timestamp('16:00').time())))
        rn = t59.loc[nd]
        exits = {}
        e_close = np.searchsorted(tarr, np.datetime64(pd.Timestamp.combine(nd, pd.Timestamp('15:59').time())))
        exits['15:59'] = (a, e_close, rn['bid_open'] + 0.5 * (rn['bid_close'] - rn['bid_open']))
        e_open = np.searchsorted(tarr, np.datetime64(pd.Timestamp.combine(nd, pd.Timestamp('09:30').time())))
        exits['09:30'] = (a, e_open, bo[e_open])
        nights = (pd.Timestamp(nd) - pd.Timestamp(d)).days
        out.append((d, int(dec5.loc[d, 'index_5m']), entry, exits, nights))
    return out, bo, bl


def returns(days, bo, bl, exit_mode, sl):
    r = np.empty(len(days))
    for k, (_, _, entry, exits, _) in enumerate(days):
        a, e, px = exits[exit_mode]
        if sl:
            stop = entry * (1 - sl / 100)
            hit = np.nonzero(bl[a:e] <= stop)[0]
            if hit.size:
                px = min(stop, bo[a + hit[0]])
        r[k] = px / entry - 1
    return r


def equity(mask, r, nights, lev):
    g = np.where(mask, 1 + INVEST * lev * (r - FUND * nights), 1.0)
    eq = START * np.cumprod(np.maximum(g, 0))
    dd = (eq / np.maximum.accumulate(np.maximum(eq, START)) - 1).min()
    return eq[-1], dd, eq


def main():
    m1 = load_1m()
    m5 = five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = trade_days(m1, m5)
    dates = pd.to_datetime(pd.Series([d[0] for d in days]))
    nights = np.array([d[4] for d in days])
    dec_idx = np.array([d[1] for d in days])
    tr_m, te_m = (dates < SPLIT).to_numpy(), (dates >= SPLIT).to_numpy()
    yrs = (dates.iloc[-1] - dates.iloc[0]).days / 365.25
    spread = np.median([(d[3]['15:59'][2] / d[2]) - 1 for d in days])  # rough bid/ask drag check
    print(f'{EPIC} 1-min Capital.com data: {len(m1):,} bars, {len(days)} trading days '
          f'{dates.iloc[0].date()} -> {dates.iloc[-1].date()}; median close-to-close bid/ask drag {spread:+.3%}')

    # ---------- Part 1: the live test8 brain ----------
    from Brains import strategy_signals as SS
    cfgs = SS.TEST8_SOXL_TOP_CONFIGS
    c = m5['closePrice']
    fired = []
    for cfg in cfgs:
        p, s = cfg['params'], cfg['condition']
        if s == 'rsi_oversold':
            f = S2.rsi(c, p.get('period', 7)) < p.get('threshold', 25)
        elif s == 'keltner_lower_break':
            n, k = p.get('period', 10), p.get('multiplier', 2.0)
            tr = pd.concat([m5['high'] - m5['low'], (m5['high'] - c.shift()).abs(), (m5['low'] - c.shift()).abs()], axis=1).max(axis=1)
            f = c < c.ewm(span=n, adjust=False).mean() - k * tr.rolling(n).mean()
        elif s.startswith('macd_histogram_negative'):
            base = SS.SIGNAL_CONFIGS[s]
            f = S2.macd_hist(c, p.get('fast_period', base['fast_period']), p.get('slow_period', base['slow_period']),
                             p.get('signal_period', base['signal_period'])) < p.get('threshold', base['threshold'])
        elif s == 'bb_lower_break':
            n, k = p.get('period', 20), p.get('std_dev', 2.0)
            f = c < c.rolling(n).mean() - k * c.rolling(n).std()
        else:
            f = pd.Series(False, index=c.index)
        fired.append(np.nan_to_num(f.to_numpy(dtype=float))[dec_idx] > 0)
    fired = np.array(fired)
    # pick highest final_balance among fired configs (select_best_signal, test8)
    order = np.argsort([-cfg['final_balance'] for cfg in cfgs])
    choice = np.full(len(days), -1)
    for k in order[::-1]:
        choice[fired[k]] = k
    print(f'\nPart 1 - live test8 brain ({len(cfgs)} configs), exit at T-30s next day:')
    for cap in [None, 5]:
        g = np.ones(len(days))
        for sl_lev_key in set(choice[choice >= 0]):
            cfg = cfgs[sl_lev_key]
            lev = cfg['params']['leverage'] if cap is None else min(cap, cfg['params']['leverage'])
            r = returns(days, bo, bl, '15:59', cfg['params']['stop_loss_pct'])
            m = choice == sl_lev_key
            g[m] = np.maximum(1 + INVEST * lev * (r[m] - FUND * nights[m]), 0)
        eq = START * np.cumprod(g)
        dd = (eq / np.maximum.accumulate(np.maximum(eq, START)) - 1).min()
        lbl = 'as configured (up to 10x - not allowed on Capital.com)' if cap is None else 'leverage capped at 5x'
        print(f'  {lbl:55s}: $500 -> ${eq[-1]:,.0f}   trades {int((choice >= 0).sum())}   max DD {dd:.0%}')

    # ---------- Part 2: wide search on replica data ----------
    bars = S2.bar_signals(m5.rename(columns={}))
    dec_df = m5.iloc[dec_idx].reset_index(drop=True)
    filters = S2.day_filters(dec_df)
    cache = {(ex, sl): returns(days, bo, bl, ex, sl) for ex in ['15:59', '09:30'] for sl in [3, 5, 8, 10, 15, None]}
    rows = []
    for (sn, (sig, sdir)), (fn, filt) in itertools.product(bars.items(), filters.items()):
        if sdir == -1:
            continue
        mask = sig[dec_idx] & filt
        if (mask & tr_m).sum() < 25 or (mask & te_m).sum() < 12:
            continue
        for (ex, sl), r in cache.items():
            for lev in [1, 2, 3, 4, 5]:
                ftr, ddtr, _ = equity(mask & tr_m, r, nights, lev)
                fte, ddte, _ = equity(mask & te_m, r, nights, lev)
                fall, ddall, _ = equity(mask, r, nights, lev)
                rows.append((sn, fn, ex, lev, sl or 0, int(mask.sum()), ftr, fte, fall, ddall))
    R = pd.DataFrame(rows, columns=['signal', 'filter', 'exit', 'lev', 'sl', 'trades', 'train_final', 'test_final', 'all_final', 'all_dd'])
    R['both'] = (R.train_final > START) & (R.test_final > START)
    R.to_csv(f'Results/{EPIC.lower()}_replica_sweep.tsv', sep='\t', index=False, float_format='%.2f')
    pd.set_option('display.width', 250)
    fm = {k: '{:,.0f}'.format for k in ['train_final', 'test_final', 'all_final']}
    fm['all_dd'] = '{:.0%}'.format
    cols = ['signal', 'filter', 'exit', 'lev', 'sl', 'trades', 'train_final', 'test_final', 'all_final', 'all_dd']
    print(f'\nPart 2 - {len(R):,} long settings on replica data ({yrs:.1f} yrs). Top by full-period balance:')
    print(R.sort_values('all_final', ascending=False).head(12)[cols].to_string(index=False, formatters=fm))

    # family robustness: group by (signal type, filter, exit, lev, sl) -> share of param neighbours profitable in both halves
    R['family'] = R.signal.str.extract(r'^([a-z]+)')[0]
    fam = R.groupby(['family', 'filter', 'exit', 'lev', 'sl']).agg(n=('both', 'size'), both=('both', 'mean'),
                                                                   median_final=('all_final', 'median'),
                                                                   worst_final=('all_final', 'min')).reset_index()
    fam = fam[(fam.n >= 6) & (fam.both == 1)]
    print('\nRobust families (every parameter variant profitable in BOTH halves), by median full-period balance:')
    print(fam.sort_values('median_final', ascending=False).head(15).to_string(
        index=False, formatters={'median_final': '{:,.0f}'.format, 'worst_final': '{:,.0f}'.format, 'both': '{:.0%}'.format}))
    R.to_pickle('/tmp/claude-0/replica.pkl')


if __name__ == '__main__':
    main()
