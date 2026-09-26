#!/usr/bin/env python3
"""Analyse mega_sweep.py output: best raw, walk-forward, and robust settings."""
import json
import os
import sys

import numpy as np
import pandas as pd

EPIC = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
OUT = os.environ.get('MEGA_OUT', '/tmp/claude-0/mega')
START = 500.0

arr = np.load(f'{OUT}/{EPIC}_metrics.npy', mmap_mode='r')  # E,S,L,N,4
names = pd.read_csv(f'{OUT}/{EPIC}_rules.txt', header=None)[0].to_numpy()
meta = json.load(open(f'{OUT}/{EPIC}_meta.json'))
EX, SL, LV = meta['exits'], meta['sls'], meta['levs']
E, S, L, N, _ = arr.shape
y_tr = (pd.Timestamp(meta['split']) - pd.Timestamp(meta['first'])).days / 365.25
y_te = (pd.Timestamp(meta['last']) - pd.Timestamp(meta['split'])).days / 365.25
y_all = y_tr + y_te
tr, te, al, dd = (np.asarray(arr[..., k]) for k in range(4))
total = tr.size
print(f'{EPIC}: {N:,} entry rules x {E} exits x {S} stops x {L} leverages = {total:,} backtests')
print(f'train {meta["first"]} -> {meta["split"]} ({y_tr:.1f}y), test -> {meta["last"]} ({y_te:.1f}y)\n')

cagr = lambda lg, y: 100 * np.expm1(lg / y)
both = (tr > 0) & (te > 0)
print(f'Profitable: train {np.mean(tr > 0):.0%}, test {np.mean(te > 0):.0%}, both {np.mean(both):.0%}')
# does train performance predict test performance?
q = np.quantile(tr, [0.5, 0.9, 0.99, 0.999])
for lo, lbl in zip(q, ['top 50%', 'top 10%', 'top 1%', 'top 0.1%']):
    m = tr >= lo
    print(f'  settings in train {lbl:8s}: {np.mean(te[m] > 0):.0%} profitable on test, median test CAGR {np.median(cagr(te[m], y_te)):+.0f}%')


def rows(idx):
    e, s, l, n = idx
    return pd.DataFrame({
        'rule': names[n], 'exit': np.array(EX)[e], 'sl%': np.array(SL)[s], 'lev': np.array(LV)[l],
        'train $': START * np.exp(tr[idx]), 'test $': START * np.exp(te[idx]),
        'all $': START * np.exp(al[idx]), 'maxDD': dd[idx]})


def show(title, flat_idx, k=15):
    idx = np.unravel_index(flat_idx[:k], tr.shape)
    d = rows(idx)
    print(f'\n{title}')
    print(d.to_string(index=False, formatters={'train $': '{:,.0f}'.format, 'test $': '{:,.0f}'.format,
                                               'all $': '{:,.0f}'.format, 'maxDD': '{:.0%}'.format},
                      max_colwidth=60))
    return d


# A) raw most profitable over the whole period
A = show('A) MOST PROFITABLE over the full period (raw, in-sample):', np.argsort(-al, axis=None))
# B) walk-forward: best on train only
B = show('B) Best on TRAIN only -> what happened on unseen TEST:', np.argsort(-tr, axis=None))
# C) robust: profitable both halves, full-period DD better than -60%, neighbours also good
score = np.minimum(cagr(tr, y_tr), cagr(te, y_te))
score[~both | (dd < -0.6)] = -np.inf
# neighbour robustness: share of adjacent exit/stop/leverage settings profitable in both halves
bf = both.astype(np.float32)
nb = np.zeros_like(bf)
cnt = np.zeros_like(bf)
for ax in range(3):
    for sh in (-1, 1):
        rolled = np.roll(bf, sh, axis=ax)
        valid = np.ones_like(bf)
        sl_ = [slice(None)] * 4
        sl_[ax] = 0 if sh == 1 else -1
        valid[tuple(sl_)] = 0
        nb += rolled * valid
        cnt += valid
nbr = nb / np.maximum(cnt, 1)
score[nbr < 0.8] = -np.inf
C = show('C) ROBUST: profitable in both halves, DD > -60%, >=80% of neighbouring exit/stop/leverage also profitable\n'
         '   ranked by the weaker half\'s annual growth:', np.argsort(-score, axis=None), 25)

os.makedirs('Results', exist_ok=True)
pd.concat([A.assign(list='A_raw'), B.assign(list='B_train'), C.assign(list='C_robust')]).to_csv(
    f'Results/{EPIC.lower()}_mega_top.tsv', sep='\t', index=False, float_format='%.3f')
