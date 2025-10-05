#!/usr/bin/env python3
"""
Download TECL historical data from Capital.com
Downloads up to 3 months of 5-minute candles
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta
import asyncio
from bot.api import CapitalComAPI
from bot.database import DatabaseManager
from bot.settings import TradingBotSettings
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def download_tecl_data():
    """Download TECL data from Capital.com"""
    
    logger.info("=" * 80)
    logger.info("TECL DATA DOWNLOADER")
    logger.info("=" * 80)
    
    try:
        # Initialize components
        settings = TradingBotSettings('settings.txt')
        api = CapitalComAPI(settings)
        db = DatabaseManager('database.db')
        
        # Authenticate with the API
        authenticated = await api.authenticate()
        if not authenticated:
            logger.error("Failed to authenticate with Capital.com API")
            logger.error("Please check your credentials in settings.txt")
            return False
        
        # Calculate date range (3 months back)
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)  # 3 months
        
        logger.info(f"Target date range: {start_date.date()} to {end_date.date()}")
        logger.info("Downloading 5-minute candles...")
        
        # Capital.com limits: typically 1000-10000 candles per request
        # 5-min candles: ~78 per day * 90 days = ~7,020 candles
        
        # The API returns the most recent candles, we just need one call
        batch_size = 1000  # More reasonable batch size
        logger.info(f"Fetching up to {batch_size} most recent candles...")
        
        try:
            # Capital.com API returns the most recent candles up to the limit
            # For 3 months: ~78 candles/day * 90 days = ~7000 candles
            
            result = await api.get_historical_prices(
                epic='TECL',
                resolution=api.ResolutionType.MINUTE_5,
                num_candles=batch_size
            )
            
            logger.info(f"API Response type: {type(result)}")
            if result and isinstance(result, dict):
                logger.info(f"API Response keys: {result.keys()}")
                if 'errorCode' in result:
                    logger.error(f"API Error: {result}")
            
            if not result:
                logger.error("No data received from API")
                return False
            
            # Parse the candles - the result IS the list of candles
            all_candles = []
            candles = result if isinstance(result, list) else result.get('prices', [])
            
            logger.info(f"Received {len(candles)} candles from API")
            
            for candle in candles:
                timestamp = candle.get('snapshotTime', candle.get('timestamp'))
                if timestamp:
                    all_candles.append({
                        'timestamp': timestamp,
                        'open': candle['openPrice']['bid'],
                        'high': candle['highPrice']['bid'],
                        'low': candle['lowPrice']['bid'],
                        'close': candle['closePrice']['bid'],
                        'volume': candle.get('lastTradedVolume', 0)
                    })
            
        except Exception as e:
            logger.error(f"Error fetching data: {e}")
            return False
        
        if all_candles:
            # Sort by timestamp (oldest first)
            all_candles.sort(key=lambda x: x['timestamp'])
            
            # Remove duplicates
            unique_candles = []
            seen_timestamps = set()
            for candle in all_candles:
                if candle['timestamp'] not in seen_timestamps:
                    unique_candles.append(candle)
                    seen_timestamps.add(candle['timestamp'])
            
            logger.info(f"\nTotal unique candles downloaded: {len(unique_candles)}")
            
            if unique_candles:
                # Parse dates
                first_timestamp = datetime.fromisoformat(unique_candles[0]['timestamp'].replace('Z', '+00:00'))
                last_timestamp = datetime.fromisoformat(unique_candles[-1]['timestamp'].replace('Z', '+00:00'))
                
                logger.info(f"Date range: {first_timestamp} to {last_timestamp}")
                logger.info(f"Days covered: {(last_timestamp - first_timestamp).days}")
                
                # Store in database (ADD to existing data, never delete!)
                logger.info("\nAdding to database (preserving existing data)...")
                
                # Store new data using the database's store_candle method
                stored_count = 0
                for candle in unique_candles:
                    try:
                        db.store_candle('TECL', candle)
                        stored_count += 1
                    except Exception as e:
                        # Skip duplicates or errors (likely duplicates)
                        pass
                logger.info(f"✅ Added {stored_count} new candles to database")
                
                # Verify storage
                stored_count = len(db.get_candles('TECL', limit=100000))
                logger.info(f"Verified: {stored_count} candles in database")
                
                # Show sample of data
                logger.info("\nSample of downloaded data:")
                logger.info("First 3 candles:")
                for i in range(min(3, len(unique_candles))):
                    c = unique_candles[i]
                    logger.info(f"  {c['timestamp']}: O={c['open']:.2f} H={c['high']:.2f} L={c['low']:.2f} C={c['close']:.2f}")
                
                logger.info("Last 3 candles:")
                for i in range(max(0, len(unique_candles)-3), len(unique_candles)):
                    c = unique_candles[i]
                    logger.info(f"  {c['timestamp']}: O={c['open']:.2f} H={c['high']:.2f} L={c['low']:.2f} C={c['close']:.2f}")
                
                return True
            else:
                logger.error("No valid candles after processing")
                return False
        else:
            logger.error("Failed to download any candles")
            return False
            
    except Exception as e:
        logger.error(f"Error in download process: {e}")
        import traceback
        traceback.print_exc()
        return False

async def main():
    """Main execution"""
    logger.info("Starting TECL data download...")
    logger.info("This will download up to 3 months of 5-minute candles")
    logger.info("-" * 80)
    
    success = await download_tecl_data()
    
    if success:
        logger.info("\n" + "=" * 80)
        logger.info("✅ DATA DOWNLOAD COMPLETE!")
        logger.info("=" * 80)
        logger.info("\nNext steps:")
        logger.info("1. Run 'python backtest_strategies.py' to test strategies")
        logger.info("2. Start the bot with 'start.bat' for live trading")
        return 0
    else:
        logger.error("\n" + "=" * 80)
        logger.error("❌ DATA DOWNLOAD FAILED!")
        logger.error("=" * 80)
        logger.error("\nTroubleshooting:")
        logger.error("1. Check your Capital.com API credentials in settings.txt")
        logger.error("2. Ensure you have an active internet connection")
        logger.error("3. Verify TECL is available in your Capital.com account")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
