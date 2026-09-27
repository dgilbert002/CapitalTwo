#!/usr/bin/env python3
"""Intraday strategy search on Capital.com 1-min bid/ask data (regular hours).

All trades open and close the same day (no overnight funding). Entries fill at
the ASK of the next minute's open, exits at the BID. Signals use only
completed 1-min candles.

Families
  dip   : price fell >= D% over the last L minutes -> buy; exit after H minutes,
          at +TP%, at -SL% (bid), or at 15:55
  orb   : price breaks above the first-30-minute high -> buy; exit 15:55 or -SL%
  mom   : price rose >= D% over L minutes -> buy (continuation); exit as dip
One trade at a time. Train = 2024-01..2025-12, test = 2026.
"""
import itertools
import sqlite3
import sys

import numpy as np
import pandas as pd

EPIC = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
SPLIT = pd.Timestamp('2026-01-01')


def load():
    m = pd.read_sql_query(f'SELECT * FROM {EPIC}_cap_1min ORDER BY timestamp', sqlite3.connect('database_av.db'))
    m['t'] = pd.to_datetime(m['timestamp'])
    tt = m['t'].dt.time
    m = m[(m['t'].dt.weekday < 5) & (tt >= pd.Timestamp('09:30').time()) & (tt < pd.Timestamp('16:00').time())]
    m = m.reset_index(drop=True)
    m['mid'] = (m.bid_close + m.ask_close) / 2
    m['day'] = m['t'].dt.normalize()
    return m


def run(m, entry, hold, tp, sl):
    """Vector-ish simulation: one trade at a time per day. Returns per-trade returns + day."""
    t_min = (m['t'].dt.hour * 60 + m['t'].dt.minute).to_numpy()
    ask_o, bid_o, bid_l, bid_h = m.ask_open.to_numpy(), m.bid_open.to_numpy(), m.bid_low.to_numpy(), m.bid_high.to_numpy()
    bid_c = m.bid_close.to_numpy()
    day = m['day'].to_numpy()
    n = len(m)
    out = []
    i = 0
    last_entry_min = 15 * 60 + 45
    while i < n - 2:
        if not entry[i] or t_min[i + 1] > last_entry_min or day[i + 1] != day[i]:
            i += 1
            continue
        j = i + 1
        e = ask_o[j]
        stop, target = e * (1 - sl / 100), e * (1 + tp / 100) if tp else np.inf
        k = j
        px = None
        while k < n:
            if day[k] != day[j] or t_min[k] >= 15 * 60 + 55 or (hold and k - j >= hold):
                px = bid_o[k] if day[k] == day[j] else bid_c[k - 1]
                break
            if bid_l[k] <= stop:
                px = min(stop, bid_o[k])
                break
            if bid_h[k] >= target:
                px = max(target, bid_o[k])
                break
            k += 1
        if px is None:
            break
        out.append((day[j], px / e - 1))
        i = k + 1
    return out


def main():
    m = load()
    mid = m['mid']
    same_day = lambda s, L: s.where(m['day'] == m['day'].shift(L))
    first30_high = m[m['t'].dt.time < pd.Timestamp('10:00').time()].groupby('day')['mid'].max()
    orb_level = m['day'].map(first30_high)
    rows = []
    fams = []
    for L, D in itertools.product([5, 15, 30, 60], [1, 2, 3, 5]):
        chg = same_day(mid / mid.shift(L) - 1, L) * 100
        fams.append((f'dip {L}m<-{D}%', (chg < -D).to_numpy()))
        fams.append((f'mom {L}m>+{D}%', (chg > D).to_numpy()))
    after10 = (m['t'].dt.time >= pd.Timestamp('10:00').time()).to_numpy()
    orb = ((mid > orb_level) & (mid.shift(1) <= orb_level)).to_numpy() & after10
    fams.append(('orb 30m breakout', orb))
    days = m['day'].unique()
    tr_days = (days < SPLIT).sum(); te_days = (days >= SPLIT).sum()
    for (name, ent), hold, tp, sl in itertools.product(fams, [15, 60, 0], [0, 2, 4], [2, 4]):
        if name.startswith('orb') and hold:
            continue
        tr = run(m, ent, hold, tp, sl)
        if len(tr) < 40:
            continue
        d = pd.DataFrame(tr, columns=['day', 'r'])
        a, b = d[d.day < SPLIT].r, d[d.day >= SPLIT].r
        for lev in (1, 3, 5):
            ga, gb = np.prod(np.maximum(1 + lev * a, 0)), np.prod(np.maximum(1 + lev * b, 0))
            rows.append((name, hold or 'eod', tp or '-', sl, lev, len(a), len(b), a.mean() * 100, ga, gb))
    R = pd.DataFrame(rows, columns=['rule', 'hold', 'tp%', 'sl%', 'lev', 'tr_trades', 'te_trades', 'avg_trade%', 'train_x', 'test_x'])
    R['trades_per_week'] = (R.tr_trades + R.te_trades) / ((tr_days + te_days) / 5)
    pd.set_option('display.width', 220)
    f = {'avg_trade%': '{:+.3f}'.format, 'train_x': '{:.2f}x'.format, 'test_x': '{:.2f}x'.format, 'trades_per_week': '{:.1f}'.format}
    print(f'{EPIC}: {len(R):,} settings, {tr_days} train days (2024-25), {te_days} test days (2026)')
    print(f"profitable in train: {np.mean(R[R.lev==1].train_x>1):.0%}  | profitable in test: {np.mean(R[R.lev==1].test_x>1):.0%}")
    print('\nBest 12 picked on TRAIN (1x) -> unseen 2026:')
    print(R[R.lev == 1].sort_values('train_x', ascending=False).head(12).to_string(index=False, formatters=f))
    rob = R[(R.lev == 3) & (R.train_x > 1) & (R.test_x > 1)].sort_values('test_x', ascending=False)
    print(f'\nProfitable in BOTH periods at 3x: {len(rob)} settings')
    print(rob.head(12).to_string(index=False, formatters=f))
    R.to_csv(f'Results/intraday_{EPIC.lower()}.tsv', sep='\t', index=False)


if __name__ == '__main__':
    main()
