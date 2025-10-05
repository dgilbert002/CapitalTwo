#!/usr/bin/env python3
"""Compare our execution with elite model trade by trade"""

import pandas as pd
import os
import sys
from datetime import time as dt_time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Scripts.db_utils import load_epic_df, load_settings

ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

STRATEGIES = {
    'rsi_oversold': {'leverage': 10.0, 'period': 7, 'stop_loss_pct': 3.5, 'threshold': 25, 'win_rate': 80.0},
    'bb_lower_break': {'leverage': 10.0, 'period': 20, 'std_dev': 2.5, 'stop_loss_pct': 3.5, 'win_rate': 80.0},
    'rsi_bullish_cross_50': {'leverage': 5.0, 'period': 7, 'stop_loss_pct': 10.0, 'win_rate': 63.0},
    'price_above_vwap': {'leverage': 4.0, 'threshold': -0.01, 'stop_loss_pct': 8.0, 'win_rate': 0.0},
    'roc_below_threshold': {'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5, 'threshold': -5, 'win_rate': 0.0},
    'macd_positive': {'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 'threshold': 0.05, 'stop_loss_pct': 4.0, 'win_rate': 0.0}
}

def load_data():
    df = load_epic_df('database_av.db', 'TECL')
    if 'snapshotTime' not in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    start = pd.to_datetime('2024-01-01')
    end = pd.to_datetime('2025-10-03') + pd.Timedelta(days=1)
    df = df[(df['snapshotTime'] >= start) & (df['snapshotTime'] < end)]
    return df.sort_values('snapshotTime').reset_index(drop=True)

def eval_signals(hist):
    lib_today = create_indicator_library(hist)
    conds = lib_today.get_conditions()
    idx = len(hist) - 1
    fired = {}
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
                    fired[signal] = conds[signal](hist, idx, params['fast_period'], params['slow_period'], params['signal_period'], params['threshold'])
            except:
                pass
    return fired

def select_best_signal(fired_signals):
    fired_list = [s for s, v in fired_signals.items() if v]
    if not fired_list:
        return None, None
    best_signal = max(fired_list, key=lambda s: STRATEGIES[s]['win_rate'])
    return best_signal, STRATEGIES[best_signal]

# Load elite model trades
elite_trades = pd.read_csv('Results/test1_trades__TECL.csv')
print(f"Loaded {len(elite_trades)} elite trades")
print(f"Elite final balance: ${elite_trades.iloc[-1]['balance_after']:.2f}")

# Run our strategy
df = load_data()
settings = load_settings('settings.txt')

start_balance = float(settings.get('start_balance', 100.0))
invest_pct = float(settings.get('invest_pct', 0.99))
monthly_top_up = float(settings.get('monthly_top_up', 0.0))

all_dates = sorted(df['date'].unique())
trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]

balance = start_balance
current_position = None
our_trades = []

monthly_groups = {}
for d in trading_days:
    monthly_groups.setdefault((d.year, d.month), []).append(d)
contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]

print(f"\nStarting balance: ${start_balance}")
print(f"Monthly top-up: ${monthly_top_up}")
print(f"Investment %: {invest_pct * 100}%")

divergence_found = False
trade_idx = 0

for current_date in trading_days:
    # Monthly top-up
    if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
        old_balance = balance
        balance += monthly_top_up
    
    day_candles = df[df['date'] == current_date].copy()
    if day_candles.empty:
        continue
    day_candles = day_candles.sort_values('snapshotTime').reset_index(drop=True)
    
    # Exit position
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
            exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice')
            if exit_price is None:
                exit_price = current_position['entry_price']
        
        price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
        gross_pnl = current_position['notional_value'] * price_change_pct
        fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
        net_pnl = gross_pnl - fees
        balance += net_pnl
        
        our_trades.append({
            'entry_date': current_position['entry_date'],
            'exit_date': current_date,
            'entry_price': current_position['entry_price'],
            'exit_price': exit_price,
            'selected_signal': current_position['selected_signal'],
            'leverage': current_position['leverage'],
            'pnl_net': net_pnl,
            'balance_after': balance
        })
        
        # Compare with elite trade
        if trade_idx < len(elite_trades):
            elite_trade = elite_trades.iloc[trade_idx]
            our_trade = our_trades[-1]
            
            # Check for divergence
            if abs(our_trade['balance_after'] - elite_trade['balance_after']) > 1.0:
                if not divergence_found:
                    print(f"\n{'='*60}")
                    print(f"DIVERGENCE FOUND at trade #{trade_idx + 1}!")
                    print(f"\nElite trade #{trade_idx + 1}:")
                    print(f"  Entry: {elite_trade['entry_date']} @ ${elite_trade['entry_price']:.2f}")
                    print(f"  Exit: {elite_trade['exit_date']} @ ${elite_trade['exit_price']:.2f}")
                    print(f"  Signal: {elite_trade['selected_signal']}")
                    print(f"  Leverage: {elite_trade['leverage']:.1f}x")
                    print(f"  P&L: ${elite_trade['pnl_net']:.2f}")
                    print(f"  Balance: ${elite_trade['balance_after']:.2f}")
                    
                    print(f"\nOur trade #{trade_idx + 1}:")
                    print(f"  Entry: {our_trade['entry_date']} @ ${our_trade['entry_price']:.2f}")
                    print(f"  Exit: {our_trade['exit_date']} @ ${our_trade['exit_price']:.2f}")
                    print(f"  Signal: {our_trade['selected_signal']}")
                    print(f"  Leverage: {our_trade['leverage']:.1f}x")
                    print(f"  P&L: ${our_trade['pnl_net']:.2f}")
                    print(f"  Balance: ${our_trade['balance_after']:.2f}")
                    
                    print(f"\nDifference: ${elite_trade['balance_after'] - our_trade['balance_after']:.2f}")
                    
                    # Check previous trades
                    if trade_idx > 0:
                        print(f"\nPrevious trade (#{trade_idx}):")
                        prev_elite = elite_trades.iloc[trade_idx - 1]
                        prev_our = our_trades[-2] if len(our_trades) > 1 else None
                        print(f"  Elite balance: ${prev_elite['balance_after']:.2f}")
                        if prev_our:
                            print(f"  Our balance: ${prev_our['balance_after']:.2f}")
                    
                    divergence_found = True
                    break
        
        trade_idx += 1
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
                balance += net_pnl
                
                our_trades.append({
                    'entry_date': current_date,
                    'exit_date': current_date,
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'selected_signal': best_signal,
                    'leverage': leverage,
                    'pnl_net': net_pnl,
                    'balance_after': balance
                })
                
                # Compare with elite
                if trade_idx < len(elite_trades):
                    elite_trade = elite_trades.iloc[trade_idx]
                    our_trade = our_trades[-1]
                    
                    if abs(our_trade['balance_after'] - elite_trade['balance_after']) > 1.0:
                        if not divergence_found:
                            print(f"\n{'='*60}")
                            print(f"DIVERGENCE FOUND at trade #{trade_idx + 1} (same-day stop)!")
                            print(f"\nElite trade #{trade_idx + 1}:")
                            print(f"  Date: {elite_trade['entry_date']}")
                            print(f"  Signal: {elite_trade['selected_signal']}")
                            print(f"  Balance: ${elite_trade['balance_after']:.2f}")
                            
                            print(f"\nOur trade #{trade_idx + 1}:")
                            print(f"  Date: {our_trade['entry_date']}")
                            print(f"  Signal: {our_trade['selected_signal']}")
                            print(f"  Balance: ${our_trade['balance_after']:.2f}")
                            
                            print(f"\nDifference: ${elite_trade['balance_after'] - our_trade['balance_after']:.2f}")
                            divergence_found = True
                            break
                
                trade_idx += 1
                current_position = None
                break
    
    if divergence_found:
        break

if not divergence_found:
    print(f"\n{'='*60}")
    print(f"Final comparison:")
    print(f"Our trades: {len(our_trades)}")
    print(f"Elite trades: {len(elite_trades)}")
    print(f"Our final balance: ${balance:.2f}")
    print(f"Elite final balance: ${elite_trades.iloc[-1]['balance_after']:.2f}")
    print(f"Difference: ${elite_trades.iloc[-1]['balance_after'] - balance:.2f}")
