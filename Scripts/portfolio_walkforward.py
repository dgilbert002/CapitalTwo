#!/usr/bin/env python3
"""Walk-forward portfolio test: every January, pick sleeves using ONLY data
before that January, trade them for the year, repeat. The chained result is
what running this process live would have produced.

Selection each year:
  * candidate settings with >= MIN_TRADES trades in the look-back window
  * score = look-back CAGR / |max drawdown| (Calmar), drawdown cap
  * greedy add while the portfolio's look-back Calmar improves
  * at most MAX_PER_EPIC sleeves per market, pairwise correlation < CORR_CAP
"""
import itertools
import os
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import multi_sweep as MS  # noqa: E402

MAX_SLEEVES, MAX_PER_EPIC, CORR_CAP, MIN_TRADES, DD_CAP = 8, 2, 0.5, 15, -0.45
YEARS = [2023, 2024, 2025, 2026]
LEVS_KEEP = None


def series_for_epic(epic):
    d, A = MS.daily(epic)
    mt = MS.META[epic]
    maxlev = min(100 / float(mt['margin_pct']), 20)
    levs = [l for l in (1, 2, 3, 5, 10, 20) if l <= maxlev]
    fl = abs(mt['overnight']['longRate']) / 100
    fs = max(-mt['overnight']['shortRate'], 0) / 100
    dates = d['date'].to_numpy()
    idx = pd.DatetimeIndex(dates)
    cols, names, ntr = [], [], []
    for name, (ent, exi, hold, side) in MS.rules(d).items():
        for trail in (None, 0.08, 0.15, 0.25):
            if hold < 9999 and trail:
                continue
            tr = MS.trades(d, A, ent, exi, hold, side, trail)
            if len(tr) < 8:
                continue
            fund = fl if side == 1 else fs
            I = np.array([t[0] for t in tr])
            J = np.array([t[1] for t in tr])
            ret = np.array([t[2] for t in tr])
            worst = np.array([t[3] for t in tr])
            nights = (dates[J] - dates[I]).astype('timedelta64[D]').astype(int)
            for lev in levs:
                r = np.where(lev * worst <= -0.8, lev * worst, lev * (ret - fund * nights))
                r = np.maximum(r, -1.0)
                s = np.zeros(len(d), dtype=np.float32)
                np.add.at(s, J, r)
                cols.append(s)
                names.append((epic, name, trail or 0, lev))
                ntr.append(np.bincount(pd.DatetimeIndex(dates[J]).year, minlength=2030)[2021:2027])
    print(f'{epic}: {len(cols)} series', flush=True)
    return idx, np.array(cols), names, np.array(ntr)


def calmar(r):
    eq = np.cumprod(1 + r)
    yrs = len(r) / 252
    dd = (eq / np.maximum.accumulate(np.maximum(eq, 1)) - 1).min()
    cagr = eq[-1] ** (1 / yrs) - 1 if eq[-1] > 0 else -1
    return cagr, dd, cagr / max(abs(dd), 0.05)


def main():
    epics = sys.argv[1:] or list(MS.META)
    with Pool(os.cpu_count()) as p:
        parts = p.map(series_for_epic, epics)
    full_idx = pd.DatetimeIndex(sorted(set().union(*[set(x[0]) for x in parts])))
    full_idx = full_idx[full_idx >= '2021-03-01']
    mats, names, ntr = [], [], []
    for idx, M, nm, nt in parts:
        df = pd.DataFrame(M.T, index=idx).reindex(full_idx).fillna(0.0)
        mats.append(df.to_numpy(dtype=np.float32).T)
        names += nm
        ntr.append(nt)
    X = np.vstack(mats)                     # settings x days
    NT = np.vstack(ntr)                     # settings x years(2021..2026) trade counts
    years = full_idx.year.to_numpy()
    print(f'{X.shape[0]:,} candidate series')

    chained, picks = [], {}
    for Y in YEARS:
        lb = years < Y
        ntr_lb = NT[:, :Y - 2021].sum(1)
        R = X[:, lb]
        eq = np.cumprod(1 + R.astype(np.float64), axis=1)
        yrs = lb.sum() / 252
        cagr = np.where(eq[:, -1] > 0, eq[:, -1] ** (1 / yrs) - 1, -1)
        dd = (eq / np.maximum.accumulate(np.maximum(eq, 1), axis=1) - 1).min(1)
        score = cagr / np.maximum(np.abs(dd), 0.05)
        ok = (ntr_lb >= MIN_TRADES) & (dd >= DD_CAP) & (cagr > 0)
        order = np.argsort(-np.where(ok, score, -np.inf))[:400]
        chosen, per_epic = [], {}
        best_port = -np.inf
        for k in order:
            if not ok[k]:
                break
            e = names[k][0]
            if per_epic.get(e, 0) >= MAX_PER_EPIC:
                continue
            if chosen:
                c = np.corrcoef(np.vstack([R[k]] + [R[j] for j in chosen]))[0, 1:]
                if np.nanmax(c) > CORR_CAP:
                    continue
            trial = chosen + [k]
            s = calmar(R[trial].mean(0))[2]
            if s > best_port or len(chosen) < 3:
                chosen, best_port = trial, max(s, best_port)
                per_epic[e] = per_epic.get(e, 0) + 1
            if len(chosen) >= MAX_SLEEVES:
                break
        picks[Y] = [names[k] for k in chosen]
        yr = years == Y
        pr = X[chosen][:, yr].mean(0)
        chained.append(pd.Series(pr, index=full_idx[yr]))
        g = np.prod(1 + pr)
        print(f'\n{Y}: picked using data before {Y} -> traded in {Y}: {g:.2f}x')
        for n in picks[Y]:
            print(f'   {n[0]:6s} {n[1]:28s} trail {n[2]:.2f} {n[3]}x')
    port = pd.concat(chained)
    eqc = (1 + port).cumprod()
    dd = (eqc / eqc.cummax() - 1).min()
    yrs = (port.index[-1] - port.index[0]).days / 365.25
    print(f'\nWALK-FORWARD {port.index[0].date()} -> {port.index[-1].date()}: {eqc.iloc[-1]:.1f}x '
          f'({eqc.iloc[-1] ** (1 / yrs) - 1:+.0%}/yr), max drawdown {dd:.0%}')
    pd.to_pickle({'port': port, 'picks': picks}, '/tmp/claude-0/walkforward.pkl')


if __name__ == '__main__':
    main()
