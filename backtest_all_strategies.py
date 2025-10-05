#!/usr/bin/env python3
"""
COMPREHENSIVE STRATEGY BACKTEST
Tests all strategy combinations on available TECL data
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, time as dt_time
import pandas as pd
import numpy as np
from bot.database import DatabaseManager
from bot.api import CapitalComAPI
from Brains.strategy_signals import (
    get_strategy_analysis,
    SIGNAL_CONFIGS,
    ENTRY_TIME,
    EXIT_TIME
)
import asyncio
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class StrategyBacktester:
    """Run backtests on all strategy combinations"""
    
    def __init__(self):
        self.db = DatabaseManager('database.db')
        self.api = CapitalComAPI()
        
    async def refresh_data(self):
        """Download fresh TECL data"""
        logger.info("=" * 80)
        logger.info("REFRESHING TECL DATA")
        logger.info("=" * 80)
        
        try:
            # Get 200 days of 5-minute candles
            logger.info("Downloading 200 days of TECL data...")
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=200)
            
            # Download data
            candles = await self.api.get_historical_prices(
                'TECL',
                resolution='MINUTE_5',
                max_count=20000,  # ~200 days of 5-min candles
                from_date=start_date.strftime('%Y-%m-%dT00:00:00'),
                to_date=end_date.strftime('%Y-%m-%dT23:59:59')
            )
            
            if candles:
                # Store in database
                self.db.store_candles('TECL', candles)
                logger.info(f"✅ Downloaded {len(candles)} candles")
                
                # Get data summary
                df = pd.DataFrame(candles)
                df['snapshotTime'] = pd.to_datetime(df['snapshotTime'])
                
                logger.info(f"Date range: {df['snapshotTime'].min()} to {df['snapshotTime'].max()}")
                logger.info(f"Total trading days: {df['snapshotTime'].dt.date.nunique()}")
                
                return True
            else:
                logger.error("Failed to download data")
                return False
                
        except Exception as e:
            logger.error(f"Error refreshing data: {e}")
            return False
    
    def get_data_summary(self):
        """Get summary of available data"""
        logger.info("\n" + "=" * 80)
        logger.info("DATA SUMMARY")
        logger.info("=" * 80)
        
        # Get all candles from database
        candles = self.db.get_candles('TECL', limit=50000)
        
        if not candles:
            logger.error("No data available in database")
            return None
            
        # Convert to DataFrame
        df = pd.DataFrame(candles, columns=['epic', 'timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        # Summary stats
        start_date = df['timestamp'].min()
        end_date = df['timestamp'].max()
        total_candles = len(df)
        trading_days = df['timestamp'].dt.date.nunique()
        
        logger.info(f"📊 Data Available:")
        logger.info(f"  Start: {start_date}")
        logger.info(f"  End: {end_date}")
        logger.info(f"  Total candles: {total_candles:,}")
        logger.info(f"  Trading days: {trading_days}")
        logger.info(f"  Date range: {(end_date - start_date).days} days")
        
        # Check for gaps
        df['date'] = df['timestamp'].dt.date
        daily_counts = df.groupby('date').size()
        logger.info(f"  Avg candles/day: {daily_counts.mean():.1f}")
        logger.info(f"  Min candles/day: {daily_counts.min()}")
        logger.info(f"  Max candles/day: {daily_counts.max()}")
        
        return df
    
    def run_backtest(self, df, strategy_mode, enable_crash_protection):
        """Run backtest for a specific strategy configuration"""
        
        # Prepare data format
        df_copy = df.copy()
        df_copy = df_copy.rename(columns={
            'open': 'openPrice',
            'high': 'highPrice',
            'low': 'lowPrice',
            'close': 'closePrice',
            'volume': 'lastTradedVolume'
        })
        df_copy['date'] = df_copy['timestamp'].dt.date
        
        # Initialize tracking
        balance = 500.0  # Starting balance
        positions = []
        trades = []
        current_position = None
        monthly_topup_dates = set()
        
        # Group by date for daily processing
        dates = sorted(df_copy['date'].unique())
        
        for current_date in dates:
            # Monthly top-up on first trading day of month
            if current_date.day <= 7 and current_date not in monthly_topup_dates:
                if not monthly_topup_dates or current_date.month != max(monthly_topup_dates).month:
                    balance += 100.0
                    monthly_topup_dates.add(current_date)
            
            # Get day's data
            day_mask = df_copy['date'] == current_date
            day_data = df_copy[day_mask].copy()
            
            if len(day_data) < 10:  # Skip days with insufficient data
                continue
            
            # Get historical data up to current date
            hist_mask = df_copy['date'] <= current_date
            historical_data = df_copy[hist_mask].tail(1000).copy()  # Last 1000 candles
            
            # Check for market close times (approximation for backtesting)
            # Assume market closes at 16:00 ET (20:00 UTC)
            close_time = pd.Timestamp.combine(current_date, dt_time(20, 0))
            entry_time = close_time - timedelta(seconds=15)  # T-15s
            exit_time = close_time - timedelta(seconds=30)   # T-30s
            
            # Exit position at T-30s if we have one
            if current_position and len(day_data) > 0:
                exit_candle = day_data.iloc[-2] if len(day_data) > 1 else day_data.iloc[-1]
                exit_price = exit_candle['closePrice']
                
                # Calculate P&L
                if current_position['direction'] == 'long':
                    pnl_pct = ((exit_price - current_position['entry_price']) / current_position['entry_price']) * 100
                else:
                    pnl_pct = ((current_position['entry_price'] - exit_price) / current_position['entry_price']) * 100
                
                pnl = current_position['size'] * (pnl_pct / 100)
                balance += current_position['size'] + pnl
                
                trades.append({
                    'entry_date': current_position['entry_date'],
                    'exit_date': current_date,
                    'entry_price': current_position['entry_price'],
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'balance_after': balance
                })
                
                current_position = None
            
            # Check for new entry at T-15s
            if balance > 10:  # Minimum balance to trade
                # Get analysis
                analysis = get_strategy_analysis(
                    historical_data,
                    strategy_mode=strategy_mode,
                    enable_crash_protection=enable_crash_protection,
                    current_date=current_date
                )
                
                if analysis['trade_signal'] == 'buy' and not current_position:
                    entry_candle = day_data.iloc[-1]
                    entry_price = entry_candle['closePrice']
                    
                    # Calculate position size (99% of balance with leverage)
                    leverage = analysis.get('strategy_leverage', 1.0)
                    position_size = balance * 0.99
                    
                    current_position = {
                        'entry_date': current_date,
                        'entry_price': entry_price,
                        'size': position_size,
                        'leverage': leverage,
                        'direction': 'long',
                        'stop_loss': analysis.get('strategy_stop_loss', 5.0),
                        'signal': analysis.get('selected_strategy', 'unknown')
                    }
                    
                    balance -= position_size
            
            # Check stop loss during the day
            if current_position:
                for _, candle in day_data.iterrows():
                    low_price = candle['lowPrice']
                    entry_price = current_position['entry_price']
                    stop_loss_pct = current_position['stop_loss']
                    
                    if low_price <= entry_price * (1 - stop_loss_pct / 100):
                        # Stop loss hit
                        exit_price = entry_price * (1 - stop_loss_pct / 100)
                        pnl = -current_position['size'] * (stop_loss_pct / 100)
                        balance += current_position['size'] + pnl
                        
                        trades.append({
                            'entry_date': current_position['entry_date'],
                            'exit_date': current_date,
                            'entry_price': entry_price,
                            'exit_price': exit_price,
                            'pnl': pnl,
                            'pnl_pct': -stop_loss_pct,
                            'balance_after': balance,
                            'exit_reason': 'stop_loss'
                        })
                        
                        current_position = None
                        break
        
        # Calculate statistics
        if trades:
            df_trades = pd.DataFrame(trades)
            wins = df_trades[df_trades['pnl'] > 0]
            losses = df_trades[df_trades['pnl'] <= 0]
            
            win_rate = (len(wins) / len(trades)) * 100 if trades else 0
            avg_win = wins['pnl_pct'].mean() if len(wins) > 0 else 0
            avg_loss = losses['pnl_pct'].mean() if len(losses) > 0 else 0
            
            # Calculate max drawdown
            df_trades['cum_balance'] = df_trades['balance_after']
            df_trades['running_max'] = df_trades['cum_balance'].expanding().max()
            df_trades['drawdown'] = (df_trades['cum_balance'] - df_trades['running_max']) / df_trades['running_max'] * 100
            max_drawdown = df_trades['drawdown'].min()
            
            return {
                'final_balance': balance,
                'total_trades': len(trades),
                'win_rate': win_rate,
                'avg_win': avg_win,
                'avg_loss': avg_loss,
                'max_drawdown': max_drawdown,
                'total_pnl': balance - 500,
                'roi': ((balance - 500) / 500) * 100
            }
        else:
            return {
                'final_balance': balance,
                'total_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'max_drawdown': 0,
                'total_pnl': balance - 500,
                'roi': ((balance - 500) / 500) * 100
            }
    
    def run_all_backtests(self, df):
        """Run backtests for all strategy combinations"""
        logger.info("\n" + "=" * 80)
        logger.info("RUNNING ALL STRATEGY BACKTESTS")
        logger.info("=" * 80)
        
        strategies = [
            ('all_signals', True, "All 6 Signals WITH Protection"),
            ('all_signals', False, "All 6 Signals NO Protection"),
            ('two_rsi_only', True, "Two RSI WITH Protection"),
            ('two_rsi_only', False, "Two RSI NO Protection"),
        ]
        
        results = []
        
        for strategy_mode, crash_protection, name in strategies:
            logger.info(f"\n📊 Testing: {name}")
            logger.info("-" * 40)
            
            result = self.run_backtest(df, strategy_mode, crash_protection)
            result['strategy'] = name
            results.append(result)
            
            logger.info(f"Final Balance: ${result['final_balance']:,.2f}")
            logger.info(f"Total P&L: ${result['total_pnl']:,.2f}")
            logger.info(f"ROI: {result['roi']:.1f}%")
            logger.info(f"Win Rate: {result['win_rate']:.1f}%")
            logger.info(f"Total Trades: {result['total_trades']}")
            logger.info(f"Max Drawdown: {result['max_drawdown']:.1f}%")
            logger.info(f"Avg Win: {result['avg_win']:.1f}%")
            logger.info(f"Avg Loss: {result['avg_loss']:.1f}%")
        
        # Summary comparison
        logger.info("\n" + "=" * 80)
        logger.info("STRATEGY COMPARISON")
        logger.info("=" * 80)
        
        logger.info("\n{:<35} | {:>12} | {:>8} | {:>8} | {:>10}".format(
            "Strategy", "Final Balance", "Win Rate", "Max DD", "ROI"
        ))
        logger.info("-" * 80)
        
        for r in results:
            logger.info("{:<35} | ${:>11,.0f} | {:>7.1f}% | {:>7.1f}% | {:>9.1f}%".format(
                r['strategy'],
                r['final_balance'],
                r['win_rate'],
                r['max_drawdown'],
                r['roi']
            ))
        
        # Highlight best performer
        best = max(results, key=lambda x: x['final_balance'])
        logger.info(f"\n🏆 BEST PERFORMER: {best['strategy']}")
        logger.info(f"   Final Balance: ${best['final_balance']:,.2f}")
        
        # Compare to expected results
        logger.info("\n" + "=" * 80)
        logger.info("COMPARISON TO EXPECTED RESULTS")
        logger.info("=" * 80)
        logger.info("Note: Results may vary based on available data period")
        logger.info("\n{:<35} | {:>12} | {:>12}".format(
            "Strategy", "Expected", "Actual"
        ))
        logger.info("-" * 60)
        
        expected = {
            "All 6 Signals WITH Protection": 699074,
            "All 6 Signals NO Protection": 376004,
            "Two RSI WITH Protection": 485948,
            "Two RSI NO Protection": 348803
        }
        
        for r in results:
            exp_val = expected.get(r['strategy'], 0)
            logger.info("{:<35} | ${:>11,} | ${:>11,.0f}".format(
                r['strategy'],
                exp_val,
                r['final_balance']
            ))

async def main():
    """Main execution"""
    tester = StrategyBacktester()
    
    # Refresh data
    logger.info("Starting data refresh...")
    success = await tester.refresh_data()
    
    if not success:
        logger.error("Failed to refresh data. Using existing data...")
    
    # Get data summary
    df = tester.get_data_summary()
    
    if df is None or len(df) < 1000:
        logger.error("Insufficient data for backtesting")
        return
    
    # Run all backtests
    tester.run_all_backtests(df)
    
    logger.info("\n" + "=" * 80)
    logger.info("BACKTEST COMPLETE")
    logger.info("=" * 80)
    logger.info("\n💡 KEY INSIGHTS:")
    logger.info("1. Results depend on data period - longer periods show better compounding")
    logger.info("2. Crash protection significantly reduces drawdowns")
    logger.info("3. All strategies require discipline - don't override stop losses")
    logger.info("4. Monthly top-ups compound significantly over time")

if __name__ == '__main__':
    asyncio.run(main())
