#!/usr/bin/env python3
"""
Alpha Vantage data downloader for trading strategy
Downloads 5-minute OHLCV data with extended hours
All timestamps stored in Eastern Time (ET) as provided by Alpha Vantage
"""

import requests
import pandas as pd
import sqlite3
import time
from datetime import datetime, timedelta
import argparse
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def load_settings(filepath='settings.txt'):
    """Load settings from file"""
    settings = {}
    current_section = None
    
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                # Check for section headers
                if line.startswith('[') and line.endswith(']'):
                    current_section = line[1:-1]
                    continue
                
                # Parse key-value pairs
                if '=' in line and current_section:
                    key, value = line.split('=', 1)
                    full_key = f"{current_section}.{key.strip()}"
                    settings[full_key] = value.strip()
    
    return settings

def fetch_av_data(symbol, interval, api_key, month=None, extended_hours=True):
    """
    Fetch data from Alpha Vantage
    
    Args:
        symbol: Stock symbol (e.g., 'TECL')
        interval: Time interval ('5min')
        api_key: Alpha Vantage API key
        month: Specific month in 'YYYY-MM' format (optional)
        extended_hours: Include extended hours data
    """
    base_url = 'https://www.alphavantage.co/query'
    
    # Use the merged TIME_SERIES_INTRADAY API for all requests
    params = {
        'function': 'TIME_SERIES_INTRADAY',
        'symbol': symbol,
        'interval': interval,
        'apikey': api_key,
        'extended_hours': 'true' if extended_hours else 'false',
        'outputsize': 'full',
        'datatype': 'json'
    }
    
    # Add month parameter if specified for historical data
    if month:
        params['month'] = month  # Format: 'YYYY-MM'
    
    logger.info(f"Fetching data from Alpha Vantage...")
    response = requests.get(base_url, params=params)
    
    if response.status_code == 200:
        # Always parse JSON response now
        data = response.json()
        
        # Check for errors
        if 'Error Message' in data:
            logger.error(f"API Error: {data['Error Message']}")
            return None
        elif 'Note' in data:
            logger.warning(f"API Note: {data['Note']}")
            return None
        
        # Extract time series data
        time_series_key = f'Time Series ({interval})'
        if time_series_key not in data:
            logger.error(f"No time series data found in response")
            return None
        
        # Convert to DataFrame
        time_series = data[time_series_key]
        df = pd.DataFrame.from_dict(time_series, orient='index')
        df.index = pd.to_datetime(df.index)
        df = df.reset_index()
        df.columns = ['timestamp', 'open', 'high', 'low', 'close', 'volume']
        
        # Convert string values to float
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = pd.to_numeric(df[col])
        
        # Convert timestamp to datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        # Sort by timestamp
        df = df.sort_values('timestamp')
        
        logger.info(f"Fetched {len(df)} candles")
        return df
    else:
        logger.error(f"Error fetching data: {response.status_code}")
        return None

def save_to_database(df, db_path, table_name):
    """Save dataframe to SQLite database"""
    conn = sqlite3.connect(db_path)
    
    # Create table if not exists
    create_query = f"""
    CREATE TABLE IF NOT EXISTS {table_name} (
        timestamp TEXT PRIMARY KEY,
        open REAL,
        high REAL,
        low REAL,
        close REAL,
        volume REAL
    )
    """
    conn.execute(create_query)
    
    # Also create metadata table if needed
    conn.execute("""
    CREATE TABLE IF NOT EXISTS epic_metadata (
        epic TEXT PRIMARY KEY,
        timeframe TEXT,
        tz TEXT,
        first_timestamp TEXT,
        last_timestamp TEXT,
        source TEXT
    )
    """)
    
    # Insert data (replace on conflict)
    df['timestamp'] = df['timestamp'].astype(str)
    
    inserted = 0
    for _, row in df.iterrows():
        try:
            insert_query = f"""
            INSERT OR REPLACE INTO {table_name} 
            (timestamp, open, high, low, close, volume)
            VALUES (?, ?, ?, ?, ?, ?)
            """
            conn.execute(insert_query, tuple(row))
            inserted += 1
        except Exception as e:
            logger.warning(f"Failed to insert row: {e}")
    
    # Update metadata
    if inserted > 0:
        first_ts = df['timestamp'].min()
        last_ts = df['timestamp'].max()
        
        conn.execute("""
        INSERT OR REPLACE INTO epic_metadata 
        (epic, timeframe, tz, first_timestamp, last_timestamp, source)
        VALUES (?, ?, ?, ?, ?, ?)
        """, ('TECL', '5min', 'US/Eastern', first_ts, last_ts, 'alpha_vantage'))
    
    conn.commit()
    conn.close()
    
    return inserted

def get_latest_timestamp(db_path, table_name):
    """Get the latest timestamp in the database"""
    conn = sqlite3.connect(db_path)
    
    try:
        query = f"SELECT MAX(timestamp) FROM {table_name}"
        result = conn.execute(query).fetchone()
        conn.close()
        
        if result and result[0]:
            return pd.to_datetime(result[0])
        return None
    except:
        conn.close()
        return None

def refresh_latest_data(settings):
    """Refresh the latest data (called at T-120s)"""
    api_key = settings.get('ALPHA_VANTAGE.api_key')
    symbol = settings.get('ALPHA_VANTAGE.symbol', 'TECL')
    interval = settings.get('ALPHA_VANTAGE.interval', '5min')
    extended_hours = settings.get('ALPHA_VANTAGE.extended_hours', 'true').lower() == 'true'
    db_path = settings.get('ALPHA_VANTAGE.database', 'database_av.db')
    table_name = settings.get('ALPHA_VANTAGE.table_name', f'{symbol}_av_{interval}')
    
    logger.info(f"Refreshing latest {symbol} data...")
    
    # Fetch latest data with outputsize='full' to get trailing 30 days
    df = fetch_av_data(symbol, interval, api_key, None, extended_hours)
    
    if df is not None and not df.empty:
        # Get current latest in database
        latest = get_latest_timestamp(db_path, table_name)
        
        if latest:
            # Only keep new data
            df = df[df['timestamp'] > latest]
            logger.info(f"Found {len(df)} new candles since {latest}")
        
        if not df.empty:
            rows = save_to_database(df, db_path, table_name)
            logger.info(f"✅ Added {rows} new rows to database")
            return rows
        else:
            logger.info("ℹ️ No new data available")
            return 0
    else:
        logger.error("❌ Failed to fetch latest data")
        return -1

def main():
    parser = argparse.ArgumentParser(description='Download Alpha Vantage data')
    parser.add_argument('--refresh', action='store_true', help='Refresh latest data')
    parser.add_argument('--initial', action='store_true', help='Download initial 1 month of data')
    parser.add_argument('--start', type=str, help='Start date (YYYY-MM-DD)')
    parser.add_argument('--end', type=str, help='End date (YYYY-MM-DD)')
    parser.add_argument('--settings', type=str, default='settings.txt', help='Settings file path')
    
    args = parser.parse_args()
    
    # Load settings
    settings = load_settings(args.settings)
    
    api_key = settings.get('ALPHA_VANTAGE.api_key')
    symbol = settings.get('ALPHA_VANTAGE.symbol', 'TECL')
    interval = settings.get('ALPHA_VANTAGE.interval', '5min')
    extended_hours = settings.get('ALPHA_VANTAGE.extended_hours', 'true').lower() == 'true'
    db_path = settings.get('ALPHA_VANTAGE.database', 'database_av.db')
    table_name = settings.get('ALPHA_VANTAGE.table_name', f'{symbol}_av_{interval}')
    
    if not api_key:
        logger.error("❌ Error: api_key not found in [ALPHA_VANTAGE] section of settings.txt")
        return
    
    logger.info("📊 Alpha Vantage Data Downloader")
    logger.info(f"   Symbol: {symbol}")
    logger.info(f"   Interval: {interval}")
    logger.info(f"   Extended Hours: {extended_hours}")
    logger.info(f"   Database: {db_path}")
    logger.info(f"   Table: {table_name}")
    logger.info("-" * 50)
    
    if args.refresh:
        # Refresh mode - get latest data
        refresh_latest_data(settings)
    
    elif args.initial:
        # Initial download - get recent data
        logger.info("📅 Downloading initial data...")
        
        # Get recent data without specifying month (gets last ~100 days with outputsize=full)
        df = fetch_av_data(symbol, interval, api_key, None, extended_hours)
        
        if df is not None and not df.empty:
            rows = save_to_database(df, db_path, table_name)
            logger.info(f"✅ Saved {rows} rows to database")
            
            # Show date range
            logger.info(f"📅 Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
            logger.info(f"📊 Total candles: {len(df)}")
        else:
            logger.error("❌ Failed to fetch initial data")
    
    else:
        logger.info("Usage:")
        logger.info("  --initial           : Download initial month of data")
        logger.info("  --refresh           : Refresh latest data")
        logger.info("  --start YYYY-MM-DD  : Download from start date (future)")
        logger.info("  --end YYYY-MM-DD    : Download to end date (future)")

if __name__ == '__main__':
    main()
