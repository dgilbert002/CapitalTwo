#!/usr/bin/env python3
"""
Debug why signals aren't firing
"""

import pandas as pd
import sqlite3
import pytz
from datetime import datetime
from bot.settings import TradingBotSettings
from Brains.strategy_signals import (
    get_strategy_analysis,
    SIGNAL_CONFIGS,
    check_rsi_oversold,
    check_bb_lower_break,
    calculate_rsi,
    calculate_bollinger_bands
)

settings = TradingBotSettings('settings.txt')

# Load data
conn = sqlite3.connect('database_av.db')
query = """
    SELECT timestamp, open, high, low, close, volume 
    FROM TECL_av_5min
    WHERE timestamp >= '2024-01-01' AND timestamp <= '2024-01-31'
    ORDER BY timestamp
"""

df = pd.read_sql_query(query, conn)
conn.close()

# Prepare data
eastern = pytz.timezone('US/Eastern')
df['timestamp'] = pd.to_datetime(df['timestamp'])
df['timestamp'] = df['timestamp'].dt.tz_localize(eastern, ambiguous='NaT')
df['date'] = df['timestamp'].dt.date

df = df.rename(columns={
    'open': 'openPrice',
    'high': 'highPrice', 
    'low': 'lowPrice',
    'close': 'closePrice',
    'volume': 'lastTradedVolume'
})

print("=" * 80)
print("DEBUGGING SIGNAL DETECTION")
print("=" * 80)

# Test specific date
test_date = datetime(2024, 1, 10).date()
historical_data = df[df['date'] <= test_date].copy()

print(f"\nTesting date: {test_date}")
print(f"Historical data points: {len(historical_data)}")

# Get the last candle
if len(historical_data) > 0:
    last_candle = historical_data.iloc[-1]
    print(f"Last candle time: {last_candle['timestamp']}")
    print(f"Last price: ${last_candle['closePrice']:.2f}")

# Test each signal individually
print("\n" + "=" * 80)
print("INDIVIDUAL SIGNAL CHECKS:")
print("=" * 80)

# RSI
rsi = calculate_rsi(pd.Series(historical_data['closePrice'].values), period=7)
if len(rsi) > 0:
    current_rsi = rsi.iloc[-1]
    print(f"\nRSI(7): {current_rsi:.2f}")
    print(f"  Oversold (<25): {current_rsi < 25}")
    print(f"  Above 50: {current_rsi > 50}")

# Bollinger Bands
bb_config = SIGNAL_CONFIGS['bb_lower_break']
bb = calculate_bollinger_bands(
    pd.Series(historical_data['closePrice'].values),
    period=bb_config['period'],
    std_dev=bb_config['std_dev']
)
if len(bb['lower']) > 0:
    current_price = historical_data.iloc[-1]['closePrice']
    bb_lower = bb['lower'].iloc[-1]
    print(f"\nBollinger Bands (period={bb_config['period']}, std={bb_config['std_dev']}):")
    print(f"  Price: ${current_price:.2f}")
    print(f"  BB Lower: ${bb_lower:.2f}")
    print(f"  Breaking below: {current_price < bb_lower}")

# Test with strategy analysis
print("\n" + "=" * 80)
print("STRATEGY ANALYSIS:")
print("=" * 80)

analysis = get_strategy_analysis(
    historical_data,
    strategy_mode='all_signals',
    enable_crash_protection=False,
    current_date=test_date
)

print(f"\nAnalysis Result:")
print(f"  Confidence: {analysis.get('confidence', 0)}%")
print(f"  Signal Name: {analysis.get('signal_name', 'None')}")
print(f"  Blocked: {analysis.get('blocked', False)}")

# Check what's in the analysis
for key, value in analysis.items():
    if key not in ['confidence', 'signal_name', 'blocked', 'direction']:
        print(f"  {key}: {value}")

# Test multiple days
print("\n" + "=" * 80)
print("TESTING MULTIPLE DAYS:")
print("=" * 80)

dates = sorted(df['date'].unique())[:10]
signal_count = 0

for date in dates:
    hist = df[df['date'] <= date].copy()
    if len(hist) < 100:
        continue
    
    analysis = get_strategy_analysis(
        hist,
        strategy_mode='all_signals',
        enable_crash_protection=False,
        current_date=date
    )
    
    if analysis.get('confidence', 0) > 0:
        signal_count += 1
        print(f"\n{date}: Signal={analysis.get('signal_name')}, Confidence={analysis.get('confidence')}%")

print(f"\nTotal signals in first 10 days: {signal_count}")

# Check if it's a data issue
print("\n" + "=" * 80)
print("DATA CHECK:")
print("=" * 80)

# Check for market close candles
market_close_candles = df[
    (df['timestamp'].dt.hour == 15) & 
    (df['timestamp'].dt.minute == 55)
]

print(f"Market close candles (15:55): {len(market_close_candles)}")
if len(market_close_candles) > 0:
    print(f"First: {market_close_candles.iloc[0]['timestamp']}")
    print(f"Last: {market_close_candles.iloc[-1]['timestamp']}")
