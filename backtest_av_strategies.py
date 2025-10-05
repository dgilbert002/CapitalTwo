#!/usr/bin/env python3
"""
Comprehensive Strategy Backtesting with Alpha Vantage Data
Tests all strategy combinations to verify the $699k system
"""

import pandas as pd
import sqlite3
import numpy as np
from datetime import datetime, timedelta, time as dt_time
import pytz
from typing import Dict, List, Tuple
import logging

# Import the proven strategy signals
from Brains.strategy_signals import (
    get_strategy_analysis, 
    SIGNAL_CONFIGS,
    ENTRY_TIME,
    EXIT_TIME,
    calculate_daily_indicators,
    should_block_trade
)
from bot.settings import TradingBotSettings

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StrategyBacktester:
    def __init__(self):
        """Initialize backtester with Alpha Vantage data"""
        self.settings = TradingBotSettings('settings.txt')
        self.db_path = self.settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
        self.table_name = self.settings.get('ALPHA_VANTAGE', 'table_name', 'TECL_av_5min')
        self.eastern = pytz.timezone('US/Eastern')
        
    def load_av_data(self, start_date=None, end_date=None):
        """Load data from Alpha Vantage database"""
        conn = sqlite3.connect(self.db_path)
        
        query = f"""
            SELECT timestamp, open, high, low, close, volume 
            FROM {self.table_name}
            WHERE 1=1
        """
        
        if start_date:
            query += f" AND timestamp >= '{start_date}'"
        if end_date:
            query += f" AND timestamp <= '{end_date}'"
            
        query += " ORDER BY timestamp"
        
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
            'volume': 'lastTradedVolume'  # Add volume mapping
        })
        
        logger.info(f"Loaded {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
        
        return df
    
    def run_backtest(self, df, strategy_mode, enable_crash_protection, 
                     start_balance=500.0, monthly_top_up=100.0):
        """Run backtest on historical data"""
        
        balance = start_balance
        positions = []
        trades = []
        current_position = None
        last_top_up_month = None
        
        # Group by date for daily processing
        dates = df['date'].unique()
        
        logger.info(f"\nBacktesting {strategy_mode} {'WITH' if enable_crash_protection else 'WITHOUT'} crash protection")
        logger.info(f"Date range: {dates[0]} to {dates[-1]} ({len(dates)} days)")
        
        for current_date in dates:
            # Get data for this day
            day_data = df[df['date'] == current_date].copy()
            
            if len(day_data) == 0:
                continue
                
            # Check for monthly top-up (first trading day of month)
            current_month = current_date.month
            if last_top_up_month != current_month and balance > 0:
                balance += monthly_top_up
                last_top_up_month = current_month
                logger.debug(f"{current_date}: Monthly top-up +${monthly_top_up:.2f}, balance=${balance:.2f}")
            
            # Get market close candle (15:55 ET)
            close_time = datetime.combine(current_date, dt_time(15, 55))
            close_candles = day_data[
                (day_data['timestamp'].dt.hour == 15) & 
                (day_data['timestamp'].dt.minute == 55)
            ]
            
            if len(close_candles) == 0:
                continue
            
            close_candle = close_candles.iloc[0]
            
            # Check for position exit (T-30s = 15:59:30)
            if current_position:
                exit_price = close_candle['closePrice']
                
                # Check stop loss throughout the day (including extended hours)
                day_low = day_data['lowPrice'].min()
                stop_loss_hit = day_low <= current_position['stop_loss']
                
                if stop_loss_hit:
                    # Exit at stop loss
                    exit_price = current_position['stop_loss']
                    # CRITICAL FIX: Use elite model's P&L calculation
                    price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                    pnl = current_position['notional_value'] * price_change_pct
                    balance += pnl  # Only add P&L, not investment
                    
                    trades.append({
                        'entry_date': current_position['entry_date'],
                        'exit_date': current_date,
                        'entry_price': current_position['entry_price'],
                        'exit_price': exit_price,
                        'notional_value': current_position['notional_value'],
                        'pnl': pnl,
                        'pnl_pct': (pnl / current_position['notional_value']) * 100,
                        'exit_reason': 'stop_loss',
                        'balance_after': balance
                    })
                    
                    current_position = None
                    logger.debug(f"{current_date}: Stop loss hit at ${exit_price:.2f}, PnL=${pnl:.2f}")
                    
                else:
                    # Normal exit at close
                    # CRITICAL FIX: Use elite model's P&L calculation
                    price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                    pnl = current_position['notional_value'] * price_change_pct
                    balance += pnl  # Only add P&L, not investment
                    
                    trades.append({
                        'entry_date': current_position['entry_date'],
                        'exit_date': current_date,
                        'entry_price': current_position['entry_price'],
                        'exit_price': exit_price,
                        'notional_value': current_position['notional_value'],
                        'pnl': pnl,
                        'pnl_pct': (pnl / current_position['notional_value']) * 100,
                        'exit_reason': 'market_close',
                        'balance_after': balance
                    })
                    
                    current_position = None
                    logger.debug(f"{current_date}: Exit at close ${exit_price:.2f}, PnL=${pnl:.2f}")
            
            # Check for new position entry (T-15s = 15:59:45)
            if balance > 10:  # Minimum balance check
                # Get all historical data up to current date for analysis
                historical_data = df[df['date'] <= current_date].copy()
                
                # Run strategy analysis
                analysis = get_strategy_analysis(
                    historical_data,
                    strategy_mode=strategy_mode,
                    enable_crash_protection=enable_crash_protection,
                    current_date=current_date
                )
                
                if analysis.get('confidence', 0) > 0 and not analysis.get('blocked', False):
                    # We have a signal - enter position
                    entry_price = close_candle['closePrice']
                    
                # Get signal details
                signal_name = analysis.get('signal_name', 'unknown')
                signal_config = SIGNAL_CONFIGS.get(signal_name, {})
                leverage = signal_config.get('leverage', 1.0)
                stop_loss_pct = signal_config.get('stop_loss_pct', 5.0)
                
                # Calculate position size (99% of balance as per config)
                # CRITICAL FIX: Use notional value like elite model
                notional_value = balance * 0.99 * leverage
                stop_loss = entry_price * (1 - stop_loss_pct / 100)
                
                current_position = {
                    'entry_date': current_date,
                    'entry_price': entry_price,
                    'notional_value': notional_value,
                    'stop_loss': stop_loss,
                    'signal': signal_name,
                    'leverage': leverage,
                    'stop_loss_pct': stop_loss_pct
                }
                
                # DON'T subtract investment from balance
                
                logger.debug(f"{current_date}: Entry signal {signal_name} at ${entry_price:.2f}, "
                           f"leverage={leverage}x, SL=${stop_loss:.2f}")
        
        # Close any remaining position
        if current_position:
            exit_price = df.iloc[-1]['closePrice']
            # CRITICAL FIX: Use elite model's P&L calculation
            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            pnl = current_position['notional_value'] * price_change_pct
            balance += pnl  # Only add P&L, not investment
            
            trades.append({
                'entry_date': current_position['entry_date'],
                'exit_date': dates[-1],
                'entry_price': current_position['entry_price'],
                'exit_price': exit_price,
                'notional_value': current_position['notional_value'],
                'pnl': pnl,
                'pnl_pct': (pnl / current_position['notional_value']) * 100,
                'exit_reason': 'end_of_data',
                'balance_after': balance
            })
        
        # Calculate statistics
        if trades:
            df_trades = pd.DataFrame(trades)
            winning_trades = df_trades[df_trades['pnl'] > 0]
            losing_trades = df_trades[df_trades['pnl'] <= 0]
            
            # Calculate max drawdown
            cumulative_balance = [start_balance]
            running_balance = start_balance
            
            for trade in trades:
                running_balance = trade['balance_after']
                cumulative_balance.append(running_balance)
            
            peak = np.maximum.accumulate(cumulative_balance)
            drawdown = (np.array(cumulative_balance) - peak) / peak * 100
            max_drawdown = drawdown.min()
            
            stats = {
                'final_balance': balance,
                'total_return': (balance - start_balance) / start_balance * 100,
                'total_trades': len(trades),
                'winning_trades': len(winning_trades),
                'losing_trades': len(losing_trades),
                'win_rate': len(winning_trades) / len(trades) * 100 if trades else 0,
                'avg_win': winning_trades['pnl'].mean() if len(winning_trades) > 0 else 0,
                'avg_loss': losing_trades['pnl'].mean() if len(losing_trades) > 0 else 0,
                'max_win': winning_trades['pnl'].max() if len(winning_trades) > 0 else 0,
                'max_loss': losing_trades['pnl'].min() if len(losing_trades) > 0 else 0,
                'max_drawdown': max_drawdown
            }
        else:
            stats = {
                'final_balance': balance,
                'total_return': 0,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'max_win': 0,
                'max_loss': 0,
                'max_drawdown': 0
            }
        
        return stats, trades

def main():
    """Run comprehensive backtests on all strategies"""
    
    logger.info("=" * 80)
    logger.info("COMPREHENSIVE STRATEGY BACKTESTING WITH ALPHA VANTAGE DATA")
    logger.info("=" * 80)
    
    backtester = StrategyBacktester()
    
    # Get test dates from settings
    settings = TradingBotSettings('settings.txt')
    start_date = settings.get('TESTING', 'start_date', '2024-01-01')
    end_date = settings.get('TESTING', 'end_date', '2025-10-03')
    
    logger.info(f"Test Period: {start_date} to {end_date}")
    
    # Load data for the specified test period
    df = backtester.load_av_data(start_date=start_date, end_date=end_date)
    
    # Check data quality
    logger.info(f"\nData Quality Check:")
    logger.info(f"  Total candles: {len(df)}")
    logger.info(f"  Date range: {df['timestamp'].min()} to {df['timestamp'].max()}")
    
    # Count market close candles
    close_candles = df[(df['timestamp'].dt.hour == 15) & (df['timestamp'].dt.minute == 55)]
    logger.info(f"  Market close candles (15:55 ET): {len(close_candles)}")
    
    # Test configurations
    test_configs = [
        ('all_signals', True, "All 6 Signals WITH Protection"),
        ('all_signals', False, "All 6 Signals NO Protection"),
        ('two_rsi_only', True, "Two RSI WITH Protection"),
        ('two_rsi_only', False, "Two RSI NO Protection"),
    ]
    
    results = []
    
    logger.info("\n" + "=" * 80)
    logger.info("RUNNING BACKTESTS")
    logger.info("=" * 80)
    
    for strategy_mode, enable_protection, description in test_configs:
        stats, trades = backtester.run_backtest(
            df, 
            strategy_mode, 
            enable_protection,
            start_balance=500.0,
            monthly_top_up=100.0
        )
        
        results.append({
            'description': description,
            'strategy': strategy_mode,
            'protection': enable_protection,
            **stats
        })
    
    # Display results
    logger.info("\n" + "=" * 80)
    logger.info("BACKTEST RESULTS SUMMARY")
    logger.info("=" * 80)
    
    logger.info("\n%-40s | %12s | %8s | %8s | %8s" % 
                ("Strategy", "Final Balance", "Win Rate", "Max DD", "Trades"))
    logger.info("-" * 90)
    
    for result in results:
        logger.info("%-40s | $%11.2f | %7.1f%% | %7.1f%% | %7d" % (
            result['description'],
            result['final_balance'],
            result['win_rate'],
            result['max_drawdown'],
            result['total_trades']
        ))
    
    # Compare with expected results
    logger.info("\n" + "=" * 80)
    logger.info("COMPARISON WITH EXPECTED RESULTS")
    logger.info("=" * 80)
    
    expected = {
        "All 6 Signals WITH Protection": 699074,
        "All 6 Signals NO Protection": 376004,
        "Two RSI WITH Protection": 485948,
        "Two RSI NO Protection": 348803
    }
    
    for result in results:
        expected_balance = expected.get(result['description'], 0)
        actual_balance = result['final_balance']
        difference = actual_balance - expected_balance
        pct_diff = (difference / expected_balance * 100) if expected_balance > 0 else 0
        
        status = "✅" if abs(pct_diff) < 10 else "⚠️"
        
        logger.info(f"\n{result['description']}:")
        logger.info(f"  Expected: ${expected_balance:,.0f}")
        logger.info(f"  Actual:   ${actual_balance:,.2f}")
        logger.info(f"  Diff:     ${difference:,.2f} ({pct_diff:+.1f}%)")
        logger.info(f"  Status:   {status}")
    
    # Detailed analysis of best performer
    best_result = max(results, key=lambda x: x['final_balance'])
    
    logger.info("\n" + "=" * 80)
    logger.info("BEST PERFORMING STRATEGY")
    logger.info("=" * 80)
    logger.info(f"\n{best_result['description']}:")
    logger.info(f"  Final Balance:  ${best_result['final_balance']:,.2f}")
    logger.info(f"  Total Return:   {best_result['total_return']:.1f}%")
    logger.info(f"  Win Rate:       {best_result['win_rate']:.1f}%")
    logger.info(f"  Total Trades:   {best_result['total_trades']}")
    logger.info(f"  Winning Trades: {best_result['winning_trades']}")
    logger.info(f"  Losing Trades:  {best_result['losing_trades']}")
    logger.info(f"  Avg Win:        ${best_result['avg_win']:.2f}")
    logger.info(f"  Avg Loss:       ${best_result['avg_loss']:.2f}")
    logger.info(f"  Max Drawdown:   {best_result['max_drawdown']:.1f}%")
    
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION COMPLETE")
    logger.info("=" * 80)

if __name__ == '__main__':
    main()
