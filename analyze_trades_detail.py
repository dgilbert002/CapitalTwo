#!/usr/bin/env python3
"""
Analyze trading patterns in detail to understand performance
"""

import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import pytz
from bot.settings import TradingBotSettings
from Brains.strategy_signals import (
    get_strategy_analysis, 
    SIGNAL_CONFIGS,
    ENTRY_TIME,
    EXIT_TIME
)
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_signal_frequency():
    """Analyze how often each signal fires"""
    settings = TradingBotSettings('settings.txt')
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table_name = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
    start_date = settings.get('TESTING', 'start_date', '2024-01-01')
    end_date = settings.get('TESTING', 'end_date', '2025-10-03')
    eastern = pytz.timezone('US/Eastern')
    
    # Load data
    conn = sqlite3.connect(db_path)
    query = f"""
        SELECT timestamp, open, high, low, close, volume 
        FROM {table_name}
        WHERE timestamp >= '{start_date}' AND timestamp <= '{end_date}'
        ORDER BY timestamp
    """
    
    df = pd.read_sql_query(query, conn)
    conn.close()
    
    # Convert and prepare data
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
    
    logger.info("=" * 80)
    logger.info("SIGNAL FREQUENCY ANALYSIS")
    logger.info("=" * 80)
    logger.info(f"Period: {start_date} to {end_date}")
    logger.info(f"Total candles: {len(df):,}")
    
    # Analyze each day
    dates = df['date'].unique()
    signal_counts = {
        'all_signals': {'fired': 0, 'blocked': 0, 'details': []},
        'two_rsi_only': {'fired': 0, 'blocked': 0, 'details': []}
    }
    
    logger.info(f"\nAnalyzing {len(dates)} trading days...")
    
    for i, current_date in enumerate(dates):
        if i % 50 == 0:
            logger.info(f"  Processing day {i+1}/{len(dates)}...")
            
        # Get data up to current date
        historical_data = df[df['date'] <= current_date].copy()
        
        # Check for market close candle
        day_data = df[df['date'] == current_date]
        close_candles = day_data[
            (day_data['timestamp'].dt.hour == 15) & 
            (day_data['timestamp'].dt.minute == 55)
        ]
        
        if len(close_candles) == 0:
            continue
        
        # Test each strategy
        for strategy_mode in ['all_signals', 'two_rsi_only']:
            for enable_protection in [True, False]:
                analysis = get_strategy_analysis(
                    historical_data,
                    strategy_mode=strategy_mode,
                    enable_crash_protection=enable_protection,
                    current_date=current_date
                )
                
                if analysis.get('confidence', 0) > 0:
                    if analysis.get('blocked', False):
                        signal_counts[strategy_mode]['blocked'] += 1
                    else:
                        signal_counts[strategy_mode]['fired'] += 1
                        
                        # Store details for first 10 signals
                        if len(signal_counts[strategy_mode]['details']) < 10:
                            signal_counts[strategy_mode]['details'].append({
                                'date': current_date,
                                'signal': analysis.get('signal_name'),
                                'confidence': analysis.get('confidence'),
                                'protection': enable_protection
                            })
    
    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("SIGNAL FREQUENCY RESULTS")
    logger.info("=" * 80)
    
    for strategy, counts in signal_counts.items():
        total = counts['fired'] + counts['blocked']
        logger.info(f"\n{strategy}:")
        logger.info(f"  Total signals: {total}")
        logger.info(f"  Fired: {counts['fired']} ({counts['fired']/len(dates)*100:.1f}% of days)")
        logger.info(f"  Blocked by crash protection: {counts['blocked']}")
        
        if counts['details']:
            logger.info(f"\n  Sample signals:")
            for detail in counts['details'][:5]:
                logger.info(f"    {detail['date']}: {detail['signal']} (conf={detail['confidence']:.0f}%)")
    
    # Check specific indicators
    logger.info("\n" + "=" * 80)
    logger.info("INDICATOR VALUES CHECK")
    logger.info("=" * 80)
    
    # Get last 200 candles for indicator calculation
    recent_data = df.tail(200).copy()
    
    # Calculate indicators
    from Brains.strategy_signals import (
        calculate_rsi,
        calculate_bollinger_bands,
        calculate_vwap,
        calculate_roc,
        calculate_macd
    )
    
    rsi = calculate_rsi(pd.Series(recent_data['closePrice'].values), period=7)
    bb_result = calculate_bollinger_bands(
        pd.Series(recent_data['closePrice'].values), period=10, std_dev=1.5
    )
    bb_upper = bb_result['upper']
    bb_middle = bb_result['sma']
    bb_lower = bb_result['lower']
    # VWAP uses typical price (high+low+close)/3
    typical_price = (recent_data['highPrice'] + recent_data['lowPrice'] + recent_data['closePrice']) / 3
    vwap = calculate_vwap(
        pd.Series(typical_price.values),
        pd.Series(recent_data['lastTradedVolume'].values)
    )
    roc = calculate_roc(pd.Series(recent_data['closePrice'].values), period=5)
    macd_result = calculate_macd(
        pd.Series(recent_data['closePrice'].values),
        fast=13, slow=30, signal=9
    )
    macd_line = macd_result['macd']
    signal_line = macd_result['signal']
    
    logger.info("\nCurrent Indicator Values (last candle):")
    logger.info(f"  RSI(7): {rsi.iloc[-1]:.2f}")
    logger.info(f"  Price: ${recent_data['closePrice'].iloc[-1]:.2f}")
    logger.info(f"  BB Lower: ${bb_lower.iloc[-1]:.2f}")
    logger.info(f"  VWAP: ${vwap.iloc[-1]:.2f}")
    logger.info(f"  ROC(5): {roc.iloc[-1]:.2f}%")
    logger.info(f"  MACD: {macd_line.iloc[-1]:.2f}")
    
    # Check thresholds
    logger.info("\nSignal Thresholds:")
    logger.info(f"  RSI < 25: {rsi.iloc[-1] < 25} (oversold)")
    logger.info(f"  RSI > 50: {rsi.iloc[-1] > 50} (bullish cross)")
    logger.info(f"  Price < BB Lower: {recent_data['closePrice'].iloc[-1] < bb_lower.iloc[-1]}")
    logger.info(f"  Price > VWAP: {recent_data['closePrice'].iloc[-1] > vwap.iloc[-1]}")
    logger.info(f"  ROC < -5: {roc.iloc[-1] < -5}")
    logger.info(f"  MACD > 0: {macd_line.iloc[-1] > 0}")
    
    # Analyze leverage impact
    logger.info("\n" + "=" * 80)
    logger.info("LEVERAGE AND RISK ANALYSIS")
    logger.info("=" * 80)
    
    for signal_name, config in SIGNAL_CONFIGS.items():
        leverage = config['leverage']
        stop_loss = config['stop_loss_pct']
        
        # Calculate potential gain/loss
        typical_move = 1.0  # 1% price move
        gain_with_leverage = typical_move * leverage
        max_loss = stop_loss
        
        logger.info(f"\n{signal_name}:")
        logger.info(f"  Leverage: {leverage}x")
        logger.info(f"  Stop Loss: {stop_loss}%")
        logger.info(f"  1% move → {gain_with_leverage:.1f}% gain")
        logger.info(f"  Max loss: {max_loss}%")
        logger.info(f"  Risk/Reward: 1:{gain_with_leverage/max_loss:.1f}")

if __name__ == '__main__':
    analyze_signal_frequency()
