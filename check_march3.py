#!/usr/bin/env python3
"""Check what happens on March 3, 2025"""

import pandas as pd
import os
import sys
from datetime import time as dt_time, date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Scripts.db_utils import load_epic_df

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
            except Exception as e:
                print(f"    Error in {signal}: {e}")
    return fired

# Load data
df = load_epic_df('database_av.db', 'TECL')
if 'snapshotTime' not in df.columns:
    df['snapshotTime'] = pd.to_datetime(df['timestamp'])

# Check dates around March 3
check_dates = [
    date(2025, 2, 28),
    date(2025, 3, 3),
    date(2025, 3, 4),
    date(2025, 3, 5),
    date(2025, 3, 6),
]

print("Checking dates around March 3, 2025...")
print("="*60)

for check_date in check_dates:
    print(f"\nDate: {check_date} ({pd.Timestamp(check_date).strftime('%A')})")
    
    # Check if it's a trading day
    if pd.Timestamp(check_date).weekday() >= 5:
        print("  Weekend - no trading")
        continue
    
    # Get day candles
    day_candles = df[df['date'] == check_date]
    if day_candles.empty:
        print("  NO DATA for this date!")
        continue
    
    print(f"  Candles available: {len(day_candles)}")
    
    # Get entry price
    entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
    if entry_price:
        print(f"  Entry price (15:59:45): ${entry_price:.2f}")
    else:
        print(f"  No entry price at 15:59:45")
        # Show what times are available
        times = day_candles['time'].unique()
        close_times = [t for t in times if t.hour == 15 and t.minute >= 55]
        print(f"  Available times near close: {close_times[:5]}")
    
    # Check signals
    hist = df[df['date'] <= check_date]
    if not hist.empty:
        print(f"  Historical data points: {len(hist)}")
        fired = eval_signals(hist)
        print(f"  Signals fired:")
        any_fired = False
        for signal, is_fired in fired.items():
            if is_fired:
                print(f"    ✓ {signal} (win_rate: {STRATEGIES[signal]['win_rate']})")
                any_fired = True
        if not any_fired:
            print(f"    (none)")

# Check elite trade details
print("\n" + "="*60)
print("Elite trade #280 details:")
elite_trades = pd.read_csv('Results/test1_trades__TECL.csv')
trade_280 = elite_trades.iloc[279]  # 0-indexed
print(f"  Entry: {trade_280['entry_date']} @ ${trade_280['entry_price']:.2f}")
print(f"  Exit: {trade_280['exit_date']} @ ${trade_280['exit_price']:.2f}")
print(f"  Signal: {trade_280['selected_signal']}")
print(f"  Leverage: {trade_280['leverage']:.1f}x")
print(f"  P&L: ${trade_280['pnl_net']:.2f}")

# Also check trade 279 to see the context
trade_279 = elite_trades.iloc[278]
print(f"\nElite trade #279 (previous):")
print(f"  Entry: {trade_279['entry_date']} @ ${trade_279['entry_price']:.2f}")
print(f"  Exit: {trade_279['exit_date']} @ ${trade_279['exit_price']:.2f}")
print(f"  Signal: {trade_279['selected_signal']}")
print(f"  Did it exit on March 3? {trade_279['exit_date'] == '2025-03-03'}")
