#!/usr/bin/env python3
"""
Analyze backtest details to understand the discrepancy
"""

import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import pytz
from bot.settings import TradingBotSettings
from Brains.strategy_signals import SIGNAL_CONFIGS
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_av_data():
    """Analyze Alpha Vantage data quality and coverage"""
    settings = TradingBotSettings('settings.txt')
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table_name = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
    
    conn = sqlite3.connect(db_path)
    
    # Get data summary
    query = f"""
        SELECT 
            MIN(timestamp) as first_date,
            MAX(timestamp) as last_date,
            COUNT(*) as total_candles,
            COUNT(DISTINCT DATE(timestamp)) as trading_days
        FROM {table_name}
    """
    
    cursor = conn.cursor()
    cursor.execute(query)
    result = cursor.fetchone()
    
    logger.info("=" * 80)
    logger.info("ALPHA VANTAGE DATA ANALYSIS")
    logger.info("=" * 80)
    logger.info(f"First candle: {result[0]}")
    logger.info(f"Last candle:  {result[1]}")
    logger.info(f"Total candles: {result[2]:,}")
    logger.info(f"Trading days: {result[3]}")
    
    # Analyze by year
    query = f"""
        SELECT 
            strftime('%Y', timestamp) as year,
            COUNT(*) as candles,
            COUNT(DISTINCT DATE(timestamp)) as days,
            MIN(close) as min_price,
            MAX(close) as max_price,
            AVG(close) as avg_price
        FROM {table_name}
        GROUP BY year
        ORDER BY year
    """
    
    cursor.execute(query)
    yearly_data = cursor.fetchall()
    
    logger.info("\nYearly Summary:")
    logger.info("Year | Candles | Days | Min Price | Max Price | Avg Price")
    logger.info("-" * 60)
    
    for year, candles, days, min_price, max_price, avg_price in yearly_data:
        logger.info(f"{year} | {candles:7,} | {days:4} | ${min_price:7.2f} | ${max_price:7.2f} | ${avg_price:7.2f}")
    
    # Check for market close candles
    query = f"""
        SELECT 
            strftime('%Y-%m', timestamp) as month,
            COUNT(*) as close_candles
        FROM {table_name}
        WHERE strftime('%H:%M', timestamp) = '15:55'
        GROUP BY month
        ORDER BY month DESC
        LIMIT 12
    """
    
    cursor.execute(query)
    close_data = cursor.fetchall()
    
    logger.info("\nMarket Close Candles (15:55 ET) - Last 12 Months:")
    logger.info("Month    | Close Candles")
    logger.info("-" * 25)
    
    for month, count in close_data:
        logger.info(f"{month} | {count:3}")
    
    # Check TECL price evolution
    query = f"""
        SELECT 
            DATE(timestamp) as date,
            MAX(close) as daily_close
        FROM {table_name}
        WHERE strftime('%H:%M', timestamp) = '15:55'
        GROUP BY date
        ORDER BY date
    """
    
    df = pd.read_sql_query(query, conn)
    df['date'] = pd.to_datetime(df['date'])
    df.set_index('date', inplace=True)
    
    # Calculate monthly returns
    monthly = df.resample('M').last()
    monthly['return'] = monthly['daily_close'].pct_change() * 100
    
    logger.info("\nMonthly Returns (Last 6 Months):")
    logger.info("Month       | Close Price | Return %")
    logger.info("-" * 40)
    
    for idx in monthly.index[-6:]:
        price = monthly.loc[idx, 'daily_close']
        ret = monthly.loc[idx, 'return']
        if pd.notna(price):
            logger.info(f"{idx.strftime('%Y-%m')}    | ${price:8.2f} | {ret:7.2f}%")
    
    # Check for specific test period
    # The original test might have been from a specific period
    test_periods = [
        ('2023-01-01', '2023-12-31', '2023 Full Year'),
        ('2024-01-01', '2024-12-31', '2024 Full Year'),
        ('2023-01-01', '2024-12-31', '2023-2024 (2 Years)'),
        ('2023-01-01', '2025-10-03', 'Full Available Data'),
        ('2024-01-01', '2025-10-03', '2024-Present'),
        ('2023-06-01', '2024-06-01', 'Mid 2023 - Mid 2024'),
    ]
    
    logger.info("\nPeriod Analysis:")
    logger.info("Period                    | Days | Candles | Avg Close")
    logger.info("-" * 60)
    
    for start, end, description in test_periods:
        query = f"""
            SELECT 
                COUNT(DISTINCT DATE(timestamp)) as days,
                COUNT(*) as candles,
                AVG(close) as avg_close
            FROM {table_name}
            WHERE timestamp >= '{start}' AND timestamp <= '{end}'
        """
        cursor.execute(query)
        days, candles, avg_close = cursor.fetchone()
        
        if days and days > 0:
            logger.info(f"{description:25} | {days:4} | {candles:7,} | ${avg_close:7.2f}")
    
    conn.close()
    
    # Signal configuration analysis
    logger.info("\n" + "=" * 80)
    logger.info("SIGNAL CONFIGURATION ANALYSIS")
    logger.info("=" * 80)
    
    logger.info("\nSignal Leverage and Stop Loss:")
    logger.info("Signal              | Leverage | Stop Loss % | Win Rate (Priority)")
    logger.info("-" * 70)
    
    for signal, config in SIGNAL_CONFIGS.items():
        leverage = config.get('leverage', 1.0)
        stop_loss = config.get('stop_loss_pct', 5.0)
        win_rate = config.get('win_rate', 0)
        logger.info(f"{signal:18} | {leverage:8.1f}x | {stop_loss:10.1f}% | {win_rate:18}%")
    
    # Calculate theoretical maximum with perfect timing
    logger.info("\n" + "=" * 80)
    logger.info("THEORETICAL ANALYSIS")
    logger.info("=" * 80)
    
    # If we had perfect 60% win rate with average leverage
    avg_leverage = np.mean([cfg['leverage'] for cfg in SIGNAL_CONFIGS.values()])
    
    logger.info(f"\nAverage leverage across signals: {avg_leverage:.1f}x")
    
    # Simple compound calculation
    start_balance = 500
    monthly_topup = 100
    months = 22  # Approximate for the test period
    
    # With 55% win rate (observed)
    win_rate = 0.559
    avg_win_pct = 2.5  # Approximate from leverage
    avg_loss_pct = 2.0  # From stop loss
    
    expected_return_per_trade = (win_rate * avg_win_pct) - ((1 - win_rate) * avg_loss_pct)
    
    logger.info(f"\nExpected return per trade: {expected_return_per_trade:.2f}%")
    logger.info(f"Trades per month (approx): 15")
    logger.info(f"Monthly return potential: {expected_return_per_trade * 15:.1f}%")
    
    # The discrepancy analysis
    logger.info("\n" + "=" * 80)
    logger.info("DISCREPANCY ANALYSIS")
    logger.info("=" * 80)
    
    logger.info("\nPossible reasons for lower results:")
    logger.info("1. Market conditions changed (TECL volatility different)")
    logger.info("2. Original test used different data source")
    logger.info("3. Original test period was during high volatility")
    logger.info("4. Execution timing differences (slippage)")
    logger.info("5. Data quality differences between sources")
    
    logger.info("\nRecommendations:")
    logger.info("1. Verify the exact test period from original results")
    logger.info("2. Check if original used specific market conditions filter")
    logger.info("3. Compare signal firing frequency between tests")
    logger.info("4. Validate indicator calculations match exactly")

if __name__ == '__main__':
    analyze_av_data()
