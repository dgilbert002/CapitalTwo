#!/usr/bin/env python3
"""
Compare TECL data between database.db and database_av.db
Test strategies on both datasets for the same date range
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
import pandas as pd
import sqlite3
from bot.database import DatabaseManager
from Brains.strategy_signals import get_strategy_analysis
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

def get_data_from_db(db_path, epic='TECL'):
    """Get all candles from a database"""
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check which database we're dealing with
        if 'av' in db_path:
            # database_av.db uses different table name
            cursor.execute("""
                SELECT timestamp, open, high, low, close, volume 
                FROM TECL_av_5min 
                ORDER BY timestamp
            """)
        else:
            # database.db uses standard table
            cursor.execute("""
                SELECT timestamp, open, high, low, close, volume 
                FROM candles 
                WHERE epic = ? 
                ORDER BY timestamp
            """, (epic,))
        
        data = cursor.fetchall()
        conn.close()
        
        if data:
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['date'] = df['timestamp'].dt.date
            return df
        return None
    except Exception as e:
        logger.error(f"Error reading {db_path}: {e}")
        return None

def compare_candles(df1, df2, label1='Database 1', label2='Database 2'):
    """Compare candles from two databases"""
    
    # Find overlapping dates
    dates1 = set(df1['date'].unique())
    dates2 = set(df2['date'].unique())
    common_dates = sorted(dates1.intersection(dates2))
    
    logger.info(f"\n{'='*80}")
    logger.info("DATE RANGE COMPARISON")
    logger.info(f"{'='*80}")
    logger.info(f"{label1}: {min(dates1)} to {max(dates1)} ({len(dates1)} days)")
    logger.info(f"{label2}: {min(dates2)} to {max(dates2)} ({len(dates2)} days)")
    logger.info(f"Common dates: {len(common_dates)} days")
    
    if not common_dates:
        logger.error("No overlapping dates found!")
        return None
    
    logger.info(f"Common period: {min(common_dates)} to {max(common_dates)}")
    
    # Filter to common dates
    df1_common = df1[df1['date'].isin(common_dates)].copy()
    df2_common = df2[df2['date'].isin(common_dates)].copy()
    
    # Compare daily statistics
    logger.info(f"\n{'='*80}")
    logger.info("DAILY PRICE COMPARISON")
    logger.info(f"{'='*80}")
    
    comparison = []
    for date in common_dates[:5]:  # Show first 5 days as sample
        d1 = df1_common[df1_common['date'] == date]
        d2 = df2_common[df2_common['date'] == date]
        
        if len(d1) > 0 and len(d2) > 0:
            comparison.append({
                'date': date,
                f'{label1}_open': d1.iloc[0]['open'],
                f'{label1}_close': d1.iloc[-1]['close'],
                f'{label1}_high': d1['high'].max(),
                f'{label1}_low': d1['low'].min(),
                f'{label1}_candles': len(d1),
                f'{label2}_open': d2.iloc[0]['open'],
                f'{label2}_close': d2.iloc[-1]['close'],
                f'{label2}_high': d2['high'].max(),
                f'{label2}_low': d2['low'].min(),
                f'{label2}_candles': len(d2),
            })
    
    if comparison:
        comp_df = pd.DataFrame(comparison)
        for _, row in comp_df.iterrows():
            logger.info(f"\nDate: {row['date']}")
            logger.info(f"  {label1}: O={row[f'{label1}_open']:.2f} H={row[f'{label1}_high']:.2f} L={row[f'{label1}_low']:.2f} C={row[f'{label1}_close']:.2f} ({row[f'{label1}_candles']} candles)")
            logger.info(f"  {label2}: O={row[f'{label2}_open']:.2f} H={row[f'{label2}_high']:.2f} L={row[f'{label2}_low']:.2f} C={row[f'{label2}_close']:.2f} ({row[f'{label2}_candles']} candles)")
            
            # Calculate differences
            open_diff = abs(row[f'{label1}_open'] - row[f'{label2}_open'])
            close_diff = abs(row[f'{label1}_close'] - row[f'{label2}_close'])
            
            if open_diff > 0.01 or close_diff > 0.01:
                logger.info(f"  ⚠️ Price difference: Open Δ=${open_diff:.2f}, Close Δ=${close_diff:.2f}")
    
    return df1_common, df2_common

def test_strategy_on_data(df, strategy_mode, enable_crash_protection, label):
    """Test a strategy on given data"""
    
    # Prepare data format
    df_copy = df.copy()
    df_copy = df_copy.rename(columns={
        'open': 'openPrice',
        'high': 'highPrice',
        'low': 'lowPrice',
        'close': 'closePrice',
        'volume': 'lastTradedVolume'
    })
    
    # Initialize tracking
    balance = 500.0
    trades = []
    current_position = None
    monthly_topup_dates = set()
    
    # Group by date
    dates = sorted(df_copy['date'].unique())
    
    for current_date in dates:
        # Monthly top-up
        if current_date.day <= 7 and current_date not in monthly_topup_dates:
            if not monthly_topup_dates or current_date.month != max(monthly_topup_dates).month:
                balance += 100.0
                monthly_topup_dates.add(current_date)
        
        # Get day's data
        day_data = df_copy[df_copy['date'] == current_date].copy()
        
        if len(day_data) < 10:
            continue
        
        # Get historical data
        hist_data = df_copy[df_copy['date'] <= current_date].tail(1000).copy()
        
        # Exit position at T-30s if we have one
        if current_position and len(day_data) > 0:
            exit_candle = day_data.iloc[-2] if len(day_data) > 1 else day_data.iloc[-1]
            exit_price = exit_candle['closePrice']
            
            # Calculate P&L
            pnl_pct = ((exit_price - current_position['entry_price']) / current_position['entry_price']) * 100
            pnl_pct = pnl_pct * current_position['leverage']
            pnl = current_position['size'] * (pnl_pct / 100)
            balance += current_position['size'] + pnl
            
            trades.append({
                'date': current_date,
                'action': 'exit',
                'price': exit_price,
                'pnl': pnl,
                'balance': balance,
                'signal': current_position.get('signal', 'unknown')
            })
            
            current_position = None
        
        # Check for new entry at T-15s
        if balance > 10 and not current_position:
            # Get analysis
            analysis = get_strategy_analysis(
                hist_data,
                strategy_mode=strategy_mode,
                enable_crash_protection=enable_crash_protection,
                current_date=current_date
            )
            
            if analysis['trade_signal'] == 'buy':
                entry_candle = day_data.iloc[-1]
                entry_price = entry_candle['closePrice']
                
                leverage = analysis.get('strategy_leverage', 1.0)
                position_size = balance * 0.99
                
                current_position = {
                    'entry_date': current_date,
                    'entry_price': entry_price,
                    'size': position_size,
                    'leverage': leverage,
                    'signal': analysis.get('selected_strategy', 'unknown')
                }
                
                balance -= position_size
                
                trades.append({
                    'date': current_date,
                    'action': 'entry',
                    'price': entry_price,
                    'signal': current_position['signal'],
                    'leverage': leverage,
                    'balance': balance
                })
    
    # Calculate statistics
    total_trades = len([t for t in trades if t['action'] == 'entry'])
    wins = len([t for t in trades if t.get('pnl', 0) > 0])
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    
    return {
        'label': label,
        'final_balance': balance,
        'total_trades': total_trades,
        'win_rate': win_rate,
        'trades': trades
    }

def compare_strategies():
    """Main comparison function"""
    
    logger.info("="*80)
    logger.info("DATABASE AND STRATEGY COMPARISON")
    logger.info("="*80)
    
    # Load data from both databases
    logger.info("\nLoading data...")
    df_current = get_data_from_db('database.db', 'TECL')
    df_av = get_data_from_db('database_av.db', 'TECL')
    
    if df_current is None:
        logger.error("No data in database.db")
        return
    
    if df_av is None:
        logger.error("No data in database_av.db")
        return
    
    logger.info(f"Current DB: {len(df_current)} candles")
    logger.info(f"AV DB: {len(df_av)} candles")
    
    # Compare candles
    df1_common, df2_common = compare_candles(
        df_current, df_av, 
        'Current DB', 'AV DB'
    )
    
    if df1_common is None or df2_common is None:
        return
    
    # Test strategies on both datasets
    strategies = [
        ('all_signals', True, "All 6 Signals WITH Protection"),
        ('two_rsi_only', True, "Two RSI WITH Protection"),
    ]
    
    logger.info(f"\n{'='*80}")
    logger.info("STRATEGY PERFORMANCE COMPARISON")
    logger.info(f"{'='*80}")
    
    for strategy_mode, crash_protection, name in strategies:
        logger.info(f"\n📊 Strategy: {name}")
        logger.info("-" * 40)
        
        # Test on current database
        result1 = test_strategy_on_data(
            df1_common, strategy_mode, crash_protection, 
            "Current DB"
        )
        
        # Test on AV database
        result2 = test_strategy_on_data(
            df2_common, strategy_mode, crash_protection,
            "AV DB"
        )
        
        # Compare results
        logger.info(f"\nResults for {name}:")
        logger.info(f"  Current DB: Balance=${result1['final_balance']:.2f}, Trades={result1['total_trades']}, Win Rate={result1['win_rate']:.1f}%")
        logger.info(f"  AV DB:      Balance=${result2['final_balance']:.2f}, Trades={result2['total_trades']}, Win Rate={result2['win_rate']:.1f}%")
        
        # Show trades side by side
        logger.info(f"\n  Trade Comparison (first 5 trades):")
        trades1 = [t for t in result1['trades'] if t['action'] == 'entry'][:5]
        trades2 = [t for t in result2['trades'] if t['action'] == 'entry'][:5]
        
        for i in range(max(len(trades1), len(trades2))):
            if i < len(trades1):
                t1 = trades1[i]
                logger.info(f"    Current DB Trade {i+1}: {t1['date']} @ ${t1['price']:.2f} ({t1['signal']})")
            else:
                logger.info(f"    Current DB Trade {i+1}: No trade")
                
            if i < len(trades2):
                t2 = trades2[i]
                logger.info(f"    AV DB Trade {i+1}:      {t2['date']} @ ${t2['price']:.2f} ({t2['signal']})")
            else:
                logger.info(f"    AV DB Trade {i+1}:      No trade")
    
    # Summary
    logger.info(f"\n{'='*80}")
    logger.info("SUMMARY")
    logger.info(f"{'='*80}")
    logger.info("\n💡 Key Findings:")
    logger.info("1. Check if prices match between databases")
    logger.info("2. Check if same signals fire on same days")
    logger.info("3. Check if performance differs significantly")
    logger.info("4. Identify any data quality issues")

if __name__ == '__main__':
    compare_strategies()
