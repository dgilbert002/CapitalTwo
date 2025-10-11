#!/usr/bin/env python3
"""
Compare Test6 vs Test7 (9 signals) with/without crash protection using Alpha Vantage data.
Respects settings.txt for data/source and date range.
"""

import os
import sqlite3
from datetime import datetime
import pandas as pd

from bot.settings import TradingBotSettings
from Brains.strategy_signals import get_strategy_analysis, ENTRY_TIME, EXIT_TIME
from focused_optimizer import calculate_trading_costs, get_price_at_time


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
    df['date'] = df['snapshotTime'].dt.date
    df['time'] = df['snapshotTime'].dt.time
    df.rename(columns={'open':'openPrice','high':'highPrice','low':'lowPrice','close':'closePrice','volume':'lastTradedVolume'}, inplace=True, errors='ignore')
    df = df.sort_values('snapshotTime').reset_index(drop=True)
    if start_date:
        df = df[df['snapshotTime'] >= pd.to_datetime(start_date)]
    if end_date:
        df = df[df['snapshotTime'] < (pd.to_datetime(end_date) + pd.Timedelta(days=1))]
    return df


def run_mode(df: pd.DataFrame, mode: str, crash_protection: bool, invest_pct=0.99, start_balance=500.0, monthly_top_up=100.0) -> float:
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
    balance = start_balance
    current_position = None

    # first trading day per month
    month_firsts = {}
    for d in trading_days:
        month_firsts.setdefault((pd.Timestamp(d).year, pd.Timestamp(d).month), d)

    for current_date in trading_days:
        if month_firsts.get((pd.Timestamp(current_date).year, pd.Timestamp(current_date).month)) == current_date and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up

        day_candles = df[df['date'] == current_date].copy().sort_values('snapshotTime')
        if day_candles.empty:
            continue

        # Close previous position per proven rules
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
                next_idx = trading_days.index(current_date)
                if next_idx < len(trading_days):
                    exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice') or current_position['entry_price']
                else:
                    exit_price = current_position['entry_price']
            change = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross = current_position['notional'] * change
            fees = calculate_trading_costs(current_position['notional'], 'long', is_overnight=True)
            balance += (gross - fees)
            current_position = None

        # Analyze
        analysis = get_strategy_analysis(df[df['date'] <= current_date], strategy_mode=mode, enable_crash_protection=crash_protection, current_date=current_date)
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

    return balance


def main():
    s = TradingBotSettings('settings.txt')
    df = load_av_df(s)
    start_balance = float(s.get('STRATEGY','start_balance','500.0')) if s.has_section('STRATEGY') else 500.0
    invest_pct = float(s.get('STRATEGY','invest_pct','0.99')) if s.has_section('STRATEGY') else 0.99
    monthly_top_up = float(s.get('STRATEGY','monthly_top_up','100.0')) if s.has_section('STRATEGY') else 100.0

    print(f"Loaded {len(df):,} candles")

    print("\nTest6 vs Test7 (WITH Protection)")
    b6 = run_mode(df, 'test6', True, invest_pct, start_balance, monthly_top_up)
    b7 = run_mode(df, 'test7', True, invest_pct, start_balance, monthly_top_up)
    print(f"Test6: ${b6:,.0f} | Test7: ${b7:,.0f} | Delta: ${b7-b6:,.0f}")

    print("\nTest6 vs Test7 (NO Protection)")
    b6n = run_mode(df, 'test6', False, invest_pct, start_balance, monthly_top_up)
    b7n = run_mode(df, 'test7', False, invest_pct, start_balance, monthly_top_up)
    print(f"Test6: ${b6n:,.0f} | Test7: ${b7n:,.0f} | Delta: ${b7n-b6n:,.0f}")


if __name__ == '__main__':
    main()


