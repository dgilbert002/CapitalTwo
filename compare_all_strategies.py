"""
Comprehensive Strategy Comparison - Apple to Apple
Uses the exact same data and methodology for all strategies
"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Scripts.db_utils import load_epic_df
from bot.settings import TradingBotSettings
from Brains.strategy_signals import get_strategy_analysis, SIGNAL_CONFIGS
# from Brains.ai_system import AISystem  # Not needed - enhanced mode handled differently
from indicators import *
from focused_optimizer import calculate_trading_costs, get_price_at_time
from datetime import time as dt_time, datetime, timedelta
import pandas as pd
import numpy as np

# Entry/exit times (15 seconds before close, 30 seconds before close next day)
ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

def run_elite_backtest(df, strategy_mode='all_signals', enable_protection=True):
    """Run backtest using elite model methodology"""
    
    # Start with settings
    settings = TradingBotSettings()
    # Use FINANCE section consistently
    balance = float(settings.get('FINANCE', 'start_balance', '500.0'))
    monthly_top_up = float(settings.get('FINANCE', 'monthly_top_up', '100.0'))
    invest_pct = 0.99
    
    trades = []
    current_position = None
    last_month = None
    min_balance = balance
    
    for idx in range(len(df)):
        current_time = df.index[idx]
        
        # Monthly top-up on first trading day
        if last_month != current_time.month:
            if last_month is not None and balance > 0:
                balance += monthly_top_up
            last_month = current_time.month
        
        # Track minimum balance
        min_balance = min(min_balance, balance)
        
        # Exit position check (T-30s)
        if current_position and current_time.time() >= EXIT_TIME:
            entry_price = current_position['entry_price']
            exit_price = df.loc[current_time, 'close']
            
            # Calculate P&L with leverage
            price_change = (exit_price - entry_price) / entry_price
            gross_pnl = current_position['notional_value'] * price_change
            
            # Apply trading costs
            trading_costs = calculate_trading_costs(
                current_position['notional_value'],
                gross_pnl,
                leverage=current_position['leverage']
            )
            net_pnl = gross_pnl - trading_costs
            
            # Update balance - only add net P&L
            balance += net_pnl
            
            trades.append({
                'exit_time': current_time,
                'exit_price': exit_price,
                'pnl': net_pnl,
                'balance': balance
            })
            
            current_position = None
        
        # Entry check (T-15s)
        if not current_position and current_time.time() >= ENTRY_TIME:
            # Get strategy decision
            if strategy_mode == 'enhanced':
                # Skip enhanced for now - it uses different logic path
                continue
            else:
                # Use proven strategy logic
                decision = get_strategy_analysis(
                    df, 
                    strategy_mode=strategy_mode,
                    enable_crash_protection=enable_protection,
                    current_date=current_time
                )
            
            if decision and decision.get('signal') == 'buy':
                investment = balance * invest_pct
                leverage = decision.get('leverage', 5.0)
                notional_value = investment * leverage
                
                current_position = {
                    'entry_time': current_time,
                    'entry_price': df.loc[current_time, 'close'],
                    'investment': investment,
                    'leverage': leverage,
                    'notional_value': notional_value,
                    'stop_loss_pct': decision.get('stop_loss_pct', 5.0),
                    'strategy': decision.get('strategy', 'unknown')
                }
                
                trades.append({
                    'entry_time': current_time,
                    'entry_price': current_position['entry_price'],
                    'investment': investment,
                    'leverage': leverage,
                    'strategy': current_position['strategy']
                })
    
    return {
        'final_balance': balance,
        'total_trades': len([t for t in trades if 'entry_time' in t]),
        'min_balance': min_balance,
        'max_drawdown': ((min_balance - 500) / 500) * 100 if min_balance < 500 else 0
    }

def main():
    print("\n" + "="*80)
    print("APPLE-TO-APPLE STRATEGY COMPARISON")
    print("Using exact same data and methodology for all strategies")
    print("="*80)
    
    # Load data
    settings = TradingBotSettings()
    # Load directly from the correct table
    import sqlite3
    conn = sqlite3.connect('database_av.db')
    df = pd.read_sql_query(
        "SELECT * FROM TECL_av_5min ORDER BY timestamp ASC",
        conn,
        parse_dates=['timestamp'],
        index_col='timestamp'
    )
    conn.close()
    
    # Rename columns for compatibility with strategy code
    column_mapping = {
        'open': 'openPrice',
        'high': 'highPrice', 
        'low': 'lowPrice',
        'close': 'closePrice',
        'volume': 'lastTradedVolume'
    }
    df.rename(columns=column_mapping, inplace=True)
    
    # Also keep the short names for compatibility
    df['open'] = df['openPrice']
    df['high'] = df['highPrice']
    df['low'] = df['lowPrice']
    df['close'] = df['closePrice']
    
    # Add timestamp column from index for compatibility
    df['timestamp'] = df.index
    
    # Filter to test period
    start_date = settings.get('TESTING', 'start_date', '2024-01-01')
    end_date = settings.get('TESTING', 'end_date', '2025-10-03')
    
    df = df[(df.index >= start_date) & (df.index <= end_date)]
    print(f"\nTest Period: {start_date} to {end_date}")
    print(f"Total Candles: {len(df):,}")
    
    # Define all strategies to test
    strategies = [
        ('All 6 Signals WITH Protection', 'all_signals', True),
        ('All 6 Signals NO Protection', 'all_signals', False),
        ('Two RSI WITH Protection', 'two_rsi_only', True),
        ('Two RSI NO Protection', 'two_rsi_only', False),
        ('Test6 - 8 Signals WITH Protection', 'test6', True),
        ('Test6 - 8 Signals NO Protection', 'test6', False),
        ('Test7 - 9 Signals WITH Protection', 'test7', True),
        ('Test7 - 9 Signals NO Protection', 'test7', False),
        # ('Enhanced - Current AI System', 'enhanced', False)  # Skip for now
    ]
    
    results = []
    
    print("\nRunning backtests...")
    print("-"*80)
    
    for name, mode, protection in strategies:
        print(f"Testing: {name}...", end=' ')
        result = run_elite_backtest(df, mode, protection)
        results.append((name, result))
        print(f"${result['final_balance']:,.0f}")
    
    # Print results table
    print("\n" + "="*80)
    print("FINAL RESULTS - APPLE TO APPLE COMPARISON")
    print("="*80)
    print(f"{'Strategy':<45} {'Final Balance':>15} {'Trades':>8} {'Max DD':>8}")
    print("-"*80)
    
    # Sort by final balance
    results.sort(key=lambda x: x[1]['final_balance'], reverse=True)
    
    for name, result in results:
        print(f"{name:<45} ${result['final_balance']:>14,.0f} {result['total_trades']:>8} {result['max_drawdown']:>7.1f}%")
    
    # Highlight winner
    print("\n" + "="*80)
    winner_name, winner_result = results[0]
    print(f"🏆 MOST PROFITABLE: {winner_name}")
    print(f"   Final Balance: ${winner_result['final_balance']:,.0f}")
    print(f"   Return: {((winner_result['final_balance']-500)/500)*100:,.1f}%")
    print("="*80)

if __name__ == "__main__":
    main()
