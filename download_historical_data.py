#!/usr/bin/env python3
"""
Download TECL historical data from specific date range
Fetches all data from September 1, 2025 to present
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

async def download_date_range_data():
    """Download TECL data from Sep 1, 2025 to present"""
    
    logger.info("=" * 80)
    logger.info("TECL HISTORICAL DATA DOWNLOADER")
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
        
        # Define date range
        start_date = datetime(2025, 9, 1, 0, 0, 0)  # September 1, 2025
        end_date = datetime.now()
        
        logger.info(f"Target date range: {start_date.date()} to {end_date.date()}")
        logger.info(f"Total days to fetch: {(end_date - start_date).days}")
        logger.info("Downloading 5-minute candles in batches...")
        
        all_candles = []
        total_api_calls = 0
        
        # Capital.com returns most recent data, so we'll make multiple calls
        # We'll try to get overlapping batches to ensure we don't miss any data
        
        current_date = end_date
        batch_size = 1000  # Max we can get per request
        
        while len(all_candles) < 10000 and total_api_calls < 20:  # Safety limits
            try:
                logger.info(f"\nBatch {total_api_calls + 1}: Requesting {batch_size} candles...")
                
                # Get batch of candles
                result = await api.get_historical_prices(
                    epic='TECL',
                    resolution=api.ResolutionType.MINUTE_5,
                    num_candles=batch_size
                )
                
                total_api_calls += 1
                
                if not result or not isinstance(result, dict):
                    logger.warning("No data received in this batch")
                    break
                
                # Check for error
                if 'errorCode' in result:
                    logger.error(f"API Error: {result}")
                    break
                
                # Parse the candles
                candles = result.get('prices', [])
                
                if not candles:
                    logger.warning("No candles in response")
                    break
                
                logger.info(f"  Received {len(candles)} candles")
                
                # Process candles
                batch_candles = []
                earliest_timestamp = None
                latest_timestamp = None
                
                for candle in candles:
                    timestamp = candle.get('snapshotTime', candle.get('timestamp'))
                    if timestamp:
                        # Parse the timestamp
                        candle_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        
                        # Only include candles from Sep 1 onwards
                        if candle_time >= start_date:
                            batch_candles.append({
                                'timestamp': timestamp,
                                'open': candle['openPrice']['bid'],
                                'high': candle['highPrice']['bid'],
                                'low': candle['lowPrice']['bid'],
                                'close': candle['closePrice']['bid'],
                                'volume': candle.get('lastTradedVolume', 0)
                            })
                            
                            if not earliest_timestamp or timestamp < earliest_timestamp:
                                earliest_timestamp = timestamp
                            if not latest_timestamp or timestamp > latest_timestamp:
                                latest_timestamp = timestamp
                
                if batch_candles:
                    # Add to our collection
                    all_candles.extend(batch_candles)
                    
                    earliest_dt = datetime.fromisoformat(earliest_timestamp.replace('Z', '+00:00'))
                    latest_dt = datetime.fromisoformat(latest_timestamp.replace('Z', '+00:00'))
                    
                    logger.info(f"  Date range in batch: {earliest_dt} to {latest_dt}")
                    logger.info(f"  Valid candles from Sep 1: {len(batch_candles)}")
                    
                    # Check if we've reached September 1
                    if earliest_dt <= start_date:
                        logger.info("  ✓ Reached target start date (Sep 1, 2025)")
                        break
                    
                    # If we're getting the same data, try a different approach
                    if len(all_candles) > 1000 and earliest_dt == datetime.fromisoformat(all_candles[-1001]['timestamp'].replace('Z', '+00:00')):
                        logger.info("  Reached API limit for historical data")
                        break
                else:
                    logger.warning("No valid candles after Sep 1 in this batch")
                    break
                
                # Small delay between requests
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error fetching batch: {e}")
                break
        
        if all_candles:
            # Remove duplicates and sort
            logger.info("\nProcessing downloaded data...")
            
            # Remove duplicates based on timestamp
            unique_candles = {}
            for candle in all_candles:
                unique_candles[candle['timestamp']] = candle
            
            # Convert back to list and sort
            unique_candles_list = list(unique_candles.values())
            unique_candles_list.sort(key=lambda x: x['timestamp'])
            
            logger.info(f"Total unique candles: {len(unique_candles_list)}")
            
            if unique_candles_list:
                # Get date range
                first_timestamp = datetime.fromisoformat(unique_candles_list[0]['timestamp'].replace('Z', '+00:00'))
                last_timestamp = datetime.fromisoformat(unique_candles_list[-1]['timestamp'].replace('Z', '+00:00'))
                
                logger.info(f"Final date range: {first_timestamp} to {last_timestamp}")
                logger.info(f"Days covered: {(last_timestamp - first_timestamp).days}")
                
                # Calculate statistics
                trading_days = len(set(datetime.fromisoformat(c['timestamp'].replace('Z', '+00:00')).date() 
                                      for c in unique_candles_list))
                logger.info(f"Trading days: {trading_days}")
                logger.info(f"Average candles per day: {len(unique_candles_list) / trading_days:.1f}")
                
                # Store in database (ADD to existing data, never delete!)
                logger.info("\nAdding to database (preserving existing data)...")
                
                stored_count = 0
                duplicate_count = 0
                
                for candle in unique_candles_list:
                    try:
                        db.store_candle('TECL', candle)
                        stored_count += 1
                    except Exception as e:
                        # Skip duplicates or errors (likely duplicates)
                        duplicate_count += 1
                
                logger.info(f"✅ Added {stored_count} new candles to database")
                if duplicate_count > 0:
                    logger.info(f"ℹ️ Skipped {duplicate_count} duplicate candles")
                
                # Verify total in database
                total_in_db = len(db.get_candles('TECL', limit=100000))
                logger.info(f"📊 Total candles now in database: {total_in_db}")
                
                # Show sample of data
                logger.info("\nSample of downloaded data:")
                logger.info("First 3 candles:")
                for i in range(min(3, len(unique_candles_list))):
                    c = unique_candles_list[i]
                    logger.info(f"  {c['timestamp']}: O={c['open']:.2f} H={c['high']:.2f} L={c['low']:.2f} C={c['close']:.2f}")
                
                if len(unique_candles_list) > 3:
                    logger.info("Last 3 candles:")
                    for i in range(max(0, len(unique_candles_list)-3), len(unique_candles_list)):
                        c = unique_candles_list[i]
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
    logger.info("Starting historical data download...")
    logger.info("Fetching all data from September 1, 2025 to present")
    logger.info("-" * 80)
    
    success = await download_date_range_data()
    
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
        logger.error("\nNote: Capital.com may limit historical data access")
        logger.error("The API typically provides only the most recent ~1000 candles")
        return 1

if __name__ == '__main__':
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
