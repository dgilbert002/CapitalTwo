import pandas as pd
import os
import sys
from datetime import time as dt_time, date

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
    ROOT = os.path.dirname(os.path.abspath(__file__))
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
            except Exception as e:
                pass
    return fired

print("Checking September 2025 trades...")
df = load_data()

# Check specific dates
check_dates = [
    date(2025, 9, 9),   # Elite gets +$40k here
    date(2025, 9, 17),  # Elite gets +$55k here
    date(2025, 9, 18),  # Elite gets +$55k here
]

for check_date in check_dates:
    print(f"\n{'='*60}")
    print(f"Date: {check_date}")
    
    # Get historical data up to this date
    hist = df[df['date'] <= check_date]
    if hist.empty:
        print("No historical data")
        continue
    
    # Check signals
    fired = eval_signals(hist)
    print(f"Signals fired:")
    for signal, is_fired in fired.items():
        if is_fired:
            print(f"  ✓ {signal} (leverage: {STRATEGIES[signal]['leverage']}x)")
    
    # Get day candles
    day_candles = df[df['date'] == check_date]
    if not day_candles.empty:
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        print(f"Entry price (15:59:45): ${entry_price:.2f}" if entry_price else "No entry price")
        
        # Check next day exit
        next_day_idx = df[df['date'] > check_date].index.min()
        if pd.notna(next_day_idx):
            next_date = df.loc[next_day_idx, 'date']
            next_day_candles = df[df['date'] == next_date]
            exit_price = get_price_at_time(next_day_candles, EXIT_TIME, 'closePrice')
            if entry_price and exit_price:
                price_change = (exit_price - entry_price) / entry_price
                print(f"Exit price (next day 15:59:30): ${exit_price:.2f}")
                print(f"Price change: {price_change:.2%}")
                
                # If rsi_oversold fired, calculate potential P&L
                if fired.get('rsi_oversold'):
                    # Assuming $77k balance like elite had before trade 392
                    balance = 77793
                    notional = balance * 0.99 * 10  # 10x leverage
                    gross_pnl = notional * price_change
                    fees = calculate_trading_costs(notional, 'long', True)
                    net_pnl = gross_pnl - fees
                    print(f"Potential P&L with 10x leverage on ${balance:.0f}:")
                    print(f"  Notional: ${notional:.0f}")
                    print(f"  Gross P&L: ${gross_pnl:.2f}")
                    print(f"  Net P&L: ${net_pnl:.2f}")
