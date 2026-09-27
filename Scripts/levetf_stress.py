#!/usr/bin/env python3
"""Stress tests for the SOXL+TQQQ shared-budget dip portfolio.

1. costs x2 and x3 (spread + funding)
2. results without 2026 (the outlier year)
3. block-bootstrap Monte Carlo (20-day blocks of real daily portfolio returns)
   -> distribution of 1/2/3-year outcomes for a $1,000 and $10,000 start,
   and the chance of reaching $500k.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edges as E  # noqa: E402
import levetf_portfolio as LP  # noqa: E402

COLS = ['SOXL', 'TQQQ']


def port_returns(P, R, budget, cols=COLS):
    Pm, Rm = P[cols].to_numpy(), R[cols].to_numpy()
    out = np.zeros(len(Rm))
    for t in range(len(Rm)):
        on = Pm[t] > 0
        if on.any():
            L = np.zeros(len(cols))
            L[on] = budget / on.sum()
            out[t] = max(L @ Rm[t], -1.0)
    return pd.Series(out, index=R.index)


def recompute_with_costs(mult):
    """Rebuild sleeve returns with spread and funding multiplied."""
    orig = E.mtm

    def mtm_scaled(d, pos):
        d = d.copy()
        d['spr'] *= mult
        d['f_long'] *= mult
        return orig(d, pos)
    E.mtm = mtm_scaled
    try:
        return LP.sleeves()
    finally:
        E.mtm = orig


def stats(r):
    eq = (1 + r).cumprod()
    yrs = (r.index[-1] - r.index[0]).days / 365.25
    return eq.iloc[-1], eq.iloc[-1] ** (1 / yrs) - 1, (eq / eq.cummax() - 1).min()


def main():
    rng = np.random.default_rng(1)
    for mult in (1, 2, 3):
        P, R = recompute_with_costs(mult)
        for b in (2, 3):
            r = port_returns(P, R, b)
            x, c, dd = stats(r)
            x5, c5, dd5 = stats(r[r.index < '2026-01-01'])
            print(f'costs x{mult} budget {b}x: 2021-26 {x:6.1f}x ({c:+.0%}/yr, DD {dd:.0%}) | '
                  f'2021-25 only {x5:5.1f}x ({c5:+.0%}/yr, DD {dd5:.0%})')
    P, R = LP.sleeves()
    print('\nMonte Carlo (20-day blocks resampled from 2021-2025 real returns, 2026 excluded to be conservative):')
    for b in (2, 3):
        r = port_returns(P, R, b)
        r = r[r.index < '2026-01-01'].to_numpy()
        blocks = [r[i:i + 20] for i in range(0, len(r) - 20)]
        for years in (1, 2, 3):
            n = years * 252 // 20
            outs = np.array([np.prod(1 + np.concatenate([blocks[k] for k in rng.integers(0, len(blocks), n)]))
                             for _ in range(5000)])
            q = np.quantile(outs, [0.05, 0.25, 0.5, 0.75, 0.95])
            print(f'  budget {b}x, {years}y: $1,000 -> 5%: ${1000*q[0]:,.0f}  25%: ${1000*q[1]:,.0f}  '
                  f'median: ${1000*q[2]:,.0f}  75%: ${1000*q[3]:,.0f}  95%: ${1000*q[4]:,.0f}  | '
                  f'P(loss) {np.mean(outs < 1):.0%}  P($1k->$500k) {np.mean(outs >= 500):.1%}  '
                  f'P($10k->$500k) {np.mean(outs >= 50):.1%}')


if __name__ == '__main__':
    main()
