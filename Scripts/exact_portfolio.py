#!/usr/bin/env python3
"""Exact 1-minute validation of the multi-market dip portfolio (2024-26).

For each market: the live rule (bot/dip_strategy) on 5-min candles rebuilt from
1-min Capital.com bid/ask data, decision at T-15s, ASK entry, BID exit at T-30s
next day, 15% emergency stop on the bid, funding per night, half size below the
200-day average (daily closes from hourly data, exactly as the bot does).
Also checks that the bot's own decision code, fed only the last 7 days, agrees
with the backtest on every day. Then runs the shared-budget portfolio.

    python Scripts/exact_portfolio.py SOXL TQQQ
"""
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, 'Scripts'))
import live_replica_backtest as LR  # noqa: E402
from bot import dip_strategy as DS  # noqa: E402

DB = os.path.join(ROOT, 'database_av.db')


def market(epic):
    LR.EPIC = epic
    m1 = LR.load_1m()
    m5 = LR.five_min(m1)
    m5['index_5m'] = np.arange(len(m5))
    days, bo, bl = LR.trade_days(m1, m5)
    idx = np.array([d[1] for d in days])
    dates = pd.to_datetime([d[0] for d in days])
    sig = DS.signal_series(m5).to_numpy()[idx]
    h1 = pd.read_sql_query(f'SELECT * FROM {epic}_cap_1h ORDER BY timestamp', sqlite3.connect(DB))
    h1['t'] = pd.to_datetime(h1['timestamp'])
    daily = DS.daily_closes_from_hourly(h1)
    px = m5['close'].to_numpy()[idx]
    below = np.array([DS.below_trend(daily[daily.index < t], float(p)) for t, p in zip(dates, px)])
    r = LR.returns(days, bo, bl, '15:59', 15)
    nights = np.array([d[4] for d in days], float)
    pnl1x = r - LR.FUND * nights                      # per unit notional, if traded
    size = sig * np.where(below, DS.TREND_BELOW_MULT, 1.0)

    # parity: bot decision code with only the last 7 days of 1-min data
    raw = pd.read_sql_query(f'SELECT * FROM {epic}_cap_1min ORDER BY timestamp', sqlite3.connect(DB))
    raw['t'] = pd.to_datetime(raw['timestamp'])
    tarr = raw['t'].to_numpy()
    agree = n = 0
    for k, t in enumerate(m5['t'].to_numpy()[idx]):
        t = pd.Timestamp(t)
        lo = np.searchsorted(tarr, np.datetime64(t - pd.Timedelta(days=12)))   # bot prefetch window
        hi = np.searchsorted(tarr, np.datetime64(t + pd.Timedelta(minutes=4)))
        live5 = DS.build_5min(raw.iloc[lo:hi])
        if live5.empty or live5['t'].iloc[-1] != t or len(live5) < DS.MIN_HISTORY_BARS:
            continue
        n += 1
        agree += DS.decide(live5).buy == bool(sig[k])
    print(f'{epic}: {len(days)} days, {int(sig.sum())} BUY signals ({int((sig & below).sum())} below 200-day avg) | '
          f'bot decision parity {agree}/{n}')
    return pd.DataFrame({f'size_{epic}': size, f'pnl_{epic}': pnl1x}, index=dates)


def simulate(df, epics, budget, brake=None):
    eq, peak, cool, out = 1.0, 1.0, 0, []
    S = df[[f'size_{e}' for e in epics]].fillna(0).to_numpy()
    P = df[[f'pnl_{e}' for e in epics]].fillna(0).to_numpy()
    for t in range(len(df)):
        on = S[t] > 0
        r = 0.0
        if on.any() and cool == 0:
            L = np.where(on, budget / on.sum(), 0.0) * S[t]
            r = float(L @ P[t])
        elif cool > 0:
            cool -= 1
        eq *= max(1 + 0.95 * r, 0.0)          # 95% of equity deployed, as the bot does
        peak = max(peak, eq)
        if brake and eq / peak - 1 < -brake:
            cool, peak = 20, eq
        out.append(eq)
    return pd.Series(out, index=df.index)


def main():
    epics = sys.argv[1:] or ['SOXL', 'TQQQ']
    df = pd.concat([market(e) for e in epics], axis=1).sort_index()
    yrs = (df.index[-1] - df.index[0]).days / 365.25
    print()
    for combo in [[e] for e in epics] + [epics]:
        for budget in (2, 3, 4):
            for brake in (None, 0.2):
                eq = simulate(df, combo, budget, brake)
                dd = (eq / eq.cummax() - 1).min()
                ye = eq.groupby(eq.index.year).last()
                yearly = ye / ye.shift(1).fillna(1.0)
                print(f'{"+".join(combo):10s} budget {budget}x brake {"20%" if brake else "off"}: '
                      f'{eq.iloc[-1]:7.1f}x ({eq.iloc[-1] ** (1 / yrs) - 1:+.0%}/yr) maxDD {dd:.0%} | '
                      + ' '.join(f'{y}:{v:.2f}x' for y, v in yearly.items()))
        print()
    df.to_pickle('/tmp/claude-0/exact_portfolio.pkl')


if __name__ == '__main__':
    main()
