#!/usr/bin/env python3
"""Build a multi-market portfolio from robust setups found by multi_sweep.py.

Each setup ("sleeve") gets a fixed share of the account, rebalanced daily, and
trades with its own leverage/stop/brake. Sleeves are chosen greedily using ONLY
2021-02..2023-12 (includes the 2022 crash); the finished portfolio is then run
on 2024-01..2026-09, which the selection never saw.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import multi_sweep as MS  # noqa: E402

MAX_SLEEVES = 8
TRAIN_DD_CAP = -0.35


def sleeve_returns(row, cache):
    """Daily return series (on exit days) of one setup at its leverage, incl. its own brake."""
    if row.epic not in cache:
        cache[row.epic] = MS.daily(row.epic)
    d, A = cache[row.epic]
    ent, exi, hold, side = MS.rules(d)[row.rule]
    tr = MS.trades(d, A, ent, exi, hold, side, row.trail or None)
    mt = MS.META[row.epic]
    fund = abs(mt['overnight']['longRate']) / 100 if side == 1 else max(-mt['overnight']['shortRate'], 0) / 100
    dates = d['date'].to_numpy()
    out = pd.Series(0.0, index=pd.DatetimeIndex(dates))
    eq, peak, cool = 1.0, 1.0, -1
    for i, j, ret, worst in tr:
        if i <= cool:
            continue
        nights = (dates[j] - dates[i]).astype('timedelta64[D]').astype(int)
        r = (1 + row.lev * worst if row.lev * worst <= -0.8 else 1 + row.lev * (ret - fund * nights))
        r = max(r, 0.0) - 1
        out.iloc[j] += r
        eq *= 1 + r
        peak = max(peak, eq)
        if row.brake and eq / peak - 1 < -row.brake:
            cool, peak = j + 20, eq
    return out


def stats(r):
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    return eq.iloc[-1], eq.iloc[-1] ** (1 / yrs) - 1, dd


def main():
    cands = pd.read_pickle('/tmp/claude-0/cands.pkl').reset_index(drop=True)
    cache, R = {}, {}
    for k, row in cands.iterrows():
        R[k] = sleeve_returns(row, cache)
    allR = pd.DataFrame(R).fillna(0.0)
    allR = allR[allR.index >= '2021-03-01']
    tr = allR[allR.index < MS.SPLIT]
    te = allR[allR.index >= MS.SPLIT]

    chosen = []
    while len(chosen) < MAX_SLEEVES:
        best, best_c = None, -9
        for k in allR.columns:
            if k in chosen:
                continue
            w = chosen + [k]
            x, c, dd = stats(tr[w].mean(axis=1))
            if dd >= TRAIN_DD_CAP and c > best_c:
                best, best_c = k, c
        if best is None:
            break
        base_c = stats(tr[chosen].mean(axis=1))[1] if chosen else -9
        if best_c <= base_c and len(chosen) >= 3:
            break
        chosen.append(best)
    print('Chosen sleeves (selected on 2021-23 only):')
    for k in chosen:
        r = cands.loc[k]
        print(f'  {r.epic:6s} {r.rule:28s} trail {r.trail:.2f} lev {r.lev}x brake {r.brake:.1f}')
    port = allR[chosen].mean(axis=1)
    for name, s in [('2021-03 -> 2023-12 (selection period, incl. 2022)', port[port.index < MS.SPLIT]),
                    ('2024-01 -> 2026-09 (unseen)', port[port.index >= MS.SPLIT]), ('Whole 5.5 years', port)]:
        x, c, dd = stats(s)
        print(f'  {name:48s} growth {x:7.1f}x  ({c:+.0%}/yr)  max drawdown {dd:.0%}')
    yearly = (1 + port).groupby(port.index.year).prod()
    print('  per year: ' + '  '.join(f'{y}: {v:.2f}x' for y, v in yearly.items()))
    corr = allR[chosen].replace(0, np.nan).corr().where(lambda m: ~np.eye(len(m), dtype=bool)).stack().mean()
    print(f'  average correlation between sleeves (trade days): {corr:.2f}')
    pd.to_pickle({'chosen': [cands.loc[k].to_dict() for k in chosen], 'port': port}, '/tmp/claude-0/portfolio.pkl')


if __name__ == '__main__':
    main()
