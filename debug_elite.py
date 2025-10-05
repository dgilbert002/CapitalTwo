#!/usr/bin/env python3
"""Debug version to match elite model exactly"""

import os
import sys
from datetime import time as dt_time
import pandas as pd

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Scripts.db_utils import load_epic_df, load_settings

ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

# Elite model exact strategies
STRATEGIES = {
    'rsi_oversold': {
        'leverage': 10.0, 'period': 7, 'stop_loss_pct': 3.5, 'threshold': 25,
        'win_rate': 80.0
    },
    'bb_lower_break': {
        'leverage': 10.0, 'period': 20, 'std_dev': 2.5, 'stop_loss_pct': 3.5,
        'win_rate': 80.0
    },
    'rsi_bullish_cross_50': {
        'leverage': 5.0, 'period': 7, 'stop_loss_pct': 10.0,
        'win_rate': 63.0
    },
    'price_above_vwap': {
        'leverage': 4.0, 'threshold': -0.01, 'stop_loss_pct': 8.0,
        'win_rate': 0.0
    },
    'roc_below_threshold': {
        'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5, 'threshold': -5,
        'win_rate': 0.0
    },
    'macd_positive': {
        'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 
        'threshold': 0.05, 'stop_loss_pct': 4.0,
        'win_rate': 0.0
    }
}

def load_data():
    """Load data exactly like elite model"""
    ROOT = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(ROOT, 'settings.txt')
    settings = load_settings(settings_path)
    
    df = load_epic_df('database_av.db', 'TECL')
    if 'snapshotTime' not in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    
    start = pd.to_datetime('2024-01-01')
    end = pd.to_datetime('2025-10-03') + pd.Timedelta(days=1)
    df = df[(df['snapshotTime'] >= start) & (df['snapshotTime'] < end)]
    
    return df.sort_values('snapshotTime').reset_index(drop=True)

def eval_signals(hist):
    """Evaluate signals exactly like elite model"""
    lib_today = create_indicator_library(hist)
    conds = lib_today.get_conditions()
    idx = len(hist) - 1
    fired = {}
    
    # Check each signal
    for signal in STRATEGIES.keys():
        fired[signal] = False
        if signal in conds:
            try:
                params = STRATEGIES[signal]
                if signal == 'rsi_oversold':
                    fired[signal] = conds[signal](hist, idx, params['period'], params['threshold'])
                elif signal == 'rsi_bullish_cross_50':
                    fired[signal] = conds[signal](hist, idx, params['period'])
                elif signal == 'bb_lower_break':
                    fired[signal] = conds[signal](hist, idx, params['period'], params['std_dev'])
                elif signal == 'price_above_vwap':
                    fired[signal] = conds[signal](hist, idx, params['threshold'])
                elif signal == 'roc_below_threshold':
                    fired[signal] = conds[signal](hist, idx, params['period'], params.get('threshold', -5))
                elif signal == 'macd_positive':
                    fired[signal] = conds[signal](hist, idx, params['fast_period'], 
                                                  params['slow_period'], params['signal_period'], 
                                                  params['threshold'])
            except Exception:
                pass
    
    return fired

def select_best_signal(fired_signals):
    """Select best signal by win_rate priority"""
    fired_list = [s for s, v in fired_signals.items() if v]
    if not fired_list:
        return None, None
    
    best_signal = max(fired_list, key=lambda s: STRATEGIES[s]['win_rate'])
    return best_signal, STRATEGIES[best_signal]

def run_strategy(df):
    """Run strategy exactly like elite Test1.py"""
    ROOT = os.path.dirname(os.path.abspath(__file__))
    settings = load_settings(os.path.join(ROOT, 'settings.txt'))
    
    # Use exact same defaults as elite
    start_balance = float(settings.get('start_balance', 100.0))
    invest_pct = float(settings.get('invest_pct', 0.99))
    monthly_top_up = float(settings.get('monthly_top_up', 0.0))
    
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
    
    balance = start_balance
    current_position = None
    trades = []
    trade_count = 0
    
    # Monthly contribution logic
    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]
    
    print(f"Starting balance: ${start_balance}")
    print(f"Monthly top-up: ${monthly_top_up}")
    print(f"Investment %: {invest_pct * 100}%")
    print("\nFirst 5 trades:")
    print("-" * 80)
    
    for current_date in trading_days:
        # Monthly top-up
        if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
            old_balance = balance
            balance += monthly_top_up
            if trade_count < 5:
                print(f"{current_date}: Monthly top-up ${monthly_top_up:.2f} (${old_balance:.2f} -> ${balance:.2f})")
        
        day_candles = df[df['date'] == current_date].copy()
        if day_candles.empty:
            continue
        day_candles = day_candles.sort_values('snapshotTime').reset_index(drop=True)
        
        # Exit position
        if current_position is not None:
            sl_pct = current_position['stop_loss_pct']
            stop_price = current_position['entry_price'] * (1 - sl_pct / 100)
            stop_hit = False
            
            # Check stop loss
            for _, c in day_candles.iterrows():
                if c['lowPrice'] <= stop_price:
                    stop_hit = True
                    exit_price = stop_price
                    break
            
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice')
                if exit_price is None:
                    exit_price = current_position['entry_price']
            
            # Calculate P&L
            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross_pnl = current_position['notional_value'] * price_change_pct
            fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
            net_pnl = gross_pnl - fees
            old_balance = balance
            balance += net_pnl
            
            if trade_count < 5:
                print(f"\nTrade #{trade_count + 1} EXIT:")
                print(f"  Date: {current_date}")
                print(f"  Exit Price: ${exit_price:.4f}")
                print(f"  Price Change: {price_change_pct:.4%}")
                print(f"  Gross P&L: ${gross_pnl:.2f}")
                print(f"  Fees: ${fees:.2f}")
                print(f"  Net P&L: ${net_pnl:.2f}")
                print(f"  Balance: ${old_balance:.2f} -> ${balance:.2f}")
            
            trades.append({
                'exit_date': current_date,
                'pnl_net': net_pnl,
                'balance_after': balance
            })
            trade_count += 1
            current_position = None
        
        # Check for entry
        hist = df[df['date'] <= current_date]
        if hist.empty:
            continue
        
        fired = eval_signals(hist)
        best_signal, signal_config = select_best_signal(fired)
        
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if best_signal is None or entry_price is None or balance <= 0 or current_position is not None:
            continue
        
        leverage = signal_config['leverage']
        stop_loss_pct = signal_config['stop_loss_pct']
        notional_value = balance * invest_pct * leverage
        
        if trade_count < 5:
            print(f"\nTrade #{trade_count + 1} ENTRY:")
            print(f"  Date: {current_date}")
            print(f"  Signal: {best_signal}")
            print(f"  Entry Price: ${entry_price:.4f}")
            print(f"  Balance: ${balance:.2f}")
            print(f"  Investment: ${balance * invest_pct:.2f}")
            print(f"  Leverage: {leverage}x")
            print(f"  Notional: ${notional_value:.2f}")
            print(f"  Stop Loss: {stop_loss_pct}%")
        
        current_position = {
            'entry_date': current_date,
            'entry_price': entry_price,
            'notional_value': notional_value,
            'leverage': leverage,
            'stop_loss_pct': stop_loss_pct,
            'selected_signal': best_signal,
        }
        
        # Check same-day stop
        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME) & (day_candles['time'] <= dt_time(20, 0))]
        if not after_hours.empty:
            sl_same_day = entry_price * (1 - stop_loss_pct / 100)
            for _, c in after_hours.iterrows():
                if c['lowPrice'] <= sl_same_day:
                    exit_price = sl_same_day
                    price_change_pct = (exit_price - entry_price) / entry_price
                    gross_pnl = notional_value * price_change_pct
                    fees = calculate_trading_costs(notional_value, 'long', is_overnight=False)
                    net_pnl = gross_pnl - fees
                    old_balance = balance
                    balance += net_pnl
                    
                    if trade_count < 5:
                        print(f"  SAME-DAY STOP HIT!")
                        print(f"  Exit Price: ${exit_price:.4f}")
                        print(f"  Net P&L: ${net_pnl:.2f}")
                        print(f"  Balance: ${old_balance:.2f} -> ${balance:.2f}")
                    
                    trades.append({
                        'exit_date': current_date,
                        'pnl_net': net_pnl,
                        'balance_after': balance
                    })
                    trade_count += 1
                    current_position = None
                    break
    
    print(f"\n{'=' * 80}")
    print(f"FINAL BALANCE: ${balance:.2f}")
    print(f"TOTAL TRADES: {len(trades)}")
    return balance

if __name__ == '__main__':
    print("DEBUGGING ELITE MODEL REPLICATION")
    print("=" * 80)
    
    df = load_data()
    print(f"Loaded {len(df):,} candles\n")
    
    final_balance = run_strategy(df)
    
    print(f"\nTarget (Elite Test1.py): $303,567")
    print(f"Difference: ${303567 - final_balance:.2f}")
