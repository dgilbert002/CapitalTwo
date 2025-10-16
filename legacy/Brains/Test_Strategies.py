#!/usr/bin/env python3
"""
Test_Strategies.py

Runs a quick, proven-style backtest across strategy modes and prints results.
Respects settings.txt:
  [ALPHA_VANTAGE] database, table_name
  [TESTING] start_date, end_date
  [STRATEGY] start_balance, invest_pct, monthly_top_up

Strategy modes evaluated:
  - all_signals (with/without crash protection)
  - two_rsi_only (with/without)
  - test6 (with/without)
  - test7 (with/without)  # Test6 + MACD histogram v2 (9 signals)

This uses the same entry/exit/stop-loss accounting as the proven system:
  - Entry at 15:59:45 (ENTRY_TIME)
  - Exit at 15:59:30 next trading day (EXIT_TIME), unless same-day stop-loss hit
  - Position sizing: notional = balance * invest_pct * leverage
  - Only net P&L is added to balance at exit (no capital subtraction at entry)
  - Monthly top-up of +$100 by default on first trading day of the month
"""

import os
import sys
import sqlite3
from datetime import datetime, time as dt_time
from typing import Dict, List, Tuple

import pandas as pd

# Ensure project root on sys.path so 'bot' and 'Brains' imports always work
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from bot.settings import TradingBotSettings
from focused_optimizer import calculate_trading_costs, get_price_at_time
from Brains.strategy_signals import (
    get_strategy_analysis,
    ENTRY_TIME,
    EXIT_TIME,
)


def load_av_df(settings: TradingBotSettings) -> pd.DataFrame:
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
    start_date = settings.get('TESTING', 'start_date', '')
    end_date = settings.get('TESTING', 'end_date', '')

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(f"SELECT * FROM {table}", conn)
    conn.close()

    if 'timestamp' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    elif 'snapshotTime' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['snapshotTime'])
    else:
        raise RuntimeError('No timestamp column found in table: ' + table)

    # Normalize column names used by strategy code
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

    if start_date:
        df = df[df['snapshotTime'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['snapshotTime'] < (pd.to_datetime(end_date) + pd.Timedelta(days=1))]
    return df


def run_mode(df: pd.DataFrame, mode: str, crash_protection: bool,
             invest_pct: float = 0.99, start_balance: float = 500.0, monthly_top_up: float = 100.0) -> Dict:
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]

    balance = start_balance
    current_position = None
    trades: List[Dict] = []

    # First trading day of each month
    month_firsts: Dict[Tuple[int,int], object] = {}
    for d in trading_days:
        month_firsts.setdefault((pd.Timestamp(d).year, pd.Timestamp(d).month), d)

    for current_date in trading_days:
        # Monthly top-up
        if month_firsts.get((pd.Timestamp(current_date).year, pd.Timestamp(current_date).month)) == current_date and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up

        day_candles = df[df['date'] == current_date].copy().sort_values('snapshotTime')
        if day_candles.empty:
            continue

        # Close prior position per proven accounting
        if current_position is not None:
            sl_pct = current_position['stop_loss_pct']
            stop_price = current_position['entry_price'] * (1 - sl_pct / 100)
            stop_hit = False
            for _, c in day_candles.iterrows():
                if c['lowPrice'] <= stop_price:
                    stop_hit = True
                    exit_price = stop_price
                    break
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice') or current_position['entry_price']
            change = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross = current_position['notional'] * change
            fees = calculate_trading_costs(current_position['notional'], 'long', is_overnight=True)
            balance += (gross - fees)
            trades.append({'date': current_date, 'pnl': gross - fees})
            current_position = None

        # Analyze for entry
        analysis = get_strategy_analysis(df[df['date'] <= current_date], strategy_mode=mode,
                                         enable_crash_protection=crash_protection, current_date=current_date)
        if analysis.get('trade_signal') != 'buy' or balance <= 0:
            continue

        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if entry_price is None:
            continue
        leverage = analysis.get('strategy_leverage', 1)
        stop_loss_pct = analysis.get('strategy_stop_loss', 4.0)
        notional = balance * invest_pct * leverage
        current_position = {
            'entry_price': entry_price,
            'notional': notional,
            'stop_loss_pct': stop_loss_pct,
        }

        # Same-day after-hours stop
        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME) & (day_candles['time'] <= dt_time(20, 0))]
        if not after_hours.empty:
            sl_level = entry_price * (1 - stop_loss_pct / 100)
            for _, c in after_hours.iterrows():
                if c['lowPrice'] <= sl_level:
                    change = (sl_level - entry_price) / entry_price
                    gross = notional * change
                    fees = calculate_trading_costs(notional, 'long', is_overnight=False)
                    balance += (gross - fees)
                    trades.append({'date': current_date, 'pnl': gross - fees})
                    current_position = None
                    break

    # If a position remains open at the very end, ignore (no next-day exit)
    final_balance = balance if balance > 0 else 0.0
    wins = sum(1 for t in trades if t['pnl'] > 0)
    losses = sum(1 for t in trades if t['pnl'] <= 0)
    return {
        'final_balance': final_balance,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
    }


def main():
    s = TradingBotSettings('settings.txt')
    df = load_av_df(s)
    # Use FINANCE section like the elite scripts do
    start_balance = float(s.get('FINANCE','start_balance','500.0')) if s.has_section('FINANCE') else 500.0
    invest_pct = float(s.get('FINANCE','invest_pct','0.99')) if s.has_section('FINANCE') else 0.99
    monthly_top_up = float(s.get('FINANCE','monthly_top_up','100.0')) if s.has_section('FINANCE') else 100.0

    tests = [
        ('all_signals', True,  'All 6 Signals WITH Protection'),
        ('all_signals', False, 'All 6 Signals NO Protection'),
        ('two_rsi_only', True,  'Two RSI WITH Protection'),
        ('two_rsi_only', False, 'Two RSI NO Protection'),
        ('test6', True,  'Test6 - 8 Signals WITH Protection'),
        ('test6', False, 'Test6 - 8 Signals NO Protection'),
        ('test7', True,  'Test7 - 9 Signals WITH Protection'),
        ('test7', False, 'Test7 - 9 Signals NO Protection'),
    ]

    print(f"Loaded {len(df):,} candles\n")
    print("Strategy Backtest Summary")
    print("==========================")
    for mode, cp, label in tests:
        res = run_mode(df, mode, cp, invest_pct, start_balance, monthly_top_up)
        print(f"{label:<40}  ${res['final_balance']:>12,.0f}  | trades={res['trades']}, W/L={res['wins']}/{res['losses']}")


if __name__ == '__main__':
    main()


