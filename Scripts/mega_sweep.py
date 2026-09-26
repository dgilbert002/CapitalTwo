#!/usr/bin/env python3
"""Mega sweep: millions of honest overnight-trade settings for one epic.

Uses the live-timing replica from live_replica_backtest.py (1-min Capital.com
bid/ask data, decision at T-15s on a partial 5-min candle, ask entry, bid exit,
bid-triggered stops, overnight funding, <=5x leverage).

Search space
  entry rules  = single signals  x  daily filters
               + pairs of signals (A AND B) from different families
  exit time    = next day 09:30 / 10:00 / 11:00 / 12:30 / 14:00 / 15:59:30
  stop-loss    = none, 2..15 %
  leverage     = 1..5x

Every setting is scored on TRAIN (< SPLIT), TEST (>= SPLIT) and ALL.
Equity maths is done on whole matrices (settings x days) in log space, spread
over all CPU cores. Per-setting log-growth is saved to $MEGA_OUT so any
setting can be re-inspected without re-running.
"""
import itertools
import os
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_replica_backtest as LR  # noqa: E402
import soxl_sweep2 as S2  # noqa: E402

EPIC = sys.argv[1] if len(sys.argv) > 1 else 'SOXL'
SPLIT = pd.Timestamp('2025-10-22')
EXITS = ['09:30', '10:00', '11:00', '12:30', '14:00', '15:59']
SLS = [0, 2, 3, 4, 5, 6, 8, 10, 15]
LEVS = [1, 2, 3, 4, 5]
MIN_TRAIN, MIN_TEST = 20, 10
OUT = os.environ.get('MEGA_OUT', '/tmp/claude-0/mega')  # ~1 GB, not for git
CHUNK = 8000


# ------------------------------------------------------------------ signals
def five_min_signals(m5):
    c, h, l, v = m5['close'], m5['high'], m5['low'], m5['volume']
    s = {}
    for n in [2, 3, 4, 5, 7, 9, 14, 21]:
        r = S2.rsi(c, n)
        for th in [5, 10, 15, 20, 25, 30, 35, 40, 45]:
            s[f'rsi|{n}<{th}'] = r < th
    for n in [5, 10, 15, 20, 30, 40, 60, 78, 120, 156]:
        m, sd = c.rolling(n).mean(), c.rolling(n).std()
        for k in [0.5, 1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0]:
            s[f'bb|{n}<-{k}'] = c < m - k * sd
    for n in [3, 6, 10, 15, 20, 30, 40, 60, 78, 117, 156, 234]:
        roc = (c / c.shift(n) - 1) * 100
        for th in [0.5, 1, 1.5, 2, 3, 4, 5, 7, 10]:
            s[f'roc|{n}<-{th}'] = roc < -th
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    for n in [5, 10, 20, 40, 78]:
        e, a = c.ewm(span=n, adjust=False).mean(), tr.rolling(n).mean()
        for k in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]:
            s[f'kelt|{n}<-{k}'] = c < e - k * a
    for f, sl_, g in [(5, 13, 4), (5, 18, 4), (8, 18, 4), (8, 21, 5), (12, 26, 9), (13, 30, 9), (19, 39, 9)]:
        mh = S2.macd_hist(c, f, sl_, g) / c
        for th in [0.0, 0.0005, 0.001, 0.002, 0.003, 0.005]:
            s[f'macdneg|{f}/{sl_}/{g}<-{th}'] = mh < -th
    for n in [5, 9, 14, 21, 40]:
        lo, hi = l.rolling(n).min(), h.rolling(n).max()
        k = (c - lo) / (hi - lo) * 100
        for th in [5, 10, 15, 20, 30]:
            s[f'stoch|{n}<{th}'] = k < th
    for n in [3, 4, 5, 6, 8]:
        dn = (c < c.shift()).astype(int)
        s[f'downbars|{n}'] = dn.rolling(n).sum() == n
    return s


def day_features(m1, m5, dec_idx, days):
    """Features known at 15:59:45 on each trading day."""
    d5 = m5.iloc[dec_idx].reset_index(drop=True)
    dc = d5['close']
    f = {}
    # today's move so far vs previous decision price
    ch1 = dc.pct_change() * 100
    for th in [0.5, 1, 2, 3, 4, 5, 7, 10]:
        f[f'daychg|<-{th}'] = ch1 < -th
        f[f'daychg|>+{th}'] = ch1 > th
    # move since 09:30 open
    op = m1[m1['t'].dt.time == pd.Timestamp('09:30').time()].set_index('date')['open']
    o = pd.Series([op.get(d[0], np.nan) for d in days] + [np.nan])[:len(dc)].to_numpy()
    intr = (dc.to_numpy() / o - 1) * 100
    for th in [0.5, 1, 2, 3, 5, 7]:
        f[f'intraday|<-{th}'] = intr < -th
        f[f'intraday|>+{th}'] = intr > th
    # daily trend filters
    for n in [5, 10, 20, 30, 50, 100, 150]:
        sma = dc.rolling(n).mean()
        f[f'sma|>{n}d'] = dc > sma
        f[f'sma|<{n}d'] = dc < sma
    for n in [2, 3, 4, 5, 7, 10]:
        ch = dc.pct_change(n)
        f[f'ndays|down{n}'] = ch < 0
        f[f'ndays|up{n}'] = ch > 0
    # volatility regime: 10d realised vol vs its 60d median
    rv = ch1.rolling(10).std()
    f['vol|high'] = rv > rv.rolling(60).median()
    f['vol|low'] = rv < rv.rolling(60).median()
    # day of week of entry
    dow = pd.Series([pd.Timestamp(d[0]).weekday() for d in days] + [0])[:len(dc)]
    for k, name in enumerate(['mon', 'tue', 'wed', 'thu', 'fri']):
        f[f'dow|not_{name}'] = dow != k
    return {k: np.nan_to_num(np.asarray(v, dtype=float)) > 0 for k, v in f.items()}


def build_masks(sig5, dayf, dec_idx, tr_m, te_m):
    """Entry masks: signal x filter, and signal AND signal across families."""
    names, rows = [], []
    base = {k: (np.nan_to_num(v.to_numpy(dtype=float))[dec_idx] > 0) for k, v in sig5.items()}
    base.update(dayf)
    ok = lambda m: (m & tr_m).sum() >= MIN_TRAIN and (m & te_m).sum() >= MIN_TEST
    base = {k: v for k, v in base.items() if ok(v)}
    keys = list(base)
    fam = {k: k.split('|')[0] for k in keys}
    filters = [k for k in keys if fam[k] in ('sma', 'ndays', 'vol', 'dow', 'daychg', 'intraday')]
    for k in keys:
        names.append(k)
        rows.append(base[k])
    for a, b in itertools.combinations(keys, 2):
        if fam[a] == fam[b]:
            continue
        m = base[a] & base[b]
        if ok(m):
            names.append(f'{a} & {b}')
            rows.append(m)
    M = np.array(rows, dtype=bool)
    # drop exact duplicate masks (keep first name)
    _, first = np.unique(np.packbits(M, axis=1), axis=0, return_index=True)
    first.sort()
    return [names[i] for i in first], M[first], len(filters)


# ------------------------------------------------------------------ scoring
G = {}


def init(M, R, nights, tr_m, te_m):
    G.update(M=M, R=R, nights=nights, tr=tr_m, te=te_m)


def score(job):
    ex, sl = job
    M, r, nights = G['M'], G['R'][(ex, sl)], G['nights']
    tr, te = G['tr'], G['te']
    out = np.empty((len(LEVS), M.shape[0], 4), dtype=np.float32)  # train, test, all log-growth; all maxDD
    for li, lev in enumerate(LEVS):
        g = np.maximum(1 + LR.INVEST * lev * (r - LR.FUND * nights), 1e-9).astype(np.float32)
        lg = np.log(g)
        for s in range(0, M.shape[0], CHUNK):
            m = M[s:s + CHUNK]
            L = np.where(m, lg, 0.0).astype(np.float32)
            cum = np.cumsum(L, axis=1)
            peak = np.maximum.accumulate(np.maximum(cum, 0), axis=1)
            out[li, s:s + CHUNK, 0] = L[:, tr].sum(1)
            out[li, s:s + CHUNK, 1] = L[:, te].sum(1)
            out[li, s:s + CHUNK, 2] = cum[:, -1]
            out[li, s:s + CHUNK, 3] = np.expm1((cum - peak).min(1))
    return ex, sl, out


def main():
    t0 = time.time()
    m1 = LR.load_1m()
    m5 = LR.five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = LR.trade_days(m1, m5)
    dates = pd.to_datetime(pd.Series([d[0] for d in days]))
    nights = np.array([d[4] for d in days], dtype=np.float32)
    dec_idx = np.array([d[1] for d in days])
    tr_m, te_m = (dates < SPLIT).to_numpy(), (dates >= SPLIT).to_numpy()
    print(f'{EPIC}: {len(days)} days {dates.iloc[0].date()} -> {dates.iloc[-1].date()}  ({time.time()-t0:.0f}s)', flush=True)

    sig5 = five_min_signals(m5)
    dayf = day_features(m1, m5, dec_idx, days)
    names, M, nf = build_masks(sig5, dayf, dec_idx, tr_m, te_m)
    print(f'{len(sig5)} candle signals + {len(dayf)} day features -> {len(names):,} distinct entry rules '
          f'({time.time()-t0:.0f}s)', flush=True)

    R = {}
    for ex in EXITS:
        dd = extend_exits(days, m1, ex)
        for sl in SLS:
            R[(ex, sl)] = LR.returns(dd, bo, bl, ex, sl or None).astype(np.float32)
    total = len(names) * len(EXITS) * len(SLS) * len(LEVS)
    print(f'Scoring {total:,} settings on {os.cpu_count()} cores...', flush=True)

    os.makedirs(OUT, exist_ok=True)
    jobs = list(itertools.product(EXITS, SLS))
    res = {}
    with Pool(os.cpu_count(), initializer=init, initargs=(M, R, nights, tr_m, te_m)) as p:
        for k, (ex, sl, out) in enumerate(p.imap_unordered(score, jobs), 1):
            res[(ex, sl)] = out
            print(f'  {k}/{len(jobs)} exit {ex} SL {sl}  ({time.time()-t0:.0f}s)', flush=True)

    # flatten to arrays: [exit, sl, lev, rule] -> metrics
    arr = np.stack([np.stack([res[(ex, sl)] for sl in SLS]) for ex in EXITS])  # E,S,L,N,4
    np.save(f'{OUT}/{EPIC}_metrics.npy', arr)
    pd.Series(names).to_csv(f'{OUT}/{EPIC}_rules.txt', index=False, header=False)
    pd.Series({'exits': EXITS, 'sls': SLS, 'levs': LEVS, 'split': str(SPLIT.date()),
               'first': str(dates.iloc[0].date()), 'last': str(dates.iloc[-1].date())}).to_json(f'{OUT}/{EPIC}_meta.json')
    print(f'Saved {arr.shape} metrics -> {OUT}/  total {time.time()-t0:.0f}s', flush=True)


def extend_exits(days, m1, ex):
    """Return day tuples whose exits dict contains exit time `ex` (bid at open of that minute)."""
    tarr = m1['t'].to_numpy()
    bo = m1['bid_open'].to_numpy()
    et = pd.Timestamp(ex).time()
    out = []
    for i, (d, di, entry, exits, nights) in enumerate(days):
        if ex in exits:
            out.append((d, di, entry, exits, nights))
            continue
        nd = d + pd.Timedelta(days=nights)
        a = exits['15:59'][0]
        e = np.searchsorted(tarr, np.datetime64(pd.Timestamp.combine(nd, et)))
        e = min(e, exits['15:59'][1])
        ex2 = dict(exits)
        ex2[ex] = (a, e, bo[e])
        out.append((d, di, entry, ex2, nights))
    return out


if __name__ == '__main__':
    main()
