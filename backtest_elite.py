#!/usr/bin/env python3
"""
Elite Model Backtest - Exact copy of Test1.py and Test3.py logic
This matches the PROVEN system that achieves $476k
"""

import os
import sys
import logging
from datetime import time as dt_time, datetime
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from bot.settings import TradingBotSettings
from Brains.strategy_signals import get_strategy_analysis, SIGNAL_CONFIGS
from indicators import create_indicator_library
from focused_optimizer import calculate_trading_costs, get_price_at_time

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

# Elite model strategy definitions (with 0.0 win_rate for low priority signals)
ELITE_STRATEGIES = {
    'rsi_oversold': {
        'leverage': 10.0, 'period': 7, 'stop_loss_pct': 3.5, 'threshold': 25,
        'win_rate': 80.0, 'final_balance': 20680.58, 'sharpe_ratio': 3.59
    },
    'bb_lower_break': {
        'leverage': 10.0, 'period': 20, 'std_dev': 2.5, 'stop_loss_pct': 3.5,
        'win_rate': 80.0, 'final_balance': 12937.44, 'sharpe_ratio': 3.33
    },
    'rsi_bullish_cross_50': {
        'leverage': 5.0, 'period': 7, 'stop_loss_pct': 10.0,
        'win_rate': 63.0, 'final_balance': 14947.13, 'sharpe_ratio': 2.74
    },
    'price_above_vwap': {
        'leverage': 4.0, 'threshold': -0.01, 'stop_loss_pct': 8.0,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Low priority
    },
    'roc_below_threshold': {
        'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5, 'threshold': -5,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Low priority
    },
    'macd_positive': {
        'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 
        'threshold': 0.05, 'stop_loss_pct': 4.0,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Low priority
    }
}

def load_av_data(start_date=None, end_date=None) -> pd.DataFrame:
    """Load Alpha Vantage data from database"""
    import sqlite3
    
    settings = TradingBotSettings()
    
    # Get dates from settings if not provided
    if not start_date:
        start_date = settings.get('TESTING', 'start_date', fallback='2024-01-01')
    if not end_date:
        end_date = settings.get('TESTING', 'end_date', fallback='2025-10-03')
    
    # Connect to AV database
    db_path = 'database_av.db'
    table_name = 'TECL_av_5min'
    
    conn = sqlite3.connect(db_path)
    try:
        # Load data
        query = f"""
        SELECT timestamp, open, high, low, close, volume
        FROM {table_name}
        ORDER BY timestamp ASC
        """
        df = pd.read_sql_query(query, conn)
    finally:
        conn.close()
    
    if df.empty:
        raise RuntimeError(f"No data found in {table_name}")
    
    # Convert timestamp and rename columns
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['snapshotTime'] = df['timestamp']
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.time
    
    df.rename(columns={
        'open': 'openPrice',
        'high': 'highPrice',
        'low': 'lowPrice',
        'close': 'closePrice',
        'volume': 'lastTradedVolume'
    }, inplace=True)
    
    # Filter by date range
    if start_date:
        start = pd.to_datetime(start_date)
        df = df[df['snapshotTime'] >= start]
    if end_date:
        end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
        df = df[df['snapshotTime'] < end]
    
    return df.sort_values('snapshotTime').reset_index(drop=True)

def nearest_candle(candles: pd.DataFrame, target_time: dt_time):
    """Find nearest candle to target time"""
    if candles.empty:
        return None
    target_ts = pd.Timestamp.combine(candles.iloc[0]['date'], target_time)
    diffs = (candles['snapshotTime'] - target_ts).abs()
    i = diffs.idxmin()
    if pd.isna(i):
        return None
    if diffs.loc[i].total_seconds() <= 300:
        return candles.loc[i]
    return None

def eval_signals_elite(hist: pd.DataFrame) -> Dict[str, bool]:
    """Evaluate signals using elite model's exact logic"""
    lib_today = create_indicator_library(hist)
    conds = lib_today.get_conditions()
    idx = len(hist) - 1
    fired = {}
    
    # RSI Oversold
    fired['rsi_oversold'] = False
    if 'rsi_oversold' in conds:
        try:
            fired['rsi_oversold'] = conds['rsi_oversold'](
                hist, idx, 
                period=ELITE_STRATEGIES['rsi_oversold']['period'], 
                threshold=ELITE_STRATEGIES['rsi_oversold']['threshold']
            )
        except Exception:
            pass
    
    # Bollinger Bands Lower Break
    fired['bb_lower_break'] = False
    if 'bb_lower_break' in conds:
        try:
            fired['bb_lower_break'] = conds['bb_lower_break'](
                hist, idx,
                period=ELITE_STRATEGIES['bb_lower_break']['period'],
                std_dev=ELITE_STRATEGIES['bb_lower_break']['std_dev']
            )
        except Exception:
            pass
    
    # RSI Bullish Cross 50
    fired['rsi_bullish_cross_50'] = False
    if 'rsi_bullish_cross_50' in conds:
        try:
            fired['rsi_bullish_cross_50'] = conds['rsi_bullish_cross_50'](
                hist, idx,
                period=ELITE_STRATEGIES['rsi_bullish_cross_50']['period']
            )
        except Exception:
            pass
    
    # Price Above VWAP
    fired['price_above_vwap'] = False
    if 'price_above_vwap' in conds:
        try:
            fired['price_above_vwap'] = conds['price_above_vwap'](
                hist, idx,
                threshold=ELITE_STRATEGIES['price_above_vwap']['threshold']
            )
        except Exception:
            pass
    
    # ROC Below Threshold
    fired['roc_below_threshold'] = False
    if 'roc_below_threshold' in conds:
        try:
            fired['roc_below_threshold'] = conds['roc_below_threshold'](
                hist, idx,
                period=ELITE_STRATEGIES['roc_below_threshold']['period'],
                threshold=ELITE_STRATEGIES['roc_below_threshold'].get('threshold', -5)
            )
        except Exception:
            pass
    
    # MACD Positive
    fired['macd_positive'] = False
    if 'macd_positive' in conds:
        try:
            fired['macd_positive'] = conds['macd_positive'](
                hist, idx,
                fast_period=ELITE_STRATEGIES['macd_positive']['fast_period'],
                slow_period=ELITE_STRATEGIES['macd_positive']['slow_period'],
                signal_period=ELITE_STRATEGIES['macd_positive']['signal_period'],
                threshold=ELITE_STRATEGIES['macd_positive']['threshold']
            )
        except Exception:
            pass
    
    return fired

def select_best_signal_elite(fired_signals: Dict[str, bool]) -> Tuple[str, Dict]:
    """Select signal with highest win_rate (priority) from fired signals"""
    fired_list = [s for s, v in fired_signals.items() if v]
    if not fired_list:
        return None, None
    
    # Sort by win_rate (descending), then by sharpe_ratio, then by final_balance
    best_signal = max(fired_list, key=lambda s: (
        ELITE_STRATEGIES[s]['win_rate'],
        ELITE_STRATEGIES[s]['sharpe_ratio'],
        ELITE_STRATEGIES[s]['final_balance']
    ))
    
    return best_signal, ELITE_STRATEGIES[best_signal]

def calculate_daily_indicators(df, timeframe_days=3):
    """Calculate indicators for crash detection"""
    # Group by date for daily aggregation
    agg_df = df.groupby('date').agg({
        'closePrice': 'last',
        'highPrice': 'max',
        'lowPrice': 'min',
        'lastTradedVolume': 'sum'
    })
    
    # Calculate rolling peak and drawdown
    lookback_periods = int(timeframe_days)
    agg_df['peak'] = agg_df['closePrice'].rolling(window=max(1, lookback_periods), min_periods=1).max()
    agg_df['drawdown'] = ((agg_df['closePrice'] - agg_df['peak']) / agg_df['peak']) * 100
    
    # Calculate RSI
    delta = agg_df['closePrice'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    agg_df['rsi'] = 100 - (100 / (1 + rs))
    
    # Volume analysis
    agg_df['vol_avg'] = agg_df['lastTradedVolume'].rolling(window=20, min_periods=1).mean()
    agg_df['vol_ratio'] = agg_df['lastTradedVolume'] / agg_df['vol_avg']
    
    # Recovery detection
    agg_df['dd_improvement'] = agg_df['drawdown'].rolling(window=5).apply(
        lambda x: x.iloc[-1] - x.iloc[0] if len(x) == 5 else 0, raw=False
    )
    
    return agg_df

def should_block_trade(daily_indicators, date, params):
    """Check if crash protection should block this trade"""
    if params is None or date not in daily_indicators.index:
        return False, "No protection"
    
    row = daily_indicators.loc[date]
    
    # Check for crash conditions
    if row['drawdown'] < params['dd_threshold']:
        # Check for bottom detection (override block)
        if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
            return False, f"BOTTOM DETECTED"
        
        # Check for recovery
        if row['dd_improvement'] > params['recovery_threshold']:
            return False, f"RECOVERY"
        
        # BLOCK the trade
        return True, f"CRASH PROTECTION"
    
    return False, "Normal"

def run_elite_backtest(df: pd.DataFrame, use_crash_protection: bool = False) -> Dict:
    """Run backtest using elite model's exact logic"""
    
    settings = TradingBotSettings()
    start_balance = 100.0  # Elite model uses 100, not 500!
    invest_pct = 0.99      # 99% investment
    monthly_top_up = 100.0
    
    # Best crash protection parameters from elite model
    crash_params = {
        'timeframe_days': 3,
        'dd_threshold': -10,
        'rsi_bottom': 20,
        'vol_spike': 1.5,
        'recovery_threshold': -3
    } if use_crash_protection else None
    
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
    
    balance = start_balance
    starting_balance = start_balance
    total_contributions = 0.0
    current_position = None
    trades: List[Dict] = []
    blocked_trades = 0
    
    # Calculate daily indicators if crash protection is enabled
    daily_indicators = None
    if crash_params is not None:
        daily_indicators = calculate_daily_indicators(df, crash_params['timeframe_days'])
    
    # Monthly contribution dates
    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]
    
    protection_str = "WITH crash protection" if use_crash_protection else "WITHOUT crash protection"
    logger.info(f"Running ELITE strategy {protection_str}...")
    
    for current_date in trading_days:
        # Monthly top-up
        if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up
            total_contributions += monthly_top_up
        
        day_candles = df[df['date'] == current_date].copy()
        if day_candles.empty:
            continue
        day_candles = day_candles.sort_values('snapshotTime').reset_index(drop=True)
        
        # Close prior position
        if current_position is not None:
            sl_pct = current_position['stop_loss_pct']
            stop_price = current_position['entry_price'] * (1 - sl_pct / 100)
            stop_hit = False
            
            # Check for stop loss through ALL candles (extended hours)
            market_hours = day_candles
            for _, c in market_hours.iterrows():
                if c['lowPrice'] <= stop_price:
                    stop_hit = True
                    exit_price = stop_price
                    exit_reason = 'STOP_LOSS'
                    break
            
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice')
                exit_reason = 'NORMAL_EXIT'
                if exit_price is None:
                    exit_price = current_position['entry_price']
                    exit_reason = 'NO_EXIT_PRICE'
            
            # ELITE MODEL P&L CALCULATION
            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross_pnl = current_position['notional_value'] * price_change_pct
            fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
            net_pnl = gross_pnl - fees
            balance += net_pnl  # Only add net P&L, not investment
            
            trades.append({
                'entry_date': current_position['entry_date'],
                'entry_price': current_position['entry_price'],
                'exit_date': current_date,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'leverage': current_position['leverage'],
                'stop_loss_pct': sl_pct,
                'notional_value': current_position['notional_value'],
                'pnl_gross': gross_pnl,
                'pnl_net': net_pnl,
                'balance_after': balance,
                'selected_signal': current_position['selected_signal']
            })
            current_position = None
        
        # Entry evaluation
        hist = df[df['date'] <= current_date]
        if hist.empty:
            continue
        
        fired = eval_signals_elite(hist)
        best_signal, signal_config = select_best_signal_elite(fired)
        
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if best_signal is None or entry_price is None or balance <= 0 or current_position is not None:
            continue
        
        # CRASH PROTECTION CHECK
        if crash_params is not None and daily_indicators is not None:
            should_block, reason = should_block_trade(daily_indicators, current_date, crash_params)
            if should_block:
                blocked_trades += 1
                continue
        
        leverage = signal_config['leverage']
        stop_loss_pct = signal_config['stop_loss_pct']
        notional_value = balance * invest_pct * leverage
        
        current_position = {
            'entry_date': current_date,
            'entry_price': entry_price,
            'notional_value': notional_value,
            'leverage': leverage,
            'stop_loss_pct': stop_loss_pct,
            'selected_signal': best_signal,
        }
        
        # Check same-day after-hours stop loss
        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME) & (day_candles['time'] <= dt_time(20, 0))]
        if not after_hours.empty:
            sl_same_day = entry_price * (1 - stop_loss_pct / 100)
            for _, c in after_hours.iterrows():
                if c['lowPrice'] <= sl_same_day:
                    exit_price = sl_same_day
                    price_change_pct = (exit_price - entry_price) / entry_price
                    gross_pnl = notional_value * price_change_pct
                    fees = calculate_trading_costs(notional_value, 'long', is_overnight=False)
                    net_pnl = gross_pnl - fees
                    balance += net_pnl
                    
                    trades.append({
                        'entry_date': current_date,
                        'entry_price': entry_price,
                        'exit_date': current_date,
                        'exit_price': exit_price,
                        'exit_reason': 'STOP_LOSS',
                        'leverage': leverage,
                        'stop_loss_pct': stop_loss_pct,
                        'notional_value': notional_value,
                        'pnl_gross': gross_pnl,
                        'pnl_net': net_pnl,
                        'balance_after': balance,
                        'selected_signal': best_signal
                    })
                    current_position = None
                    break
    
    final_balance = balance if balance > 0 else 0
    total_return_pct = ((final_balance - starting_balance - total_contributions) / starting_balance) * 100
    
    # Calculate metrics
    wins = [t for t in trades if t['pnl_net'] > 0]
    losses = [t for t in trades if t['pnl_net'] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    
    # Calculate drawdown
    balances = [starting_balance]
    for t in trades:
        balances.append(t['balance_after'])
    peak = starting_balance
    drawdowns = []
    for b in balances:
        peak = max(peak, b)
        dd = ((b - peak) / peak * 100) if peak > 0 else 0
        drawdowns.append(dd)
    max_drawdown = min(drawdowns) if drawdowns else 0
    
    # Signal distribution
    signal_counts = {}
    for t in trades:
        sig = t['selected_signal']
        signal_counts[sig] = signal_counts.get(sig, 0) + 1
    
    return {
        'final_balance': final_balance,
        'total_return_pct': total_return_pct,
        'total_contributions': total_contributions,
        'trades': len(trades),
        'blocked_trades': blocked_trades,
        'win_count': len(wins),
        'loss_count': len(losses),
        'win_rate': win_rate,
        'max_drawdown': max_drawdown,
        'signal_distribution': signal_counts
    }

def main():
    logger.info("=" * 80)
    logger.info("ELITE MODEL BACKTEST - Matching Proven System")
    logger.info("=" * 80)
    
    # Load data
    logger.info("Loading Alpha Vantage data...")
    df = load_av_data()
    logger.info(f"Loaded {len(df):,} candles")
    
    # Run without protection (baseline)
    logger.info("\n[1/2] Running WITHOUT crash protection (baseline)...")
    res_no_protection = run_elite_backtest(df, use_crash_protection=False)
    
    logger.info(f"Final Balance: ${res_no_protection['final_balance']:,.0f}")
    logger.info(f"Total Return: {res_no_protection['total_return_pct']:+.1f}%")
    logger.info(f"Trades: {res_no_protection['trades']}")
    logger.info(f"Win Rate: {res_no_protection['win_rate']:.1f}%")
    logger.info(f"Max Drawdown: {res_no_protection['max_drawdown']:.1f}%")
    
    # Signal distribution
    logger.info("Signal Distribution:")
    for signal, count in res_no_protection['signal_distribution'].items():
        logger.info(f"  {signal}: {count}")
    
    # Run with protection
    logger.info("\n[2/2] Running WITH crash protection...")
    res_with_protection = run_elite_backtest(df, use_crash_protection=True)
    
    logger.info(f"Final Balance: ${res_with_protection['final_balance']:,.0f}")
    logger.info(f"Total Return: {res_with_protection['total_return_pct']:+.1f}%")
    logger.info(f"Trades: {res_with_protection['trades']} (Blocked: {res_with_protection['blocked_trades']})")
    logger.info(f"Win Rate: {res_with_protection['win_rate']:.1f}%")
    logger.info(f"Max Drawdown: {res_with_protection['max_drawdown']:.1f}%")
    
    # Comparison
    logger.info("\n" + "=" * 80)
    logger.info("RESULTS COMPARISON")
    logger.info("=" * 80)
    
    logger.info(f"\nWITHOUT crash protection: ${res_no_protection['final_balance']:,.0f}")
    logger.info(f"WITH crash protection:    ${res_with_protection['final_balance']:,.0f}")
    
    improvement = ((res_with_protection['final_balance'] - res_no_protection['final_balance']) / 
                  res_no_protection['final_balance'] * 100)
    logger.info(f"\nCrash protection improvement: {improvement:+.1f}%")
    
    # Compare to elite model's results
    logger.info("\n" + "=" * 80)
    logger.info("VALIDATION vs ELITE MODEL")
    logger.info("=" * 80)
    
    elite_baseline = 303567  # From Test1.py
    elite_protected = 476408  # From Test3.py
    
    logger.info(f"\nBaseline (No Protection):")
    logger.info(f"  Elite Model:  ${elite_baseline:,.0f}")
    logger.info(f"  Our Result:   ${res_no_protection['final_balance']:,.0f}")
    diff_pct = ((res_no_protection['final_balance'] - elite_baseline) / elite_baseline * 100)
    logger.info(f"  Difference:   {diff_pct:+.1f}%")
    
    logger.info(f"\nWith Protection:")
    logger.info(f"  Elite Model:  ${elite_protected:,.0f}")
    logger.info(f"  Our Result:   ${res_with_protection['final_balance']:,.0f}")
    diff_pct = ((res_with_protection['final_balance'] - elite_protected) / elite_protected * 100)
    logger.info(f"  Difference:   {diff_pct:+.1f}%")

if __name__ == '__main__':
    main()
