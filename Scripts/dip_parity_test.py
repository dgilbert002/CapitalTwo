#!/usr/bin/env python3
"""Parity test: the live bot's decision code (bot/dip_strategy, fed only the
last 7 days of 1-min candles up to 15:59:45, exactly like bot/dip_bot.py)
must agree with the backtester's signal on every trading day."""
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'Scripts'))
from bot import dip_strategy as DS  # noqa: E402
import live_replica_backtest as LR  # noqa: E402

m1 = pd.read_sql_query('SELECT * FROM SOXL_cap_1min ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
m1['t'] = pd.to_datetime(m1['timestamp'])

# backtester view: full history, decision on 15:55 candle
full5 = DS.build_5min(m1)
bt_sig = DS.signal_series(full5)
bt = dict(zip(full5['t'], bt_sig))

# independent cross-check against the mega-sweep engine's own candles/indicators
lm1 = LR.load_1m(); lm5 = LR.five_min(lm1)
import soxl_sweep2 as S2  # noqa: E402
c = lm5['close']
ms = ((c / c.shift(78) - 1) * 100 < -2) & (S2.macd_hist(c, 19, 39, 9) < -0.001 * c)
ms = dict(zip(lm5['t'], ms))

days = sorted(set(full5['t'][full5['t'].dt.time == pd.Timestamp('15:55').time()]))
agree = agree_ms = n = 0
mism = []
tarr = m1['t'].to_numpy()
for t in days:
    cut = t + pd.Timedelta(minutes=4)                      # 15:59:00 - minute 15:59 still forming
    lo = np.searchsorted(tarr, np.datetime64(t - pd.Timedelta(days=7)))
    hi = np.searchsorted(tarr, np.datetime64(cut))
    live5 = DS.build_5min(m1.iloc[lo:hi])
    if live5.empty or live5['t'].iloc[-1] != t or len(live5) < DS.MIN_HISTORY_BARS:
        continue
    live = DS.decide(live5).buy
    n += 1
    agree += live == bool(bt[t])
    agree_ms += live == bool(ms.get(t, False))
    if live != bool(bt[t]):
        mism.append(t)
print(f'{n} trading days checked')
print(f'live decision == backtester signal : {agree}/{n}')
print(f'live decision == mega-sweep engine : {agree_ms}/{n}')
print(f'BUY days: {sum(bool(bt[t]) for t in days)}')
if mism:
    print('mismatches:', mism[:10])

# ---- trend filter parity: live (hourly 15:00 closes for past days + today's 15:55 price)
#      vs backtest (15:55 closes of every trading day)
h1 = pd.read_sql_query('SELECT * FROM SOXL_cap_1h ORDER BY timestamp', sqlite3.connect(os.path.join(ROOT, 'database_av.db')))
h1['t'] = pd.to_datetime(h1['timestamp'])
daily_live = DS.daily_closes_from_hourly(h1)
_d = full5[full5['t'].dt.time == pd.Timestamp('15:55').time()]
dec5 = pd.Series(_d['close'].to_numpy(), index=_d['t'].dt.normalize().to_numpy())
# backtest series needs history before 2024: use hourly closes before the 1-min data starts
bt_daily = pd.concat([daily_live[daily_live.index < dec5.index[0]], dec5])
bt_below = bt_daily < bt_daily.rolling(DS.TREND_SMA_DAYS).mean()
agree = n = 0
for t in dec5.index:
    live_b = DS.below_trend(daily_live[daily_live.index < t], float(dec5[t]))
    n += 1
    agree += live_b == bool(bt_below[t])
print(f'trend filter (200-day) live == backtest : {agree}/{n}')
