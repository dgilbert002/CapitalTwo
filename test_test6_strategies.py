#!/usr/bin/env python3
"""
Test script to validate Test6 strategies (8 signals) 
Expected results:
- Without protection: $509,453
- With protection: $958,260
"""

import sys
import os
import pandas as pd
import numpy as np
from datetime import datetime
import logging
import sqlite3
from configparser import ConfigParser

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Brains.strategy_signals import (
    SIGNAL_CONFIGS, check_all_signals, select_best_signal,
    calculate_daily_indicators, should_block_trade,
    CRASH_PROTECTION_CONFIG
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_av_data(start_date='2024-01-01', end_date='2025-10-05'):
    """Load Alpha Vantage data from database"""
    conn = sqlite3.connect('database_av.db')
    query = f"""
        SELECT * FROM TECL_av_5min 
        WHERE timestamp >= '{start_date}' 
        AND timestamp <= '{end_date} 23:59:59'
        ORDER BY timestamp
    """
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Rename columns to match expected format
    df.rename(columns={
        'open': 'openPrice',
        'high': 'highPrice',
        'low': 'lowPrice',
        'close': 'closePrice',
        'volume': 'lastTradedVolume'
    }, inplace=True)
    
    # Convert timestamp
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    
    return df

def run_test6_backtest(df, enable_protection=False):
    """Run backtest with Test6 strategies (8 signals)"""
    
    balance = 500.0
    monthly_top_up = 100.0
    invest_pct = 0.99
    
    current_position = None
    trades = []
    last_top_up_month = None
    
    # Entry and exit times (Eastern Time)
    entry_hour, entry_minute = 15, 59
    exit_hour, exit_minute = 15, 59
    
    logger.info(f"\n{'='*60}")
    logger.info(f"Running Test6 {'WITH' if enable_protection else 'WITHOUT'} Protection")
    logger.info(f"Start Balance: ${balance:,.2f}")
    logger.info(f"{'='*60}")
    
    for i in range(len(df)):
        row = df.iloc[i]
        current_date = row['date']
        timestamp = row['timestamp']
        
        # Monthly top-up
        if timestamp.day <= 5 and timestamp.month != last_top_up_month and balance > 0:
            balance += monthly_top_up
            last_top_up_month = timestamp.month
            logger.debug(f"Monthly top-up: +${monthly_top_up} → Balance: ${balance:,.2f}")
        
        # Check for stop loss
        if current_position:
            if row['lowPrice'] <= current_position['stop_loss']:
                exit_price = current_position['stop_loss']
                price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                pnl = current_position['notional_value'] * price_change_pct
                balance += pnl
                
                trades.append({
                    'entry_date': current_position['entry_date'],
                    'exit_date': current_date,
                    'signal': current_position['signal'],
                    'entry_price': current_position['entry_price'],
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'exit_reason': 'stop_loss'
                })
                
                logger.debug(f"Stop loss hit: {current_position['signal']} → P&L: ${pnl:,.2f}")
                current_position = None
        
        # Exit position at market close
        if current_position and timestamp.hour == exit_hour and timestamp.minute >= exit_minute - 1:
            exit_price = row['closePrice']
            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            pnl = current_position['notional_value'] * price_change_pct
            balance += pnl
            
            trades.append({
                'entry_date': current_position['entry_date'],
                'exit_date': current_date,
                'signal': current_position['signal'],
                'entry_price': current_position['entry_price'],
                'exit_price': exit_price,
                'pnl': pnl,
                'exit_reason': 'market_close'
            })
            
            current_position = None
        
        # Check for entry signals at entry time
        if not current_position and timestamp.hour == entry_hour and timestamp.minute >= entry_minute - 1:
            # Get recent data for analysis
            lookback = max(0, i - 100)
            recent_df = df.iloc[lookback:i+1].copy()
            
            # Check crash protection if enabled
            if enable_protection:
                daily_indicators = calculate_daily_indicators(recent_df, current_date)
                if should_block_trade(daily_indicators, CRASH_PROTECTION_CONFIG):
                    continue
            
            # Check all 8 signals (test6 mode)
            signals_fired = check_all_signals(recent_df, strategy_mode='test6')
            
            if any(signals_fired.values()):
                # Select best signal by win_rate
                best_signal = select_best_signal(signals_fired, SIGNAL_CONFIGS)
                if best_signal:
                    config = SIGNAL_CONFIGS[best_signal]
                    entry_price = row['closePrice']
                    leverage = config['leverage']
                    stop_loss_pct = config['stop_loss_pct']
                    
                    notional_value = balance * invest_pct * leverage
                    stop_loss = entry_price * (1 - stop_loss_pct / 100)
                    
                    current_position = {
                        'entry_date': current_date,
                        'entry_price': entry_price,
                        'notional_value': notional_value,
                        'stop_loss': stop_loss,
                        'signal': best_signal,
                        'leverage': leverage
                    }
                    
                    logger.debug(f"Entry: {best_signal} @ ${entry_price:.2f}, Leverage: {leverage}x")
    
    # Close any open position at end
    if current_position:
        exit_price = df.iloc[-1]['closePrice']
        price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
        pnl = current_position['notional_value'] * price_change_pct
        balance += pnl
        
        trades.append({
            'entry_date': current_position['entry_date'],
            'exit_date': df.iloc[-1]['date'],
            'signal': current_position['signal'],
            'entry_price': current_position['entry_price'],
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_reason': 'end_of_data'
        })
    
    # Calculate statistics
    total_trades = len(trades)
    winning_trades = sum(1 for t in trades if t['pnl'] > 0)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
    
    # Count trades by signal
    signal_counts = {}
    for trade in trades:
        signal = trade['signal']
        if signal not in signal_counts:
            signal_counts[signal] = 0
        signal_counts[signal] += 1
    
    logger.info(f"\n{'='*60}")
    logger.info(f"RESULTS - Test6 {'WITH' if enable_protection else 'WITHOUT'} Protection")
    logger.info(f"{'='*60}")
    logger.info(f"Final Balance: ${balance:,.2f}")
    logger.info(f"Total Return: {(balance - 500) / 500 * 100:.1f}%")
    logger.info(f"Total Trades: {total_trades}")
    logger.info(f"Win Rate: {win_rate:.1f}%")
    logger.info(f"\nTrades by Signal:")
    for signal in sorted(signal_counts.keys()):
        logger.info(f"  {signal}: {signal_counts[signal]} trades")
    
    # Highlight new Test6 signals
    keltner_trades = signal_counts.get('keltner_lower_break', 0)
    macd_hist_trades = signal_counts.get('macd_histogram_negative', 0)
    logger.info(f"\nTest6 New Signals:")
    logger.info(f"  Keltner Lower Break: {keltner_trades} trades")
    logger.info(f"  MACD Histogram Negative: {macd_hist_trades} trades")
    
    return balance, trades

def main():
    """Run Test6 validation"""
    
    # Load settings
    settings = ConfigParser()
    settings.read('settings.txt')
    
    start_date = settings.get('TESTING', 'start_date', fallback='2024-01-01')
    end_date = settings.get('TESTING', 'end_date', fallback='2025-10-05')
    
    logger.info(f"Loading data from {start_date} to {end_date}")
    
    # Load data
    df = load_av_data(start_date, end_date)
    logger.info(f"Loaded {len(df)} candles")
    
    # Run both Test6 scenarios
    logger.info("\n" + "="*80)
    logger.info("TEST6 VALIDATION - 8 STRATEGIES")
    logger.info("="*80)
    
    # Test6 without protection (expected: $509,453)
    balance_no_protection, trades_no_protection = run_test6_backtest(df, enable_protection=False)
    
    # Test6 with protection (expected: $958,260)
    balance_with_protection, trades_with_protection = run_test6_backtest(df, enable_protection=True)
    
    # Final summary
    logger.info("\n" + "="*80)
    logger.info("FINAL SUMMARY")
    logger.info("="*80)
    logger.info(f"Test6 NO Protection:   ${balance_no_protection:,.0f} (Expected: $509,453)")
    logger.info(f"Test6 WITH Protection: ${balance_with_protection:,.0f} (Expected: $958,260)")
    
    # Check if results match expectations
    no_protection_match = abs(balance_no_protection - 509453) < 10000  # Within $10k
    with_protection_match = abs(balance_with_protection - 958260) < 10000  # Within $10k
    
    if no_protection_match and with_protection_match:
        logger.info("\n✅ SUCCESS! Results match expected values!")
    else:
        logger.warning("\n⚠️ Results don't match expectations. May need adjustment.")

if __name__ == "__main__":
    main()
