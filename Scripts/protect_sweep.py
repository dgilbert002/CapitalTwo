#!/usr/bin/env python3
"""Protection-layer sweep for the dip strategy.

Two datasets:
  EXACT : the live rule on 1-min Capital.com bid/ask data, 2024-01 -> 2026-09
  CRASH : an hourly proxy of the rule on Capital.com hourly bid/ask data,
          2021-02 -> 2026-09 (includes the 2022 semiconductor crash)

Protection layers (all use only information known at decision time):
  crash   the old app's crash protection (3-day drawdown < -10% blocks the trade
          unless RSI<20 & volume spike, or the drawdown is 'recovering')
  trend   when price is below its N-day average, leverage x mult (0 = skip)
  volt    volatility targeting: leverage x clip(target / 20-day vol)
  brake   account circuit breaker: after a drawdown of X% from the equity peak,
          stop trading for C trading days, then reset the peak

Each setting = base leverage x stop x crash x trend x volt x brake, scored on
both datasets. Output: best profit for each max-drawdown cap.
"""
import itertools
import os
import sqlite3
import sys
from multiprocessing import Pool

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'Scripts'))
import live_replica_backtest as LR  # noqa: E402
from bot import dip_strategy as DS  # noqa: E402

FUND = 0.000222
INVEST = 0.95
LEVS = [2, 3, 4, 5]
SLS = [0, 10, 15]
CRASH = [False, True]
TREND = [None, (50, 0.0), (50, 0.5), (100, 0.0), (100, 0.5), (200, 0.0), (200, 0.5)]
VOLT = [None, 0.03, 0.04, 0.05, 0.07]          # target daily vol for vol targeting
BRAKE = [None, (0.2, 10), (0.2, 20), (0.3, 10), (0.3, 20), (0.4, 20)]


def rsi(c, n=14):
    d = c.diff()
    return 100 - 100 / (1 + d.clip(lower=0).rolling(n).mean() / (-d.clip(upper=0)).rolling(n).mean())


def daily_features(close, volume=None):
    c = pd.Series(close)
    f = pd.DataFrame(index=c.index)
    peak = c.rolling(3, min_periods=1).max()
    dd = (c / peak - 1) * 100
    r = rsi(c)
    rec = dd.rolling(5).apply(lambda x: x.iloc[-1] - x.iloc[0], raw=False)
    bottom = (r < 20)
    if volume is not None:
        v = pd.Series(volume)
        bottom &= v / v.rolling(20, min_periods=1).mean() > 1.5
    else:
        bottom &= False
    f['crash_block'] = (dd < -10) & ~bottom & ~(rec > -3)
    for n in (50, 100, 200):
        f[f'below{n}'] = c < c.rolling(n).mean()          # NaN -> False (no filter until enough history)
    f['vol20'] = c.pct_change().rolling(20).std()
    return f


# ---------------------------------------------------------------- datasets
def exact_dataset():
    m1 = LR.load_1m()
    m5 = LR.five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = LR.trade_days(m1, m5)
    idx = np.array([d[1] for d in days])
    sig = DS.signal_series(m5).to_numpy()[idx]
    dates = pd.to_datetime([d[0] for d in days])
    close = m5['close'].to_numpy()[idx]
    vol = m1.groupby('date')['volume'].sum().reindex([d[0] for d in days]).to_numpy()
    R = {sl: LR.returns(days, bo, bl, '15:59', sl or None) for sl in SLS}
    nights = np.array([d[4] for d in days], float)
    return dict(name='EXACT 2024-26', dates=dates, sig=sig, R=R, nights=nights,
                feat=daily_features(close, vol), periods={'2024-25H2 (train)': dates < '2025-10-22',
                                                          '2025-10 -> 2026-09 (test)': dates >= '2025-10-22'})


def crash_dataset():
    h = pd.read_sql_query('SELECT * FROM SOXL_cap_1h ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
    h['t'] = pd.to_datetime(h['timestamp'])
    h = h[(h.t.dt.weekday < 5) & (h.t.dt.hour >= 4) & (h.t.dt.hour < 20)].reset_index(drop=True)
    c = (h.bid_close + h.ask_close) / 2
    roc = (c / c.shift(12) - 1) * 100
    m = c.ewm(span=3, adjust=False).mean() - c.ewm(span=6, adjust=False).mean()
    hist = (m - m.ewm(span=2, adjust=False).mean()) / c
    sig_all = (roc < -2) & (hist < -0.001)
    dec = np.nonzero((h.t.dt.hour == 15).to_numpy())[0]
    dates = pd.to_datetime(h.t.iloc[dec].dt.normalize().to_numpy())
    ask_c, bid_c, bid_o, bid_l = (h[k].to_numpy() for k in ('ask_close', 'bid_close', 'bid_open', 'bid_low'))
    R = {}
    for sl in SLS:
        r = np.zeros(len(dec))
        for i in range(len(dec) - 1):
            a, b = dec[i], dec[i + 1]
            e = ask_c[a]
            px = bid_c[b]
            if sl:
                stop = e * (1 - sl / 100)
                hit = np.nonzero(bid_l[a + 1:b + 1] <= stop)[0]
                if hit.size:
                    px = min(stop, bid_o[a + 1 + hit[0]])
            r[i] = px / e - 1
        R[sl] = r
    nights = np.r_[np.diff(dates).astype('timedelta64[D]').astype(float), 1]
    close = c.to_numpy()[dec]
    return dict(name='CRASH-TEST 2021-26 (hourly proxy)', dates=dates, sig=sig_all.to_numpy()[dec], R=R, nights=nights,
                feat=daily_features(close), periods={'2021-02 -> 2023-12 (incl. 2022 crash)': dates < '2024-01-01',
                                                     '2022 only': (dates >= '2022-01-01') & (dates < '2023-01-01'),
                                                     '2024-01 -> 2026-09': dates >= '2024-01-01'})


# ---------------------------------------------------------------- engine
D = {}


def simulate(ds, lev, sl, crash, trend, volt, brake, mask=None):
    sig, r, nights, f = ds['sig'], ds['R'][sl], ds['nights'], ds['feat']
    cb = f['crash_block'].to_numpy()
    below = f[f'below{trend[0]}'].to_numpy() if trend else None
    vol = f['vol20'].to_numpy()
    eq, peak, mdd, cool, trades = 1.0, 1.0, 0.0, 0, 0
    for i in range(len(sig)):
        if mask is not None and not mask[i]:
            continue
        if cool > 0:
            cool -= 1
            continue
        if not sig[i] or (crash and cb[i]):
            continue
        L = lev
        if trend and below[i]:
            L *= trend[1]
        if volt and not np.isnan(vol[i]) and vol[i] > 0:
            L *= min(max(volt / vol[i], 0.25), 2.0)
        L = min(L, 5.0)
        if L <= 0:
            continue
        eq *= max(1 + INVEST * L * (r[i] - FUND * nights[i]), 0.0)
        trades += 1
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        if brake and eq / peak - 1 < -brake[0]:
            cool, peak = brake[1], eq
    return eq, mdd, trades


def job(args):
    ds = D['ds']
    lev, sl, crash, trend, volt, brake = args
    out = {'lev': lev, 'sl': sl, 'crash': crash, 'trend': trend, 'volt': volt, 'brake': brake}
    eq, dd, n = simulate(ds, *args)
    out.update(final=eq, maxdd=dd, trades=n)
    for pn, pm in ds['periods'].items():
        e, d, _ = simulate(ds, *args, mask=pm)
        out[f'{pn}|x'] = e
        out[f'{pn}|dd'] = d
    return out


def init(ds):
    D['ds'] = ds


def sweep(ds):
    grid = list(itertools.product(LEVS, SLS, CRASH, TREND, VOLT, BRAKE))
    with Pool(os.cpu_count(), initializer=init, initargs=(ds,)) as p:
        rows = p.map(job, grid, chunksize=50)
    df = pd.DataFrame(rows)
    yrs = (ds['dates'][-1] - ds['dates'][0]).days / 365.25
    df['cagr'] = df['final'] ** (1 / yrs) - 1
    return df


def label(r):
    parts = [f"{r['lev']}x", f"SL{r['sl']}" if r['sl'] else 'noSL']
    if r['crash']:
        parts.append('crashProt')
    if isinstance(r['trend'], tuple):
        parts.append(f"<{r['trend'][0]}d:x{r['trend'][1]}")
    if pd.notna(r['volt']):
        parts.append(f"volTgt{r['volt']:.0%}")
    if isinstance(r['brake'], tuple):
        parts.append(f"brake{int(r['brake'][0]*100)}%/{r['brake'][1]}d")
    return ' '.join(parts)


def main():
    out = {}
    for ds in (crash_dataset(), exact_dataset()):
        df = sweep(ds)
        df['setting'] = df.apply(label, axis=1)
        out[ds['name']] = df
        base = df[(~df.crash) & df.trend.isna() & df.volt.isna() & df.brake.isna() & (df.sl == 15)]
        print(f"\n=== {ds['name']}: {len(df):,} settings, {int(ds['sig'].sum())} signal days ===")
        pcols = [c for c in df.columns if c.endswith('|x')]
        show = lambda x: print(x[['setting', 'final', 'cagr', 'maxdd', 'trades'] + pcols].to_string(
            index=False, formatters={'final': '{:,.1f}x'.format, 'cagr': '{:+.0%}'.format, 'maxdd': '{:.0%}'.format,
                                     **{c: '{:,.2f}x'.format for c in pcols}}))
        print('No protection (just leverage + 15% stop):')
        show(base)
        for cap in (-0.2, -0.3, -0.4, -0.5):
            ok = df[df.maxdd >= cap]
            print(f'\nBest profit with max drawdown better than {cap:.0%}:')
            show(ok.sort_values('final', ascending=False).head(3))
    pd.concat([d.assign(dataset=k) for k, d in out.items()]).drop(columns=['trend', 'brake']).to_csv(
        os.path.join(ROOT, 'Results', 'soxl_protect_sweep.tsv'), sep='\t', index=False, float_format='%.4f')
    pd.to_pickle(out, '/tmp/claude-0/protect.pkl')


if __name__ == '__main__':
    main()
