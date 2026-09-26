#!/usr/bin/env python3
"""Stress-test candidate settings from the mega sweep.

For each candidate: trade list stats, per-year growth, result without its best
3 trades, and a permutation test - the same number of trades on RANDOM days
(same exit, stop, leverage), 2000 times. If the rule's result isn't well above
the random ones, its profit came from the market drifting up, not from timing.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_replica_backtest as LR  # noqa: E402
import mega_sweep as MS  # noqa: E402

EPIC = 'SOXL'
CANDIDATES = [
    # rule, exit, sl, lev
    ('roc|117<-2 & macdneg|19/39/9<-0.001', '15:59', 0, 5),
    ('roc|117<-2 & macdneg|19/39/9<-0.001', '15:59', 0, 3),
    ('macdneg|19/39/9<-0.0005 & sma|<5d', '09:30', 0, 5),
    ('macdneg|19/39/9<-0.0005 & sma|<5d', '09:30', 0, 3),
    ('roc|60<-3 & macdneg|19/39/9<-0.0005', '14:00', 0, 5),
    ('macdneg|19/39/9<-0.0005 & ndays|down4', '09:30', 10, 5),
    ('roc|10<-0.5 & macdneg|19/39/9<-0.001', '15:59', 15, 5),   # raw #1
    ('bb|20<-1.5 & sma|>50d', '09:30', 8, 3),                   # earlier robust pick
    ('macdneg|19/39/9<-0.001', '15:59', 0, 3),                  # single-signal core
]
RNG = np.random.default_rng(7)


def main():
    m1 = LR.load_1m()
    m5 = LR.five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = LR.trade_days(m1, m5)
    dates = pd.to_datetime(pd.Series([d[0] for d in days]))
    nights = np.array([d[4] for d in days])
    dec_idx = np.array([d[1] for d in days])
    sig5 = MS.five_min_signals(m5)
    dayf = MS.day_features(m1, m5, dec_idx, days)
    base = {k: (np.nan_to_num(v.to_numpy(dtype=float))[dec_idx] > 0) for k, v in sig5.items()}
    base.update(dayf)
    ext = {}
    for rule, ex, sl, lev in CANDIDATES:
        mask = np.ones(len(days), bool)
        for part in rule.split(' & '):
            mask &= base[part]
        if ex not in ext:
            ext[ex] = MS.extend_exits(days, m1, ex)
        r = LR.returns(ext[ex], bo, bl, ex, sl or None)
        g = np.maximum(1 + LR.INVEST * lev * (r - LR.FUND * nights), 0)
        final = LR.START * np.prod(g[mask])
        tg = g[mask]
        no_best3 = LR.START * np.prod(np.sort(tg)[:-3])
        # permutation: same number of trades on random days
        k = int(mask.sum())
        rand = np.array([LR.START * np.prod(g[RNG.choice(len(g), k, replace=False)]) for _ in range(2000)])
        pct = (rand < final).mean()
        yr = pd.Series(np.where(mask, g, 1.0), index=dates.dt.year).groupby(level=0).prod()
        print(f'\n{rule} | exit {ex} | SL {sl or "none"} | {lev}x')
        print(f'  trades {k}, win {np.mean(r[mask] > 0):.0%}, avg SOXL move {np.mean(r[mask]):+.2%}, '
              f'worst {r[mask].min():+.1%}, best {r[mask].max():+.1%}')
        print(f'  $500 -> ${final:,.0f}   without best 3 trades: ${no_best3:,.0f}   '
              f'per-year x: ' + '  '.join(f'{y}:{v:.1f}' for y, v in yr.items()))
        print(f'  random days, same #trades: median ${np.median(rand):,.0f}, 95th pct ${np.quantile(rand, .95):,.0f} '
              f'-> rule beats {pct:.1%} of random')


if __name__ == '__main__':
    main()
