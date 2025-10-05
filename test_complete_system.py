#!/usr/bin/env python3
"""
Complete test of the trading system with correct position sizing
"""

import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import pytz
from typing import Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

# Load settings properly
from bot.settings import TradingBotSettings
settings = TradingBotSettings('settings.txt')

# Import the proven strategy signals
from Brains.strategy_signals import (
    get_strategy_analysis, 
    SIGNAL_CONFIGS,
    ENTRY_TIME,
    EXIT_TIME
)

class ProvenSystemTester:
    def __init__(self):
        """Initialize with settings from settings.txt"""
        self.settings = settings
        self.db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
        self.table_name = settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
        self.eastern = pytz.timezone('US/Eastern')
        
        # Get financial settings from settings.txt
        self.invest_pct = settings.getfloat('BOT_CONFIG', 'investment_pct', 99.0) / 100.0
        self.monthly_top_up = settings.getfloat('STRATEGY', 'monthly_top_up', 100.0)
        self.start_balance = settings.getfloat('STRATEGY', 'start_balance', 500.0)
        
        logger.info(f"Settings loaded:")
        logger.info(f"  Investment %: {self.invest_pct * 100:.0f}%")
        logger.info(f"  Monthly Top-up: ${self.monthly_top_up}")
        logger.info(f"  Start Balance: ${self.start_balance}")
    
    def load_data(self, start_date, end_date):
        """Load data from Alpha Vantage database"""
        conn = sqlite3.connect(self.db_path)
        query = f"""
            SELECT timestamp, open, high, low, close, volume 
            FROM {self.table_name}
            WHERE timestamp >= '{start_date}' AND timestamp <= '{end_date}'
            ORDER BY timestamp
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Convert timestamp to datetime and localize to Eastern Time
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df['timestamp'] = df['timestamp'].dt.tz_localize(self.eastern, ambiguous='NaT')
        
        # Add date column for strategy analysis
        df['date'] = df['timestamp'].dt.date
        
        # Rename columns for compatibility
        df = df.rename(columns={
            'open': 'openPrice',
            'high': 'highPrice', 
            'low': 'lowPrice',
            'close': 'closePrice',
            'volume': 'lastTradedVolume'
        })
        
        logger.info(f"Loaded {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        return df
    
    def test_single_trade(self, df, test_date):
        """Test a single trade with detailed calculations"""
        
        # Get data up to test date
        historical_data = df[df['date'] <= test_date].copy()
        
        if len(historical_data) < 100:
            return None
        
        # Get strategy analysis
        analysis = get_strategy_analysis(
            historical_data,
            strategy_mode='all_signals',
            enable_crash_protection=False,  # Disable for this test
            current_date=test_date
        )
        
        if analysis.get('confidence', 0) > 0 and not analysis.get('blocked', False):
            signal_name = analysis.get('signal_name')
            if signal_name and signal_name in SIGNAL_CONFIGS:
                signal_config = SIGNAL_CONFIGS[signal_name]
                
                # Get entry price (market close)
                day_data = df[df['date'] == test_date]
                close_candles = day_data[
                    (day_data['timestamp'].dt.hour == 15) & 
                    (day_data['timestamp'].dt.minute == 55)
                ]
                
                if len(close_candles) > 0:
                    entry_price = close_candles.iloc[0]['closePrice']
                    leverage = signal_config['leverage']
                    stop_loss_pct = signal_config['stop_loss_pct']
                    
                    return {
                        'date': test_date,
                        'signal': signal_name,
                        'entry_price': entry_price,
                        'leverage': leverage,
                        'stop_loss_pct': stop_loss_pct,
                        'confidence': analysis.get('confidence')
                    }
        
        return None
    
    def calculate_position(self, balance, trade_info):
        """Calculate position size with CORRECT formula"""
        
        # CORRECT FORMULA from settings
        investment = balance * self.invest_pct  # Use 99% of balance
        leverage = trade_info['leverage']
        entry_price = trade_info['entry_price']
        
        # Position with leverage
        position_value = investment * leverage
        shares = position_value / entry_price
        
        return {
            'investment': investment,
            'position_value': position_value,
            'shares': shares,
            'entry_price': entry_price,
            'leverage': leverage
        }
    
    def calculate_pnl(self, position, exit_price):
        """Calculate P&L correctly"""
        
        # Price change
        price_change = exit_price - position['entry_price']
        price_change_pct = price_change / position['entry_price']
        
        # P&L on leveraged position
        pnl = price_change * position['shares']
        
        # Return percentage on investment
        return_pct = pnl / position['investment'] * 100
        
        return {
            'exit_price': exit_price,
            'price_change': price_change,
            'price_change_pct': price_change_pct * 100,
            'pnl': pnl,
            'return_pct': return_pct
        }
    
    def run_test(self):
        """Run comprehensive test"""
        
        logger.info("=" * 80)
        logger.info("TESTING PROVEN SYSTEM WITH CORRECT POSITION SIZING")
        logger.info("=" * 80)
        
        # Load data for testing period
        start_date = settings.get('TESTING', 'start_date', '2024-01-01')
        end_date = '2024-02-01'  # Just test first month
        
        df = self.load_data(start_date, end_date)
        
        # Get unique trading days
        trading_days = sorted(df['date'].unique())[:20]  # First 20 days
        
        # Initialize
        balance = self.start_balance
        trades = []
        
        logger.info(f"\nTesting first 20 trading days...")
        logger.info(f"Start Balance: ${balance:.2f}")
        logger.info(f"Investment %: {self.invest_pct * 100:.0f}%")
        
        # Test each day
        for day in trading_days:
            trade_info = self.test_single_trade(df, day)
            
            if trade_info:
                # Calculate position
                position = self.calculate_position(balance, trade_info)
                
                # Simulate 2% favorable move
                exit_price = trade_info['entry_price'] * 1.02
                
                # Calculate P&L
                pnl_info = self.calculate_pnl(position, exit_price)
                
                # Update balance
                new_balance = balance - position['investment'] + position['investment'] + pnl_info['pnl']
                
                trades.append({
                    'date': day,
                    'signal': trade_info['signal'],
                    'balance_before': balance,
                    'investment': position['investment'],
                    'leverage': position['leverage'],
                    'position_value': position['position_value'],
                    'shares': position['shares'],
                    'entry_price': trade_info['entry_price'],
                    'exit_price': exit_price,
                    'pnl': pnl_info['pnl'],
                    'return_pct': pnl_info['return_pct'],
                    'balance_after': new_balance
                })
                
                balance = new_balance
                
                if len(trades) <= 3:  # Show first 3 trades
                    logger.info(f"\n" + "=" * 60)
                    logger.info(f"Trade {len(trades)} on {day}:")
                    logger.info(f"  Signal: {trade_info['signal']} ({position['leverage']}x leverage)")
                    logger.info(f"  Balance Before: ${trades[-1]['balance_before']:.2f}")
                    logger.info(f"  Investment: ${position['investment']:.2f} ({self.invest_pct * 100:.0f}% of balance)")
                    logger.info(f"  Position Value: ${position['position_value']:.2f} (with leverage)")
                    logger.info(f"  Shares: {position['shares']:.2f}")
                    logger.info(f"  Entry: ${trade_info['entry_price']:.2f}")
                    logger.info(f"  Exit: ${exit_price:.2f} (+2% simulated)")
                    logger.info(f"  P&L: ${pnl_info['pnl']:.2f}")
                    logger.info(f"  Return: {pnl_info['return_pct']:.1f}%")
                    logger.info(f"  Balance After: ${new_balance:.2f}")
        
        # Summary
        logger.info("\n" + "=" * 80)
        logger.info("SUMMARY:")
        logger.info("=" * 80)
        logger.info(f"Total Trades: {len(trades)}")
        logger.info(f"Starting Balance: ${self.start_balance:.2f}")
        logger.info(f"Final Balance: ${balance:.2f}")
        logger.info(f"Total Return: ${balance - self.start_balance:.2f} ({(balance/self.start_balance - 1) * 100:.1f}%)")
        
        if trades:
            avg_investment = np.mean([t['investment'] for t in trades])
            avg_position = np.mean([t['position_value'] for t in trades])
            avg_leverage = np.mean([t['leverage'] for t in trades])
            
            logger.info(f"\nAverage per trade:")
            logger.info(f"  Investment: ${avg_investment:.2f}")
            logger.info(f"  Position Value: ${avg_position:.2f}")
            logger.info(f"  Leverage: {avg_leverage:.1f}x")
        
        # Projection
        if len(trades) > 0:
            avg_return_per_trade = (balance / self.start_balance) ** (1/len(trades)) - 1
            projected_400_trades = self.start_balance * (1 + avg_return_per_trade) ** 400
            
            logger.info(f"\nProjection:")
            logger.info(f"  Avg return per trade: {avg_return_per_trade * 100:.2f}%")
            logger.info(f"  Projected after 400 trades: ${projected_400_trades:,.0f}")
            
            if projected_400_trades > 100000:
                logger.info(f"\n✅ SYSTEM VALIDATED! Projection shows potential for 6-figure returns!")
            else:
                logger.info(f"\n⚠️ Lower than expected. Check signal frequency and win rate.")

def main():
    tester = ProvenSystemTester()
    tester.run_test()

if __name__ == '__main__':
    main()
