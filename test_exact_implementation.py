#!/usr/bin/env python3
"""
Test using EXACT implementation from TradingBot_Full_Logic.py
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timedelta
import pytz

# Copy exact signal configs from TradingBot_Full_Logic.py
SIGNAL_CONFIGS = {
    'rsi_oversold': {
        'leverage': 10.0,
        'stop_loss_pct': 3.5,
        'period': 7,
        'threshold': 25,
        'win_rate': 80.0
    },
    'rsi_bullish_cross_50': {
        'leverage': 5.0,
        'stop_loss_pct': 10.0,
        'period': 7,
        'win_rate': 63.0
    },
    'bb_lower_break': {
        'leverage': 10.0,
        'stop_loss_pct': 3.5,
        'period': 20,       # Your proven system uses 20
        'std_dev': 2.5,     # Your proven system uses 2.5
        'win_rate': 80.0
    },
    'price_above_vwap': {
        'leverage': 4.0,
        'stop_loss_pct': 8.0,
        'threshold': -0.01,
        'win_rate': 57.6
    },
    'roc_below_threshold': {
        'leverage': 5.0,
        'stop_loss_pct': 7.5,
        'period': 10,
        'threshold': -5,
        'win_rate': 78.9
    },
    'macd_positive': {
        'leverage': 5.0,
        'stop_loss_pct': 4.0,
        'fast_period': 13,
        'slow_period': 30,
        'signal_period': 9,
        'threshold': 0.05,
        'win_rate': 63.0
    }
}

# Copy exact calculation functions
def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI (Relative Strength Index)"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(prices: pd.Series, period: int = 14, std_dev: float = 2.0) -> dict:
    """Calculate Bollinger Bands"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return {'sma': sma, 'upper': upper, 'lower': lower}

def check_bb_lower_break(df: pd.DataFrame, idx: int, period: int = 14, std_dev: float = 1.5) -> bool:
    """Check if price breaks below lower Bollinger Band"""
    if len(df) < period:
        return False
    bb = calculate_bollinger_bands(df['closePrice'], period, std_dev)
    lower = bb['lower'].iloc[idx]
    if pd.isna(lower):
        return False
    return df['closePrice'].iloc[idx] < lower

# Load data
conn = sqlite3.connect('database_av.db')
query = """
    SELECT timestamp, open, high, low, close, volume 
    FROM TECL_av_5min
    WHERE timestamp >= '2024-01-01' AND timestamp <= '2024-02-01'
    ORDER BY timestamp
"""
df = pd.read_sql_query(query, conn)
conn.close()

# Prepare data exactly as in TradingBot_Full_Logic.py
df['snapshotTime'] = pd.to_datetime(df['timestamp'])
df['date'] = df['snapshotTime'].dt.date
df['time'] = df['snapshotTime'].dt.time
df['openPrice'] = df['open']
df['highPrice'] = df['high']
df['lowPrice'] = df['low']
df['closePrice'] = df['close']
df['lastTradedVolume'] = df['volume']

print("=" * 80)
print("TESTING EXACT IMPLEMENTATION FROM TradingBot_Full_Logic.py")
print("=" * 80)

# Test BB signal with exact parameters
bb_config = SIGNAL_CONFIGS['bb_lower_break']
print(f"\nBollinger Bands Config (from your proven system):")
print(f"  Period: {bb_config['period']}")
print(f"  Std Dev: {bb_config['std_dev']}")
print(f"  Leverage: {bb_config['leverage']}x")
print(f"  Stop Loss: {bb_config['stop_loss_pct']}%")

# Count signals
signal_count = 0
test_days = df['date'].unique()[:20]  # First 20 days

for day in test_days:
    day_data = df[df['date'] <= day].copy()
    if len(day_data) < bb_config['period']:
        continue
    
    idx = len(day_data) - 1
    if check_bb_lower_break(day_data, idx, bb_config['period'], bb_config['std_dev']):
        signal_count += 1
        if signal_count <= 3:
            print(f"\nBB Signal on {day}:")
            print(f"  Price: ${day_data.iloc[idx]['closePrice']:.2f}")

print(f"\n" + "=" * 80)
print(f"RESULTS:")
print(f"  BB Signals in first 20 days: {signal_count}")
print(f"  Days analyzed: {len(test_days)}")
print(f"  Signal frequency: {signal_count / len(test_days) * 100:.1f}%")

# Test the actual trading logic
print("\n" + "=" * 80)
print("SIMULATING ACTUAL TRADING")
print("=" * 80)

balance = 500.0
entry_time = dt_time(15, 59, 45)
trades = 0

for day in test_days[:10]:  # First 10 days
    day_candles = df[df['date'] == day].copy()
    if day_candles.empty:
        continue
    
    # Find candle at entry time
    entry_candles = day_candles[
        (day_candles['time'].apply(lambda x: x.hour) == 15) & 
        (day_candles['time'].apply(lambda x: x.minute) == 59)
    ]
    
    if not entry_candles.empty:
        # Check for BB signal
        hist_data = df[df['date'] <= day].copy()
        idx = len(hist_data) - 1
        
        if check_bb_lower_break(hist_data, idx, bb_config['period'], bb_config['std_dev']):
            entry_price = entry_candles.iloc[0]['closePrice']
            leverage = bb_config['leverage']
            position_size = balance * 0.99 * leverage
            
            trades += 1
            print(f"\nTrade {trades} on {day}:")
            print(f"  Entry: ${entry_price:.2f}")
            print(f"  Position: ${position_size:.2f} ({leverage}x leverage)")
            print(f"  Balance: ${balance:.2f}")

print(f"\n" + "=" * 80)
print(f"Total trades in first 10 days: {trades}")
