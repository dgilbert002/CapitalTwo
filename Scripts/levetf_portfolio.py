#!/usr/bin/env python3
"""Parallel, compounding dip-buying across 3x index ETFs (SOXL, TQQQ, UPRO, TNA).

Rule per market = the live SOXL rule (hourly proxy), drop threshold scaled by
each market's volatility (SOXL keeps 2%), half size below the 200-day average.
Nothing re-tuned per market.

Each day every market that fires gets `lev` x equity notional; if the total
would exceed MAX_GROSS x equity (Capital.com 20% margin -> 5x, keep a buffer)
all positions are scaled down together. Account brake: equity down BRAKE from
its peak -> no new trades for 20 trading days. Equity compounds daily.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dip_cross_market as DC  # noqa: E402
import edges as E  # noqa: E402

MARKETS = ['SOXL', 'TQQQ', 'UPRO', 'TNA']
MAX_GROSS = 4.5


def sleeves():
    ref_vol = DC.hourly('SOXL').pipe(lambda h: ((h.bid_close + h.ask_close) / 2).pct_change(12).std())
    P, R = {}, {}
    for e in MARKETS:
        h = DC.hourly(e)
        d = E.load(e)
        drop = 2.0 * ((h.bid_close + h.ask_close) / 2).pct_change(12).std() / ref_vol
        buy = DC.signal(h, drop).reindex(d.index).fillna(False).astype(float)
        below = (d['sig'] < d['sig'].rolling(200).mean()).astype(float)
        pos = buy * (1 - 0.5 * below)
        P[e] = pos.shift(1)                       # position held during the day its P&L is booked
        R[e] = E.mtm(d, pos)
    P = pd.DataFrame(P).fillna(0.0)
    R = pd.DataFrame(R).fillna(0.0)
    keep = R.index >= E.START
    return P[keep], R[keep]


def simulate(P, R, lev, brake=0.2, cost_mult=1.0, markets=None):
    cols = markets or list(R.columns)
    P, R = P[cols].to_numpy(), R[cols].to_numpy()
    eq, peak, cool = 1.0, 1.0, 0
    out = np.empty(len(R))
    for t in range(len(R)):
        L = np.full(len(cols), float(lev))
        gross = (L * P[t]).sum()
        if gross > MAX_GROSS:
            L *= MAX_GROSS / gross
        if cool > 0:
            L[:] = 0.0
            cool -= 1
        r = L @ R[t]
        eq *= max(1 + r, 0.0)
        peak = max(peak, eq)
        if brake and eq / peak - 1 < -brake:
            cool, peak = 20, eq
        out[t] = eq
    return out


def describe(idx, eq):
    s = pd.Series(eq, index=idx)
    yrs = (idx[-1] - idx[0]).days / 365.25
    dd = (s / s.cummax() - 1).min()
    ye = s.groupby(s.index.year).last()
    yearly = ye / ye.shift(1).fillna(1.0)
    return s.iloc[-1], s.iloc[-1] ** (1 / yrs) - 1, dd, yearly


def main():
    P, R = sleeves()
    print(f'Days {R.index[0].date()} -> {R.index[-1].date()}; trades per market: '
          + ', '.join(f'{c} {int((P[c].diff() > 0).sum())}' for c in P))
    print(f'Days with 2+ markets in a trade: {int(((P > 0).sum(1) >= 2).sum())}\n')
    for combo in (['SOXL'], ['SOXL', 'TQQQ'], MARKETS):
        for lev in (2, 3, 4, 5):
            x, c, dd, yearly = describe(R.index, simulate(P, R, lev, markets=combo))
            print(f'{"+".join(combo):20s} {lev}x each: {x:7.1f}x ({c:+.0%}/yr) maxDD {dd:4.0%} | '
                  + ' '.join(f'{y}:{v:.2f}x' for y, v in yearly.items()))
        print()
    pd.to_pickle((P, R), '/tmp/claude-0/levetf.pkl')


if __name__ == '__main__':
    main()
