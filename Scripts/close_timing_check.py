#!/usr/bin/env python3
"""How much does deciding on the still-forming candle (T-60s, current price)
change decisions vs the finished 5-min candle? SOXL, Capital.com 1-min bid/ask,
for the 16:00 ET close and the 20:00 ET extended close.

A = full 5-min candles (last candle closes AT the close)
B = same, but the last candle is built from its first 4 minutes (price at T-60s)
Signals: ~360 indicator rules (RSI, BB, ROC, Keltner, MACD, stochastic ...).
"""
import sys, os
import numpy as np, pandas as pd
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import live_replica_backtest as LR
import mega_sweep as MS

def candles(m1, close_hhmm, partial):
    t_close = pd.Timestamp(close_hhmm).time()
    x = m1.copy()
    if partial:   # drop the final minute before each close (still forming at T-60s)
        last_min = (pd.Timestamp(close_hhmm) - pd.Timedelta(minutes=1)).time()
        x = x[x['t'].dt.time != last_min]
    x = x.set_index('t')
    a = x.resample('5min', label='left', closed='left').agg(
        {'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last', 'volume': 'sum'}).dropna().reset_index()
    return a

def main():
    m1 = LR.load_1m()
    for close in ('16:00', '20:00'):
        dec_t = (pd.Timestamp(close) - pd.Timedelta(minutes=5)).time()
        A = candles(m1, close, False); B = candles(m1, close, True)
        ia = A.index[A['t'].dt.time == dec_t]; ib = B.index[B['t'].dt.time == dec_t]
        da = pd.Series(ia, index=A['t'][ia].dt.normalize()); db = pd.Series(ib, index=B['t'][ib].dt.normalize())
        days = da.index.intersection(db.index)
        sa, sb = MS.five_min_signals(A), MS.five_min_signals(B)
        agree, fired_a, fired_both = [], [], []
        for k in sa:
            a = np.nan_to_num(sa[k].to_numpy(dtype=float))[da[days].to_numpy()] > 0
            b = np.nan_to_num(sb[k].to_numpy(dtype=float))[db[days].to_numpy()] > 0
            if a.sum() + b.sum() == 0: continue
            agree.append((a == b).mean()); fired_a.append(a.sum())
            fired_both.append((a & b).sum() / max((a | b).sum(), 1))
        # price move in the final minute (T-60s -> close) and in the last 15s proxy
        pa = A['close'].to_numpy()[da[days].to_numpy()]; pb = B['close'].to_numpy()[db[days].to_numpy()]
        mv = (pa / pb - 1) * 100
        print(f'\n=== SOXL close {close} ET: {len(days)} days, {len(agree)} indicators ===')
        print(f'  same BUY/NO decision on a given day: median {np.median(agree):.1%}, worst indicator {np.min(agree):.1%}')
        print(f'  of days where either version fires, both fire: median {np.median(fired_both):.0%}')
        print(f'  price move in the final minute: median |move| {np.median(np.abs(mv)):.2f}%, 90th pct {np.quantile(np.abs(mv), .9):.2f}%, max {np.abs(mv).max():.1f}%')


def pnl_compare():
    m1 = LR.load_1m()
    for close in ('16:00', '20:00'):
        dec_t = (pd.Timestamp(close) - pd.Timedelta(minutes=5)).time()
        A = candles(m1, close, False); B = candles(m1, close, True)
        ia = A.index[A['t'].dt.time == dec_t]; ib = B.index[B['t'].dt.time == dec_t]
        da = pd.Series(ia, index=A['t'][ia].dt.normalize()); db = pd.Series(ib, index=B['t'][ib].dt.normalize())
        days = da.index.intersection(db.index)
        pa = pd.Series(A['close'].to_numpy()[da[days].to_numpy()], index=days)      # price at the close
        pb = pd.Series(B['close'].to_numpy()[db[days].to_numpy()], index=days)      # price at T-60s
        nxt = pa.shift(-1)
        rA = (nxt / pa - 1).fillna(0)          # backtest: decide & fill at the close
        rB = (nxt / pb - 1).fillna(0)          # live: decide & fill ~T-60s..T-15s
        sa, sb = MS.five_min_signals(A), MS.five_min_signals(B)
        rows = []
        for k in sa:
            a = np.nan_to_num(sa[k].to_numpy(dtype=float))[da[days].to_numpy()] > 0
            b = np.nan_to_num(sb[k].to_numpy(dtype=float))[db[days].to_numpy()] > 0
            if a.sum() < 20: continue
            gA = np.prod(1 + 3 * rA[a]); gB = np.prod(1 + 3 * rB[b])
            rows.append((k, a.sum(), gA, gB))
        d = pd.DataFrame(rows, columns=['ind', 'trades', 'backtest_x', 'live_x'])
        same_side = ((d.backtest_x > 1) == (d.live_x > 1)).mean()
        corr = np.corrcoef(np.log(d.backtest_x.clip(1e-6)), np.log(d.live_x.clip(1e-6)))[0, 1]
        top = d.sort_values('backtest_x', ascending=False).head(20)
        print(f'\n--- {close} ET, 3x leverage, hold to next close, {len(d)} indicators with >=20 trades ---')
        print(f'  backtest vs live agree on profit/loss: {same_side:.0%} | correlation of results: {corr:.2f}')
        print(f'  median ratio live/backtest growth: {np.median(d.live_x / d.backtest_x):.2f}')
        print(f'  top-20 by backtest: median backtest {top.backtest_x.median():.1f}x -> live {top.live_x.median():.1f}x')
        print(top.head(6).to_string(index=False, formatters={'backtest_x': '{:.1f}x'.format, 'live_x': '{:.1f}x'.format}))

pnl_compare()
