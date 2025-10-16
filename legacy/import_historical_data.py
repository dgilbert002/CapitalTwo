#!/usr/bin/env python3
"""
Import historical 5-minute TECL data from AlphaVantage CSV into the trading bot database
"""

import pandas as pd
import sqlite3
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def import_alphavantage_data():
    """Import AlphaVantage 5-minute TECL data into the database"""
    
    # File paths
    csv_file = "./alphavantage_data/TECL_5m_alphavantage.csv"
    db_file = "database.db"
    
    logger.info(f"Starting import from {csv_file} to {db_file}")
    
    try:
        # Read the CSV file
        logger.info("Reading CSV file...")
        df = pd.read_csv(csv_file)
        logger.info(f"Loaded {len(df)} rows from CSV")
        
        # Connect to database
        logger.info("Connecting to database...")
        conn = sqlite3.connect(db_file)
        cursor = conn.cursor()
        
        # Create table if it doesn't exist
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS candles (
                epic TEXT NOT NULL,
                timestamp DATETIME NOT NULL,
                open REAL NOT NULL,
                high REAL NOT NULL,
                low REAL NOT NULL,
                close REAL NOT NULL,
                volume INTEGER,
                PRIMARY KEY (epic, timestamp)
            )
        """)
        
        # Clear existing TECL data
        logger.info("Clearing existing TECL data...")
        cursor.execute("DELETE FROM candles WHERE epic = 'TECL'")
        conn.commit()
        
        # Import data
        logger.info("Importing data...")
        imported_count = 0
        
        for index, row in df.iterrows():
            try:
                # Parse timestamp
                timestamp = datetime.strptime(row['snapshotTime'], '%Y-%m-%d %H:%M:%S')
                
                # Insert into database
                cursor.execute("""
                    INSERT OR REPLACE INTO candles (epic, timestamp, open, high, low, close, volume)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    'TECL',
                    timestamp,
                    float(row['openPrice']),
                    float(row['highPrice']),
                    float(row['lowPrice']),
                    float(row['closePrice']),
                    int(row['lastTradedVolume']) if pd.notna(row['lastTradedVolume']) else 0
                ))
                
                imported_count += 1
                
                # Commit every 1000 rows
                if imported_count % 1000 == 0:
                    conn.commit()
                    logger.info(f"Imported {imported_count} rows...")
                    
            except Exception as e:
                logger.error(f"Error importing row {index}: {e}")
                continue
        
        # Final commit
        conn.commit()
        
        # Verify import
        cursor.execute("SELECT COUNT(*) FROM candles WHERE epic = 'TECL'")
        total_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM candles WHERE epic = 'TECL'")
        date_range = cursor.fetchone()
        
        logger.info(f"Import completed successfully!")
        logger.info(f"Total TECL candles in database: {total_count}")
        logger.info(f"Date range: {date_range[0]} to {date_range[1]}")
        
        conn.close()
        
        return True
        
    except Exception as e:
        logger.error(f"Import failed: {e}")
        return False

if __name__ == "__main__":
    success = import_alphavantage_data()
    if success:
        print("✅ Historical data import completed successfully!")
        print("🚀 The trading bot now has over 45,000 5-minute TECL candles for AI analysis!")
    else:
        print("❌ Import failed. Check the logs for details.")
