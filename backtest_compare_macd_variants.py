#!/usr/bin/env python3
"""
Backtest comparator for MACD histogram negative variants (v1 vs v2) using Alpha Vantage data.

Respects settings.txt:
  [ALPHA_VANTAGE] database, table_name
  [TESTING] start_date, end_date
  [BOT_CONFIG] entry/exit defaults implied by proven system

Simulation rules (proven system simplified):
  - Entry: 15:59:45 (ENTRY_TIME)
  - Exit:  15:59:30 next day or Stop Loss if hit
  - Position sizing: invest_pct (default 0.99) * balance * leverage
  - Add only net P&L on exit (no capital lockup subtraction on entry)
  - Monthly top-up: +$100 on first trading day of the month (if configured)

Outputs final balances for both variants for quick comparison.
"""

import os
import sqlite3
from datetime import datetime, time as dt_time
from typing import Dict, Tuple

import pandas as pd

from bot.settings import TradingBotSettings
from focused_optimizer import calculate_trading_costs, get_price_at_time
from Brains.strategy_signals import (
    check_macd_histogram_negative,
    ENTRY_TIME,
    EXIT_TIME,
)


VARIANT_V1 = {
    'name': 'macd_histogram_negative',
    'fast_period': 8,
    'slow_period': 18,
    'signal_period': 4,
    'threshold': -0.05,
    'leverage': 5.0,
    'stop_loss_pct': 4.0,
}

VARIANT_V2 = {
    'name': 'macd_histogram_negative_v2',
    'fast_period': 5,
    'slow_period': 18,
    'signal_period': 4,
    'threshold': -0.10,
    'leverage': 5.0,
    'stop_loss_pct': 5.5,
}


def load_av_df(settings: TradingBotSettings) -> pd.DataFrame:
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
    start_date = settings.get('TESTING', 'start_date', '')
    end_date = settings.get('TESTING', 'end_date', '')

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()

    # Normalize timestamps and helper columns
    if 'timestamp' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    elif 'snapshotTime' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['snapshotTime'])
    else:
        raise RuntimeError('No timestamp column found')

    # Ensure required price/volume columns
    rename = {}
    if 'open' in df.columns: rename['open'] = 'openPrice'
    if 'high' in df.columns: rename['high'] = 'highPrice'
    if 'low' in df.columns: rename['low'] = 'lowPrice'
    if 'close' in df.columns: rename['close'] = 'closePrice'
    if 'volume' in df.columns: rename['volume'] = 'lastTradedVolume'
    if rename:
        df.rename(columns=rename, inplace=True)

    df['date'] = df['snapshotTime'].dt.date
    df['time'] = df['snapshotTime'].dt.time
    df = df.sort_values('snapshotTime').reset_index(drop=True)

    # Date filter
    if start_date:
        df = df[df['snapshotTime'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['snapshotTime'] < (pd.to_datetime(end_date) + pd.Timedelta(days=1))]

    return df


def run_variant(df: pd.DataFrame, variant: Dict, invest_pct: float = 0.99,
                start_balance: float = 500.0, monthly_top_up: float = 100.0) -> Tuple[float, int]:
    """Run simplified backtest using only the given MACD histogram negative variant.
    Returns (final_balance, trades_count).
    """
    # Prepare trading days (weekdays only)
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]

    balance = start_balance
    trades = 0

    # Monthly contributions: first trading day of month (>= 10 trading days heuristic omitted)
    month_firsts = {}
    for d in trading_days:
        month_firsts.setdefault((pd.Timestamp(d).year, pd.Timestamp(d).month), d)

    for current_date in trading_days:
        # Monthly top-up
        if month_firsts.get((pd.Timestamp(current_date).year, pd.Timestamp(current_date).month)) == current_date and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up

        day_candles = df[df['date'] == current_date].copy().sort_values('snapshotTime')
        if day_candles.empty:
            continue

        # Decide if the variant fires today using historical up to date
        hist = df[df['date'] <= current_date]
        if hist.empty:
            continue

        try:
            fired = check_macd_histogram_negative(
                hist, len(hist) - 1,
                fast=variant['fast_period'], slow=variant['slow_period'],
                signal_period=variant['signal_period'], threshold=variant['threshold']
            )
        except Exception:
            fired = False

        if not fired or balance <= 0:
            continue

        # Entry at ENTRY_TIME
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if entry_price is None:
            continue

        leverage = variant['leverage']
        sl_pct = variant['stop_loss_pct']
        notional = balance * invest_pct * leverage
        trades += 1

        # Same-day after-hours stop loss until 20:00
        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME) & (day_candles['time'] <= dt_time(20, 0))]
        exited = False
        if not after_hours.empty:
            sl_level = entry_price * (1 - sl_pct / 100)
            for _, c in after_hours.iterrows():
                if c['lowPrice'] <= sl_level:
                    change = (sl_level - entry_price) / entry_price
                    gross = notional * change
                    fees = calculate_trading_costs(notional, 'long', is_overnight=False)
                    balance += (gross - fees)
                    exited = True
                    break

        if exited:
            continue

        # Next day exit at EXIT_TIME
        next_idx = trading_days.index(current_date) + 1
        if next_idx >= len(trading_days):
            continue
        next_date = trading_days[next_idx]
        next_day = df[df['date'] == next_date].copy().sort_values('snapshotTime')
        exit_price = get_price_at_time(next_day, EXIT_TIME, 'closePrice')
        if exit_price is None:
            exit_price = entry_price
        change = (exit_price - entry_price) / entry_price
        gross = notional * change
        fees = calculate_trading_costs(notional, 'long', is_overnight=True)
        balance += (gross - fees)

    return balance if balance > 0 else 0.0, trades


def main():
    settings = TradingBotSettings('settings.txt')
    # Inputs from settings
    start_balance = float(settings.get('STRATEGY', 'start_balance', '500.0')) if settings.has_section('STRATEGY') else 500.0
    invest_pct = float(settings.get('STRATEGY', 'invest_pct', '0.99')) if settings.has_section('STRATEGY') else 0.99
    monthly_top_up = float(settings.get('STRATEGY', 'monthly_top_up', '100.0')) if settings.has_section('STRATEGY') else 100.0

    df = load_av_df(settings)
    print(f"Loaded {len(df):,} candles")

    v1_balance, v1_trades = run_variant(df, VARIANT_V1, invest_pct, start_balance, monthly_top_up)
    v2_balance, v2_trades = run_variant(df, VARIANT_V2, invest_pct, start_balance, monthly_top_up)

    print("\nMACD Histogram Negative Variants Comparison")
    print("=========================================")
    print(f"V1 (fast=8, thr=-0.05, SL=4.0):  ${v1_balance:,.0f}  | trades={v1_trades}")
    print(f"V2 (fast=5, thr=-0.10, SL=5.5): ${v2_balance:,.0f}  | trades={v2_trades}")
    diff = v2_balance - v1_balance
    print(f"\nDelta: ${diff:,.0f} ({'improvement' if diff>0 else 'worse' if diff<0 else 'same'})")


if __name__ == '__main__':
    main()


