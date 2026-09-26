#!/usr/bin/env python3
"""Round 2 of the mega sweep: take the TOP_K best entry rules from round 1
(ranked by their weaker train/test half) and AND each with every other base
signal / day filter, then score all exits x stops x leverages again."""
import itertools
import json
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_replica_backtest as LR  # noqa: E402
import mega_sweep as MS  # noqa: E402

EPIC = 'SOXL'
TOP_K = int(os.environ.get('TOP_K', 3000))
OUT = MS.OUT


def main():
    t0 = time.time()
    prev = np.load(f'{OUT}/{EPIC}_metrics.npy', mmap_mode='r')
    names = pd.read_csv(f'{OUT}/{EPIC}_rules.txt', header=None)[0].tolist()
    best = np.minimum(prev[..., 0], prev[..., 1]).max(axis=(0, 1, 2))   # best weaker-half per rule
    top = np.argsort(-best)[:TOP_K]

    m1 = LR.load_1m()
    m5 = LR.five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = LR.trade_days(m1, m5)
    dates = pd.to_datetime(pd.Series([d[0] for d in days]))
    nights = np.array([d[4] for d in days], dtype=np.float32)
    dec_idx = np.array([d[1] for d in days])
    tr_m, te_m = (dates < MS.SPLIT).to_numpy(), (dates >= MS.SPLIT).to_numpy()
    base = {k: (np.nan_to_num(v.to_numpy(dtype=float))[dec_idx] > 0) for k, v in MS.five_min_signals(m5).items()}
    base.update(MS.day_features(m1, m5, dec_idx, days))
    rule_mask = lambda r: np.logical_and.reduce([base[p] for p in r.split(' & ')])

    new_names, rows = [], []
    for i in top:
        r = names[i]
        fams = {p.split('|')[0] for p in r.split(' & ')}
        m = rule_mask(r)
        for k, v in base.items():
            if k.split('|')[0] in fams:
                continue
            mm = m & v
            if (mm & tr_m).sum() >= MS.MIN_TRAIN and (mm & te_m).sum() >= MS.MIN_TEST:
                new_names.append(f'{r} & {k}')
                rows.append(mm)
    M = np.array(rows, dtype=bool)
    _, first = np.unique(np.packbits(M, axis=1), axis=0, return_index=True)
    first.sort()
    new_names = [new_names[i] for i in first]
    M = M[first]
    print(f'{TOP_K} top rules x base signals -> {len(new_names):,} distinct 3-part rules '
          f'= {len(new_names) * len(MS.EXITS) * len(MS.SLS) * len(MS.LEVS):,} backtests ({time.time()-t0:.0f}s)', flush=True)

    R = {}
    for ex in MS.EXITS:
        dd = MS.extend_exits(days, m1, ex)
        for sl in MS.SLS:
            R[(ex, sl)] = LR.returns(dd, bo, bl, ex, sl or None).astype(np.float32)
    jobs = list(itertools.product(MS.EXITS, MS.SLS))
    res = {}
    with Pool(os.cpu_count(), initializer=MS.init, initargs=(M, R, nights, tr_m, te_m)) as p:
        for k, (ex, sl, out) in enumerate(p.imap_unordered(MS.score, jobs), 1):
            res[(ex, sl)] = out
            if k % 9 == 0:
                print(f'  {k}/{len(jobs)} ({time.time()-t0:.0f}s)', flush=True)
    arr = np.stack([np.stack([res[(ex, sl)] for sl in MS.SLS]) for ex in MS.EXITS])
    tag = f'{EPIC}3'
    np.save(f'{OUT}/{tag}_metrics.npy', arr)
    pd.Series(new_names).to_csv(f'{OUT}/{tag}_rules.txt', index=False, header=False)
    json.dump(json.load(open(f'{OUT}/{EPIC}_meta.json')), open(f'{OUT}/{tag}_meta.json', 'w'))
    print(f'Saved {arr.shape} -> {OUT}/{tag}_*  total {time.time()-t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
