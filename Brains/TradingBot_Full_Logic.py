#!/usr/bin/env python3
"""
COMPLETE TRADING BOT WITH FULL CALCULATION LOGIC
This file contains ALL the actual calculations and logic from Test3/Test5

THIS IS THE REAL IMPLEMENTATION - Not just results!
"""

import os
import sqlite3
from datetime import datetime, time as dt_time, timedelta
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional

# ==============================================================================
# CONFIGURATION (For GUI Integration)
# ==============================================================================

CONFIG = {
    # Strategy Selection
    'strategy': 'all_signals',  # 'all_signals', 'two_rsi_only', 'custom'
    
    # Individual Signals (if custom)
    'custom_signals': ['rsi_oversold', 'rsi_bullish_cross_50'],
    
    # Protection Settings
    'enable_crash_protection': True,
    
    # Crash Protection Parameters
    'crash_protection': {
        'timeframe_days': 3,      # Days to look back
        'dd_threshold': -10,       # Drawdown threshold (%)
        'rsi_bottom': 20,          # RSI level for bottom detection
        'vol_spike': 1.5,          # Volume spike multiplier
        'recovery_threshold': -3,  # Recovery improvement (%)
    },
    
    # Financial Settings
    'start_balance': 500.0,
    'monthly_top_up': 100.0,
    'invest_pct': 0.99,  # Use 99% of balance per trade
    
    # Date Range
    'start_date': '2024-01-01',
    'end_date': '2025-10-05',
    
    # Database
    'db_path': 'database_av.db',
    'table': 'TECL_av_5min',
    
    # Trading Times
    'entry_time': '15:59:45',  # Enter 15 seconds before market close
    'exit_time': '15:59:30',    # Exit 30 seconds before market close
}

# Signal Definitions with Parameters
SIGNAL_CONFIGS = {
    'rsi_oversold': {
        'leverage': 10.0,
        'stop_loss_pct': 3.5,
        'period': 7,
        'threshold': 25,
        'win_rate': 80.0
    },
    'rsi_bullish_cross_50': {
        'leverage': 5.0,
        'stop_loss_pct': 10.0,
        'period': 7,
        'win_rate': 63.0
    },
    'bb_lower_break': {
        'leverage': 10.0,
        'stop_loss_pct': 3.5,
        'period': 14,
        'std_dev': 1.5,
        'win_rate': 80.0
    },
    'price_above_vwap': {
        'leverage': 4.0,
        'stop_loss_pct': 8.0,
        'threshold': -0.01,
        'win_rate': 0.0
    },
    'roc_below_threshold': {
        'leverage': 5.0,
        'stop_loss_pct': 7.5,
        'period': 10,
        'threshold': -5,
        'win_rate': 0.0
    },
    'macd_positive': {
        'leverage': 5.0,
        'stop_loss_pct': 4.0,
        'fast_period': 13,
        'slow_period': 30,
        'signal_period': 9,
        'threshold': 0.05,
        'win_rate': 0.0
    }
}

# ==============================================================================
# CORE CALCULATION FUNCTIONS
# ==============================================================================

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Calculate RSI (Relative Strength Index)"""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_bollinger_bands(prices: pd.Series, period: int = 14, std_dev: float = 2.0) -> Dict:
    """Calculate Bollinger Bands"""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return {'sma': sma, 'upper': upper, 'lower': lower}

def calculate_vwap(prices: pd.Series, volumes: pd.Series) -> pd.Series:
    """Calculate VWAP (Volume Weighted Average Price)"""
    pv = prices * volumes
    cumulative_pv = pv.cumsum()
    cumulative_volume = volumes.cumsum()
    vwap = cumulative_pv / cumulative_volume
    return vwap

def calculate_roc(prices: pd.Series, period: int = 10) -> pd.Series:
    """Calculate Rate of Change"""
    roc = ((prices - prices.shift(period)) / prices.shift(period)) * 100
    return roc

def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict:
    """Calculate MACD"""
    exp1 = prices.ewm(span=fast, adjust=False).mean()
    exp2 = prices.ewm(span=slow, adjust=False).mean()
    macd_line = exp1 - exp2
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return {'macd': macd_line, 'signal': signal_line, 'histogram': histogram}

# ==============================================================================
# SIGNAL DETECTION FUNCTIONS
# ==============================================================================

def check_rsi_oversold(df: pd.DataFrame, idx: int, period: int = 7, threshold: float = 25) -> bool:
    """Check if RSI is oversold"""
    if len(df) < period + 1:
        return False
    rsi = calculate_rsi(df['closePrice'], period)
    return rsi.iloc[idx] < threshold if not pd.isna(rsi.iloc[idx]) else False

def check_rsi_bullish_cross_50(df: pd.DataFrame, idx: int, period: int = 7) -> bool:
    """Check if RSI crosses above 50"""
    if len(df) < period + 2 or idx < 1:
        return False
    rsi = calculate_rsi(df['closePrice'], period)
    if pd.isna(rsi.iloc[idx]) or pd.isna(rsi.iloc[idx-1]):
        return False
    return rsi.iloc[idx] > 50 and rsi.iloc[idx-1] <= 50

def check_bb_lower_break(df: pd.DataFrame, idx: int, period: int = 14, std_dev: float = 1.5) -> bool:
    """Check if price breaks below lower Bollinger Band"""
    if len(df) < period:
        return False
    bb = calculate_bollinger_bands(df['closePrice'], period, std_dev)
    lower = bb['lower'].iloc[idx]
    if pd.isna(lower):
        return False
    return df['closePrice'].iloc[idx] < lower

def check_price_above_vwap(df: pd.DataFrame, idx: int, threshold: float = -0.01) -> bool:
    """Check if price is above VWAP by threshold"""
    if len(df) < 2:
        return False
    vwap = calculate_vwap(df['closePrice'], df['lastTradedVolume'])
    if pd.isna(vwap.iloc[idx]):
        return False
    return df['closePrice'].iloc[idx] > vwap.iloc[idx] * (1 + threshold)

def check_roc_below_threshold(df: pd.DataFrame, idx: int, period: int = 10, threshold: float = -5) -> bool:
    """Check if ROC is below threshold"""
    if len(df) < period + 1:
        return False
    roc = calculate_roc(df['closePrice'], period)
    if pd.isna(roc.iloc[idx]):
        return False
    return roc.iloc[idx] < threshold

def check_macd_positive(df: pd.DataFrame, idx: int, fast: int = 13, slow: int = 30, 
                        signal_period: int = 9, threshold: float = 0.05) -> bool:
    """Check if MACD histogram is positive above threshold"""
    if len(df) < slow + signal_period:
        return False
    macd = calculate_macd(df['closePrice'], fast, slow, signal_period)
    hist = macd['histogram'].iloc[idx]
    if pd.isna(hist):
        return False
    return hist > threshold

# Signal checking functions map
SIGNAL_FUNCTIONS = {
    'rsi_oversold': check_rsi_oversold,
    'rsi_bullish_cross_50': check_rsi_bullish_cross_50,
    'bb_lower_break': check_bb_lower_break,
    'price_above_vwap': check_price_above_vwap,
    'roc_below_threshold': check_roc_below_threshold,
    'macd_positive': check_macd_positive,
}

# ==============================================================================
# CRASH PROTECTION LOGIC
# ==============================================================================

def calculate_daily_indicators(df: pd.DataFrame, timeframe_days: int) -> pd.DataFrame:
    """
    Calculate daily indicators for crash detection
    This is the EXACT logic from Test3
    """
    # Group by date for daily calculations
    daily_data = df.groupby('date').agg({
        'closePrice': 'last',
        'highPrice': 'max',
        'lowPrice': 'min',
        'lastTradedVolume': 'sum'
    }).reset_index()
    
    # Calculate rolling peak and drawdown
    lookback = max(1, int(timeframe_days))
    daily_data['peak'] = daily_data['closePrice'].rolling(window=lookback, min_periods=1).max()
    daily_data['drawdown'] = ((daily_data['closePrice'] - daily_data['peak']) / daily_data['peak']) * 100
    
    # Calculate RSI on daily data
    daily_data['rsi'] = calculate_rsi(daily_data['closePrice'], period=14)
    
    # Volume analysis
    daily_data['vol_avg'] = daily_data['lastTradedVolume'].rolling(window=20, min_periods=1).mean()
    daily_data['vol_ratio'] = daily_data['lastTradedVolume'] / daily_data['vol_avg']
    
    # Recovery detection (improvement in drawdown)
    daily_data['dd_improvement'] = daily_data['drawdown'].rolling(window=5).apply(
        lambda x: x.iloc[-1] - x.iloc[0] if len(x) == 5 else 0, raw=False
    )
    
    return daily_data

def should_block_trade(daily_indicators: pd.DataFrame, current_date, params: Dict) -> Tuple[bool, str, bool]:
    """
    Determine if trade should be blocked based on crash protection
    Returns: (should_block, reason, is_bottom_detected)
    """
    # Find the row for current date
    date_data = daily_indicators[daily_indicators['date'] == current_date]
    if date_data.empty:
        return False, "no_data", False
    
    row = date_data.iloc[0]
    
    # Check if in significant drawdown
    in_drawdown = row['drawdown'] < params['dd_threshold']
    
    # Check for bottom detection (oversold + volume spike)
    is_bottom = False
    if not pd.isna(row['rsi']) and not pd.isna(row['vol_ratio']):
        is_bottom = (row['rsi'] < params['rsi_bottom'] and 
                    row['vol_ratio'] > params['vol_spike'])
    
    # Check for recovery (drawdown improving)
    is_recovering = False
    if not pd.isna(row['dd_improvement']):
        is_recovering = row['dd_improvement'] > params['recovery_threshold']
    
    # Decision logic
    should_block = in_drawdown and not is_bottom and not is_recovering
    
    reason = ""
    if should_block:
        reason = f"drawdown_{row['drawdown']:.1f}%"
    elif is_bottom:
        reason = "bottom_detected"
    elif is_recovering:
        reason = "recovering"
    
    return should_block, reason, is_bottom

# ==============================================================================
# TRADING COST CALCULATIONS
# ==============================================================================

def calculate_trading_costs(notional_value: float, direction: str = 'long', is_overnight: bool = True) -> float:
    """
    Calculate realistic trading costs
    - Spread: 0.1% each way
    - Commission: 0.02% each way  
    - Overnight financing: 0.01% per day if held overnight
    """
    spread_cost = notional_value * 0.001  # 0.1% spread
    commission = notional_value * 0.0002   # 0.02% commission
    
    overnight_cost = 0
    if is_overnight:
        # Approximate overnight financing cost
        overnight_cost = notional_value * 0.0001  # 0.01% per night
    
    total_cost = spread_cost + commission + overnight_cost
    return total_cost

# ==============================================================================
# MAIN TRADING ENGINE
# ==============================================================================

class CompleteTradingBot:
    """
    Complete trading bot with all calculation logic
    """
    
    def __init__(self, config: Dict = None):
        self.config = config or CONFIG
        self.df = None
        self.trades = []
        
    def load_data(self) -> pd.DataFrame:
        """Load data from database"""
        conn = sqlite3.connect(self.config['db_path'])
        query = f"SELECT * FROM {self.config['table']}"
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        # Process timestamps
        if 'timestamp' in df.columns:
            df['snapshotTime'] = pd.to_datetime(df['timestamp'])
        elif 'snapshotTime' in df.columns:
            df['snapshotTime'] = pd.to_datetime(df['snapshotTime'])
        
        # Filter by date range
        start = pd.to_datetime(self.config['start_date'])
        end = pd.to_datetime(self.config['end_date']) + timedelta(days=1)
        df = df[(df['snapshotTime'] >= start) & (df['snapshotTime'] < end)]
        
        # Add helper columns
        df['date'] = df['snapshotTime'].dt.date
        df['time'] = df['snapshotTime'].dt.time
        
        # Ensure price columns exist
        if 'open' in df.columns and 'openPrice' not in df.columns:
            df['openPrice'] = df['open']
        if 'high' in df.columns and 'highPrice' not in df.columns:
            df['highPrice'] = df['high']
        if 'low' in df.columns and 'lowPrice' not in df.columns:
            df['lowPrice'] = df['low']
        if 'close' in df.columns and 'closePrice' not in df.columns:
            df['closePrice'] = df['close']
        if 'volume' in df.columns and 'lastTradedVolume' not in df.columns:
            df['lastTradedVolume'] = df['volume']
        
        self.df = df.sort_values('snapshotTime').reset_index(drop=True)
        return self.df
    
    def get_active_signals(self) -> List[str]:
        """Get list of signals to use based on configuration"""
        if self.config['strategy'] == 'all_signals':
            return list(SIGNAL_CONFIGS.keys())
        elif self.config['strategy'] == 'two_rsi_only':
            return ['rsi_oversold', 'rsi_bullish_cross_50']
        elif self.config['strategy'] == 'custom':
            return self.config['custom_signals']
        return []
    
    def check_signals(self, df: pd.DataFrame) -> Dict[str, bool]:
        """Check which signals are firing"""
        active_signals = self.get_active_signals()
        fired_signals = {}
        idx = len(df) - 1
        
        for signal in active_signals:
            if signal in SIGNAL_FUNCTIONS and signal in SIGNAL_CONFIGS:
                func = SIGNAL_FUNCTIONS[signal]
                params = SIGNAL_CONFIGS[signal]
                
                # Call the appropriate checking function with parameters
                if signal == 'rsi_oversold':
                    fired = func(df, idx, params['period'], params['threshold'])
                elif signal == 'rsi_bullish_cross_50':
                    fired = func(df, idx, params['period'])
                elif signal == 'bb_lower_break':
                    fired = func(df, idx, params['period'], params['std_dev'])
                elif signal == 'price_above_vwap':
                    fired = func(df, idx, params['threshold'])
                elif signal == 'roc_below_threshold':
                    fired = func(df, idx, params['period'], params.get('threshold', -5))
                elif signal == 'macd_positive':
                    fired = func(df, idx, params['fast_period'], params['slow_period'],
                               params['signal_period'], params['threshold'])
                else:
                    fired = False
                
                fired_signals[signal] = fired
        
        return fired_signals
    
    def select_best_signal(self, fired_signals: Dict[str, bool]) -> Tuple[str, Dict]:
        """Select best signal when multiple fire (highest win rate)"""
        best_signal = None
        best_config = None
        best_win_rate = 0
        
        for signal, is_firing in fired_signals.items():
            if is_firing and signal in SIGNAL_CONFIGS:
                config = SIGNAL_CONFIGS[signal]
                if config['win_rate'] > best_win_rate:
                    best_win_rate = config['win_rate']
                    best_signal = signal
                    best_config = config
        
        return best_signal, best_config
    
    def get_price_at_time(self, day_candles: pd.DataFrame, target_time: dt_time, price_type: str = 'closePrice'):
        """Get price at specific time"""
        # Find candle closest to target time
        target_ts = pd.Timestamp.combine(day_candles.iloc[0]['date'], target_time)
        time_diffs = (day_candles['snapshotTime'] - target_ts).abs()
        
        if time_diffs.min() <= timedelta(minutes=5):  # Within 5 minutes
            closest_idx = time_diffs.idxmin()
            return day_candles.loc[closest_idx, price_type]
        return None
    
    def run_backtest(self) -> Dict:
        """
        Run complete backtest with all calculations
        THIS IS THE ACTUAL TRADING LOGIC
        """
        if self.df is None:
            self.load_data()
        
        df = self.df
        
        # Initialize tracking variables
        balance = self.config['start_balance']
        starting_balance = balance
        monthly_top_up = self.config['monthly_top_up']
        invest_pct = self.config['invest_pct']
        total_contributions = 0
        
        # Parse trading times
        entry_time = dt_time.fromisoformat(self.config['entry_time'])
        exit_time = dt_time.fromisoformat(self.config['exit_time'])
        
        # Get trading days (weekdays only)
        all_dates = sorted(df['date'].unique())
        trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
        
        # Setup monthly contribution dates (first trading day of each month)
        monthly_groups = {}
        for d in trading_days:
            key = (d.year, d.month)
            if key not in monthly_groups:
                monthly_groups[key] = []
            monthly_groups[key].append(d)
        contribution_dates = [days[0] for days in monthly_groups.values() if len(days) > 10]
        
        # Calculate crash protection indicators if enabled
        daily_indicators = None
        if self.config['enable_crash_protection']:
            daily_indicators = calculate_daily_indicators(df, self.config['crash_protection']['timeframe_days'])
        
        # Trading variables
        current_position = None
        trades = []
        blocked_trades = 0
        
        # MAIN TRADING LOOP
        for current_date in trading_days:
            
            # Monthly contribution
            if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
                balance += monthly_top_up
                total_contributions += monthly_top_up
            
            # Get candles for current day
            day_candles = df[df['date'] == current_date].copy()
            if day_candles.empty:
                continue
            
            # ========== EXIT LOGIC ==========
            if current_position is not None:
                sl_pct = current_position['stop_loss_pct']
                stop_price = current_position['entry_price'] * (1 - sl_pct / 100)
                stop_hit = False
                exit_price = None
                exit_time_actual = None
                
                # Check for stop loss throughout the day (including after-hours)
                for _, candle in day_candles.iterrows():
                    if candle['lowPrice'] <= stop_price:
                        stop_hit = True
                        exit_price = stop_price
                        exit_time_actual = candle['snapshotTime']
                        exit_reason = 'STOP_LOSS'
                        break
                
                # If no stop loss, exit at normal time
                if not stop_hit:
                    exit_price = self.get_price_at_time(day_candles, exit_time, 'closePrice')
                    if exit_price is None:
                        exit_price = current_position['entry_price']
                    exit_reason = 'NORMAL_EXIT'
                
                # Calculate P&L
                price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                gross_pnl = current_position['notional_value'] * price_change_pct
                
                # Calculate trading costs
                is_overnight = current_position['entry_date'] != current_date
                fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight)
                
                net_pnl = gross_pnl - fees
                balance += net_pnl
                
                # Record trade
                trades.append({
                    'entry_date': current_position['entry_date'],
                    'entry_price': current_position['entry_price'],
                    'exit_date': current_date,
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'signal': current_position['signal'],
                    'leverage': current_position['leverage'],
                    'stop_loss_pct': sl_pct,
                    'gross_pnl': gross_pnl,
                    'fees': fees,
                    'net_pnl': net_pnl,
                    'balance_after': balance
                })
                
                current_position = None
            
            # ========== ENTRY LOGIC ==========
            if current_position is None and balance > 0:
                
                # Get historical data up to current date
                hist = df[df['date'] <= current_date]
                
                # Check crash protection
                if self.config['enable_crash_protection'] and daily_indicators is not None:
                    should_block, block_reason, is_bottom = should_block_trade(
                        daily_indicators, current_date, self.config['crash_protection']
                    )
                    if should_block:
                        blocked_trades += 1
                        continue
                
                # Check which signals are firing
                fired_signals = self.check_signals(hist)
                
                # Select best signal
                best_signal, signal_config = self.select_best_signal(fired_signals)
                
                if best_signal is not None:
                    # Get entry price
                    entry_price = self.get_price_at_time(day_candles, entry_time, 'closePrice')
                    
                    if entry_price is not None:
                        # Get leverage and stop loss
                        leverage = signal_config['leverage']
                        stop_loss_pct = signal_config['stop_loss_pct']
                        
                        # Calculate position size
                        notional_value = balance * invest_pct * leverage
                        
                        # Check for same-day stop loss in after-hours
                        same_day_exit = False
                        after_entry = day_candles[day_candles['time'] > entry_time]
                        stop_price = entry_price * (1 - stop_loss_pct / 100)
                        
                        for _, candle in after_entry.iterrows():
                            if candle['lowPrice'] <= stop_price:
                                # Same day stop loss hit
                                exit_price = stop_price
                                price_change_pct = (exit_price - entry_price) / entry_price
                                gross_pnl = notional_value * price_change_pct
                                fees = calculate_trading_costs(notional_value, 'long', False)
                                net_pnl = gross_pnl - fees
                                balance += net_pnl
                                
                                trades.append({
                                    'entry_date': current_date,
                                    'entry_price': entry_price,
                                    'exit_date': current_date,
                                    'exit_price': exit_price,
                                    'exit_reason': 'STOP_LOSS_SAME_DAY',
                                    'signal': best_signal,
                                    'leverage': leverage,
                                    'stop_loss_pct': stop_loss_pct,
                                    'gross_pnl': gross_pnl,
                                    'fees': fees,
                                    'net_pnl': net_pnl,
                                    'balance_after': balance
                                })
                                same_day_exit = True
                                break
                        
                        # If not stopped out same day, hold position
                        if not same_day_exit:
                            current_position = {
                                'entry_date': current_date,
                                'entry_price': entry_price,
                                'notional_value': notional_value,
                                'leverage': leverage,
                                'stop_loss_pct': stop_loss_pct,
                                'signal': best_signal
                            }
        
        # Calculate final metrics
        self.trades = trades
        final_balance = balance if balance > 0 else 0
        
        # Calculate performance metrics
        if trades:
            wins = [t for t in trades if t['net_pnl'] > 0]
            losses = [t for t in trades if t['net_pnl'] <= 0]
            win_rate = (len(wins) / len(trades)) * 100
            
            # Calculate max drawdown
            peak = starting_balance
            max_dd = 0
            min_balance = starting_balance
            
            for trade in trades:
                if trade['balance_after'] > peak:
                    peak = trade['balance_after']
                if trade['balance_after'] < min_balance:
                    min_balance = trade['balance_after']
                dd = (peak - trade['balance_after']) / peak * 100
                max_dd = max(max_dd, dd)
        else:
            win_rate = 0
            max_dd = 0
            min_balance = starting_balance
        
        return {
            'final_balance': final_balance,
            'starting_balance': starting_balance,
            'total_return_pct': ((final_balance - starting_balance - total_contributions) / starting_balance) * 100,
            'total_trades': len(trades),
            'blocked_trades': blocked_trades,
            'win_rate': win_rate,
            'max_drawdown_pct': -max_dd,
            'min_balance': min_balance,
            'total_contributions': total_contributions,
            'trades': trades  # Full trade history with all details
        }

# ==============================================================================
# DEMONSTRATION
# ==============================================================================

def main():
    """Demonstrate the complete trading bot"""
    print("=" * 80)
    print("COMPLETE TRADING BOT WITH FULL CALCULATION LOGIC")
    print("=" * 80)
    print("\nThis file contains ALL the actual calculations from Test3/Test5")
    print("Every indicator, signal, and protection calculation is here!\n")
    
    # Create bot
    bot = CompleteTradingBot(CONFIG)
    
    print("📊 Loading data from database...")
    bot.load_data()
    print(f"✅ Loaded {len(bot.df):,} candles")
    
    print(f"\n📋 Configuration:")
    print(f"  Strategy: {CONFIG['strategy']}")
    print(f"  Crash Protection: {'ENABLED' if CONFIG['enable_crash_protection'] else 'DISABLED'}")
    print(f"  Start Balance: ${CONFIG['start_balance']}")
    print(f"  Monthly Top-up: ${CONFIG['monthly_top_up']}")
    
    print("\n🔄 Running backtest with FULL calculations...")
    results = bot.run_backtest()
    
    print("\n" + "=" * 80)
    print("📈 RESULTS")
    print("=" * 80)
    print(f"  Final Balance:     ${results['final_balance']:,.2f}")
    print(f"  Total Return:      {results['total_return_pct']:,.1f}%")
    print(f"  Total Trades:      {results['total_trades']}")
    print(f"  Blocked (Crash):   {results['blocked_trades']}")
    print(f"  Win Rate:          {results['win_rate']:.1f}%")
    print(f"  Max Drawdown:      {results['max_drawdown_pct']:.1f}%")
    print(f"  Min Balance:       ${results['min_balance']:,.2f}")
    
    # Show some example trades
    if results['trades']:
        print("\n📊 Sample Trades (First 3):")
        for i, trade in enumerate(results['trades'][:3], 1):
            print(f"\n  Trade {i}:")
            print(f"    Signal: {trade['signal']}")
            print(f"    Entry: ${trade['entry_price']:.2f} on {trade['entry_date']}")
            print(f"    Exit:  ${trade['exit_price']:.2f} on {trade['exit_date']}")
            print(f"    Leverage: {trade['leverage']}x")
            print(f"    P&L: ${trade['net_pnl']:.2f}")
            print(f"    Balance After: ${trade['balance_after']:.2f}")
    
    print("\n💡 KEY FEATURES IN THIS FILE:")
    print("  ✓ All 6 signal calculations (RSI, BB, VWAP, ROC, MACD)")
    print("  ✓ Complete crash protection logic")
    print("  ✓ Trading cost calculations")
    print("  ✓ Position sizing with leverage")
    print("  ✓ Stop loss monitoring (including after-hours)")
    print("  ✓ Monthly contribution logic")
    print("  ✓ Full trade history with all details")
    
    return results

if __name__ == '__main__':
    results = main()
