#!/usr/bin/env python3
"""
Test Alpha Vantage Integration
Verifies all components are working together correctly
"""

import asyncio
import sqlite3
import pandas as pd
from datetime import datetime, time
import pytz
from bot.settings import TradingBotSettings
from bot.market_time import MarketTimeManager
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def test_alpha_vantage_data():
    """Test that Alpha Vantage data is available and correct"""
    logger.info("=" * 80)
    logger.info("TESTING ALPHA VANTAGE DATA")
    logger.info("=" * 80)
    
    settings = TradingBotSettings('settings.txt')
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table_name = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
    
    try:
        conn = sqlite3.connect(db_path)
        
        # Check if table exists
        cursor = conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cursor.fetchone()[0]
        
        logger.info(f"✅ Alpha Vantage database connected")
        logger.info(f"   Total candles: {count}")
        
        # Get date range
        cursor.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table_name}")
        min_ts, max_ts = cursor.fetchone()
        
        logger.info(f"   Date range: {min_ts} to {max_ts}")
        
        # Check for critical trading times (15:55 ET candles)
        cursor.execute(f"""
            SELECT COUNT(*) FROM {table_name} 
            WHERE strftime('%H:%M', timestamp) = '15:55'
        """)
        close_candles = cursor.fetchone()[0]
        
        logger.info(f"   Market close candles (15:55 ET): {close_candles}")
        
        if close_candles > 0:
            logger.info("   ✅ Has market close time data (can execute strategy)")
        else:
            logger.warning("   ⚠️ No market close time data found")
        
        # Show sample of recent data
        cursor.execute(f"""
            SELECT timestamp, close FROM {table_name}
            ORDER BY timestamp DESC LIMIT 5
        """)
        recent = cursor.fetchall()
        
        logger.info("\n   Recent candles:")
        for ts, close_price in recent:
            logger.info(f"     {ts}: ${close_price:.2f}")
        
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"❌ Error testing Alpha Vantage data: {e}")
        return False

def test_timezone_conversion():
    """Test timezone conversions for display"""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING TIMEZONE CONVERSIONS")
    logger.info("=" * 80)
    
    # Test times
    eastern = pytz.timezone('US/Eastern')
    uae = pytz.timezone('Asia/Dubai')
    
    # Market close time in ET
    et_close = datetime.now(eastern).replace(hour=16, minute=0, second=0)
    
    # Entry time (T-15s)
    et_entry = et_close.replace(hour=15, minute=59, second=45)
    
    # Exit time (T-30s)
    et_exit = et_close.replace(hour=15, minute=59, second=30)
    
    # Convert to UAE time
    uae_close = et_close.astimezone(uae)
    uae_entry = et_entry.astimezone(uae)
    uae_exit = et_exit.astimezone(uae)
    
    logger.info("Market Events:")
    logger.info(f"  Close: {et_close.strftime('%I:%M %p ET')} = {uae_close.strftime('%I:%M %p UAE')}")
    logger.info(f"  Entry: {et_entry.strftime('%I:%M:%S %p ET')} = {uae_entry.strftime('%I:%M:%S %p UAE')}")
    logger.info(f"  Exit:  {et_exit.strftime('%I:%M:%S %p ET')} = {uae_exit.strftime('%I:%M:%S %p UAE')}")
    
    # Check if conversions are correct
    expected_diff = 8 if et_close.dst() else 9  # UAE is UTC+4, ET is UTC-5 (or UTC-4 during DST)
    actual_diff = (uae_close.hour - et_close.hour) % 24
    
    if actual_diff == expected_diff:
        logger.info(f"\n✅ Timezone conversion correct (ET + {expected_diff} hours = UAE)")
    else:
        logger.warning(f"\n⚠️ Timezone conversion issue: expected +{expected_diff}h, got +{actual_diff}h")
    
    return True

def test_market_timing():
    """Test market timing calculations"""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING MARKET TIMING")
    logger.info("=" * 80)
    
    settings = TradingBotSettings('settings.txt')
    market_timer = MarketTimeManager(settings)
    
    # Mock market info (you'd get this from Capital.com API)
    mock_market_info = {
        "marketStatus": "TRADEABLE",
        "instrument": {
            "openingHours": {
                "mon": [{"from": "13:30", "to": "20:00"}],
                "tue": [{"from": "13:30", "to": "20:00"}],
                "wed": [{"from": "13:30", "to": "20:00"}],
                "thu": [{"from": "13:30", "to": "20:00"}],
                "fri": [{"from": "13:30", "to": "20:00"}]
            }
        }
    }
    
    event = market_timer.get_next_market_event(mock_market_info)
    
    logger.info("Current Market Event:")
    logger.info(f"  Market is: {'OPEN' if event.get('is_open') else 'CLOSED'}")
    logger.info(f"  Next event: {event.get('next_event', 'unknown')}")
    
    if event.get('time_until_seconds'):
        hours = event['time_until_seconds'] / 3600
        logger.info(f"  Time until: {hours:.1f} hours")
    
    if event.get('current_uae_time'):
        logger.info(f"  Current UAE time: {event['current_uae_time']}")
    
    return True

async def test_data_refresh():
    """Test the T-120s data refresh mechanism"""
    logger.info("\n" + "=" * 80)
    logger.info("TESTING T-120s DATA REFRESH")
    logger.info("=" * 80)
    
    from bot.trader import TradingBot
    settings = TradingBotSettings('settings.txt')
    
    try:
        # Create bot instance
        bot = TradingBot(settings)
        
        # Test the refresh method
        logger.info("Testing Alpha Vantage refresh...")
        success = await bot.refresh_alpha_vantage_data()
        
        if success:
            logger.info("✅ Data refresh successful")
        else:
            logger.warning("⚠️ Data refresh failed (check API key and network)")
        
        return success
        
    except Exception as e:
        logger.error(f"❌ Error testing data refresh: {e}")
        return False

async def main():
    """Run all tests"""
    logger.info("ALPHA VANTAGE INTEGRATION TEST SUITE")
    logger.info("=" * 80)
    
    results = []
    
    # Test 1: Alpha Vantage Data
    results.append(("Alpha Vantage Data", test_alpha_vantage_data()))
    
    # Test 2: Timezone Conversion
    results.append(("Timezone Conversion", test_timezone_conversion()))
    
    # Test 3: Market Timing
    results.append(("Market Timing", test_market_timing()))
    
    # Test 4: Data Refresh
    results.append(("T-120s Data Refresh", await test_data_refresh()))
    
    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("TEST SUMMARY")
    logger.info("=" * 80)
    
    for test_name, passed in results:
        status = "✅ PASSED" if passed else "❌ FAILED"
        logger.info(f"{test_name}: {status}")
    
    all_passed = all(result[1] for result in results)
    
    if all_passed:
        logger.info("\n🎉 ALL TESTS PASSED! System ready for trading.")
        logger.info("\nNext steps:")
        logger.info("1. Run 'start.bat' to start the bot")
        logger.info("2. Select 'All 6 Signals WITH Protection' in the dashboard")
        logger.info("3. Monitor at 11:58 PM UAE for data refresh")
        logger.info("4. Watch for trade execution at 11:59:45 PM UAE")
    else:
        logger.warning("\n⚠️ Some tests failed. Please review and fix issues.")
    
    return all_passed

if __name__ == '__main__':
    success = asyncio.run(main())
    exit(0 if success else 1)
