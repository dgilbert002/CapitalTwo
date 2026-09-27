#!/usr/bin/env python3
"""Parallel, compounding portfolio of the edge sleeves from edges.py.

Every day each sleeve gets a notional weight (x equity) from data up to the
previous day only:
  risk parity   weight ~ 1 / trailing 60-day volatility of the sleeve
  selection     'all'  : every sleeve, no choosing
                'wf'   : monthly walk-forward - keep sleeves whose trailing
                         252-day Sharpe > 0 (all kept until a year of history)
  vol target    scale the whole book so its trailing 60-day vol = TARGET
  margin cap    sum(weight x market margin) <= 90% of equity
  brake         if equity falls BRAKE from its peak, halve exposure for 20 days
Equity compounds daily across all sleeves.
"""
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import edges as E  # noqa: E402

MARGIN = {e: float(E.META[e]['margin_pct']) / 100 for e in E.META}


def sleeve_margin(name):
    if name.startswith('reversal'):
        return 0.20
    if name.startswith('soxl_dip'):
        return 0.20
    return MARGIN[name.split('_', 1)[1]]


def run(R, target, select='all', brake=0.2, max_w=5.0):
    vol = R.rolling(60, min_periods=20).std().shift(1) * np.sqrt(252)
    sharpe = (R.rolling(252, min_periods=252).mean() / R.rolling(252, min_periods=252).std()).shift(1)
    month = R.index.to_period('M')
    marg = np.array([sleeve_margin(c) for c in R.columns])
    eq, peak, cool = 1.0, 1.0, 0
    out, wlog = [], []
    active = np.ones(R.shape[1], bool)
    port_hist = []
    for t in range(len(R)):
        if select == 'wf' and (t == 0 or month[t] != month[t - 1]):
            s = sharpe.iloc[t].to_numpy()
            active = np.where(np.isnan(s), True, s > 0)
        v = vol.iloc[t].to_numpy()
        ok = active & np.isfinite(v) & (v > 0)
        w = np.zeros(R.shape[1])
        if ok.any():
            w[ok] = 1 / v[ok]
            w /= w[ok].sum()
            # scale to target using trailing covariance of the sleeves
            hist = R.iloc[max(0, t - 60):t]
            if len(hist) >= 20:
                pv = np.sqrt(w @ hist.cov().to_numpy() @ w * 252)
                if pv > 0:
                    w *= target / pv
        w = np.minimum(w, max_w)
        m = (w * marg).sum()
        if m > 0.9:
            w *= 0.9 / m
        if cool > 0:
            w *= 0.5
            cool -= 1
        r = float(w @ R.iloc[t].to_numpy())
        eq *= max(1 + r, 0)
        peak = max(peak, eq)
        if brake and eq / peak - 1 < -brake and cool == 0:
            cool, peak = 20, eq
        out.append(eq)
        wlog.append(w.sum())
    return pd.Series(out, index=R.index), pd.Series(wlog, index=R.index)


def report(name, eq, gross):
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    dd = (eq / eq.cummax() - 1).min()
    yearly = eq.groupby(eq.index.year).last() / eq.groupby(eq.index.year).last().shift(1).fillna(1.0)
    print(f'{name:34s} {eq.iloc[-1]:8.1f}x {eq.iloc[-1] ** (1 / yrs) - 1:+6.0%}/yr  maxDD {dd:5.0%}  '
          f'avg gross {gross.mean():.1f}x | ' + ' '.join(f'{y}:{v:5.2f}x' for y, v in yearly.items()))


def main():
    R = pd.read_pickle('/tmp/claude-0/sleeves.pkl')
    print(f'{R.shape[1]} sleeves, {R.index[0].date()} -> {R.index[-1].date()}\n')
    res = {}
    for select in ('all', 'wf'):
        for target in (0.20, 0.30, 0.40, 0.60, 0.80):
            eq, g = run(R, target, select)
            res[(select, target)] = eq
            report(f'{select:3s} sleeves, vol target {target:.0%}', eq, g)
        print()
    pd.to_pickle(res, '/tmp/claude-0/edge_port.pkl')


if __name__ == '__main__':
    main()
