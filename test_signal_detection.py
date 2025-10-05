#!/usr/bin/env python3
"""
Test signal detection with corrected parameters
"""

import pandas as pd
import sqlite3
from datetime import datetime
from Brains.strategy_signals import (
    SIGNAL_CONFIGS,
    check_bb_lower_break,
    calculate_bollinger_bands
)
from bot.settings import TradingBotSettings
import pytz

# Load settings
settings = TradingBotSettings('settings.txt')
db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
table_name = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')

# Load some data
conn = sqlite3.connect(db_path)
query = f"""
    SELECT timestamp, open, high, low, close, volume 
    FROM {table_name}
    WHERE timestamp >= '2024-01-01' AND timestamp <= '2024-01-31'
    ORDER BY timestamp
    LIMIT 5000
"""

df = pd.read_sql_query(query, conn)
conn.close()

# Prepare data
eastern = pytz.timezone('US/Eastern')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['timestamp'] = df['timestamp'].dt.tz_localize(eastern, ambiguous='NaT')
df['date'] = df['timestamp'].dt.date

# Rename columns
df = df.rename(columns={
    'open': 'openPrice',
    'high': 'highPrice', 
    'low': 'lowPrice',
    'close': 'closePrice',
    'volume': 'lastTradedVolume'
})

print("=" * 80)
print("TESTING BOLLINGER BANDS SIGNAL DETECTION")
print("=" * 80)

# Get BB config
bb_config = SIGNAL_CONFIGS['bb_lower_break']
print(f"\nBB Configuration:")
print(f"  Period: {bb_config['period']}")
print(f"  Std Dev: {bb_config['std_dev']}")
print(f"  Leverage: {bb_config['leverage']}x")

# Calculate BB
bb_result = calculate_bollinger_bands(
    pd.Series(df['closePrice'].values), 
    period=bb_config['period'], 
    std_dev=bb_config['std_dev']
)

# Check for signals
signal_count = 0
for idx in range(bb_config['period'], len(df)):
    if check_bb_lower_break(df.iloc[:idx+1], idx, bb_config['period'], bb_config['std_dev']):
        signal_count += 1
        if signal_count <= 5:  # Show first 5
            print(f"\nSignal {signal_count}:")
            print(f"  Date: {df.iloc[idx]['timestamp']}")
            print(f"  Price: ${df.iloc[idx]['closePrice']:.2f}")
            print(f"  BB Lower: ${bb_result['lower'].iloc[idx]:.2f}")
            print(f"  Breaking below: {df.iloc[idx]['closePrice'] < bb_result['lower'].iloc[idx]}")

print(f"\n" + "=" * 80)
print(f"RESULTS:")
print(f"  Total BB signals in January: {signal_count}")
print(f"  Total candles analyzed: {len(df) - bb_config['period']}")
print(f"  Signal frequency: {signal_count / (len(df) - bb_config['period']) * 100:.1f}%")

# Check all signals
print("\n" + "=" * 80)
print("ALL SIGNALS FREQUENCY CHECK")
print("=" * 80)

from Brains.strategy_signals import get_strategy_analysis

# Test on a specific day
test_date = datetime(2024, 1, 10).date()
day_data = df[df['date'] <= test_date].copy()

if len(day_data) > 100:
    analysis = get_strategy_analysis(
        day_data,
        strategy_mode='all_signals',
        enable_crash_protection=False,
        current_date=test_date
    )
    
    print(f"\nAnalysis for {test_date}:")
    print(f"  Confidence: {analysis.get('confidence', 0)}%")
    print(f"  Signal: {analysis.get('signal_name', 'None')}")
    print(f"  Blocked: {analysis.get('blocked', False)}")
    print(f"  Direction: {analysis.get('direction', 'None')}")
    
    if 'signals_fired' in analysis:
        print(f"\n  Signals that fired:")
        for sig, fired in analysis['signals_fired'].items():
            if fired:
                print(f"    - {sig}")
