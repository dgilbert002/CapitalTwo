"""
Test enhanced crash protection WITH smart bottom detection
This combines the best of both: gap detection + intelligent bottom fishing
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time
import sqlite3
from typing import Dict, Tuple
import logging

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(message)s')
logger = logging.getLogger(__name__)

# Import from test_all_proven_strategies.py
from test_all_proven_strategies import (
    eval_signals, 
    select_best_signal,
    calculate_daily_indicators as calc_daily_orig,
    load_data
)
from focused_optimizer import calculate_trading_costs, get_price_at_time
from Scripts.db_utils import load_settings
from Brains.strategy_signals import SIGNAL_CONFIGS

# Define strategy combinations
STRATEGIES = {
    'all_6_signals': {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50'],
        'bb_lower_break': SIGNAL_CONFIGS['bb_lower_break'],
        'price_above_vwap': SIGNAL_CONFIGS['price_above_vwap'],
        'roc_below_threshold': SIGNAL_CONFIGS['roc_below_threshold'],
        'macd_positive': SIGNAL_CONFIGS['macd_positive']
    },
    'two_rsi_only': {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50']
    },
    'test6': {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50'],
        'bb_lower_break': SIGNAL_CONFIGS['bb_lower_break'],
        'price_above_vwap': SIGNAL_CONFIGS['price_above_vwap'],
        'roc_below_threshold': SIGNAL_CONFIGS['roc_below_threshold'],
        'macd_positive': SIGNAL_CONFIGS['macd_positive'],
        'keltner_lower_break': SIGNAL_CONFIGS['keltner_lower_break'],
        'macd_histogram_negative': SIGNAL_CONFIGS['macd_histogram_negative']
    },
    'test7': {
        'rsi_oversold': SIGNAL_CONFIGS['rsi_oversold'],
        'rsi_bullish_cross_50': SIGNAL_CONFIGS['rsi_bullish_cross_50'],
        'bb_lower_break': SIGNAL_CONFIGS['bb_lower_break'],
        'price_above_vwap': SIGNAL_CONFIGS['price_above_vwap'],
        'roc_below_threshold': SIGNAL_CONFIGS['roc_below_threshold'],
        'macd_positive': SIGNAL_CONFIGS['macd_positive'],
        'keltner_lower_break': SIGNAL_CONFIGS['keltner_lower_break'],
        'macd_histogram_negative': SIGNAL_CONFIGS['macd_histogram_negative'],
        'macd_histogram_negative_v2': SIGNAL_CONFIGS['macd_histogram_negative_v2']
    }
}

# Entry/Exit times
ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

def calculate_enhanced_daily_indicators(df, timeframe_days=3):
    """Enhanced daily indicators including gap detection"""
    # Get original indicators
    daily_data = calc_daily_orig(df, timeframe_days)
    
    # Add gap calculation (CRITICAL FOR ENHANCED)
    # df['date'] is already a date, not datetime
    daily_close = df.groupby(df['date'])['closePrice'].last()
    daily_open = df.groupby(df['date'])['openPrice'].first()
    daily_data['prev_close'] = daily_close.shift(1)
    daily_data['gap'] = ((daily_open - daily_data['prev_close']) / daily_data['prev_close']) * 100
    
    # Add intraday range
    daily_high = df.groupby(df['date'])['highPrice'].max()
    daily_low = df.groupby(df['date'])['lowPrice'].min()
    daily_data['intraday_range'] = ((daily_high - daily_low) / daily_open) * 100
    
    # Add consecutive red days
    daily_returns = daily_close.pct_change()
    consecutive_red = []
    count = 0
    for ret in daily_returns:
        if pd.notna(ret) and ret < 0:
            count += 1
        else:
            count = 0
        consecutive_red.append(count)
    daily_data['consecutive_red'] = pd.Series(consecutive_red, index=daily_data.index)
    
    return daily_data

def should_block_trade_original(daily_indicators, date, params):
    """Original smart crash protection with bottom detection (from test_all_proven_strategies.py)"""
    if params is None or date not in daily_indicators.index:
        return False, "No data"
    
    row = daily_indicators.loc[date]
    
    # Check for crash conditions
    if row['drawdown'] < params['dd_threshold']:
        # Check for bottom detection (override block)
        if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
            return False, "BOTTOM DETECTED - allowing trade"  # Allow trade at bottom
        
        # Check for recovery
        if row['dd_improvement'] > params['recovery_threshold']:
            return False, "RECOVERY - allowing trade"  # Allow trade during recovery
        
        # BLOCK the trade
        return True, f"Crash protection: DD {row['drawdown']:.1f}%"
    
    return False, "Normal conditions"

def should_block_trade_enhanced(daily_indicators, date, params):
    """ENHANCED crash protection: gap detection + smart bottom detection"""
    if params is None or date not in daily_indicators.index:
        return False, "No data"
    
    row = daily_indicators.loc[date]
    
    # FIRST: Check for extreme gaps (highest priority)
    gap = row.get('gap', 0)
    if pd.notna(gap):
        if gap < -10.0:  # ONLY block EXTREME gaps (was -7)
            # Even with extreme gap, check for bottom
            if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
                return False, "Extreme gap but BOTTOM DETECTED - allowing"
            # Check if in strong drawdown already (don't double-punish)
            if row['drawdown'] < -20:
                return False, "Extreme gap but already in deep drawdown - allowing bottom fishing"
            return True, f"EXTREME GAP: {gap:.2f}%"
        elif gap < -7.0:  # Raised threshold from -5 to -7
            # ALWAYS allow if RSI is oversold (these often bounce)
            if row['rsi'] < 30:
                return False, "Major gap but RSI oversold - allowing"
            # Check if it's a bottom opportunity
            if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
                return False, "Major gap but BOTTOM DETECTED - allowing"
            # Check if we're in recovery
            if row.get('dd_improvement', 0) > params['recovery_threshold']:
                return False, "Gap but RECOVERY - allowing"
            # Only block if also in drawdown
            if row['drawdown'] < -5:
                return True, f"Major gap down: {gap:.2f}% with DD {row['drawdown']:.1f}%"
    
    # SECOND: Check multi-day weakness (made less aggressive)
    returns_5d = row.get('5d_return', 0)
    if pd.notna(returns_5d) and returns_5d < -20:  # Was -15, now -20
        # But allow if bottom detected
        if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
            return False, "5d decline but BOTTOM DETECTED - allowing"
        # Or if recovery started
        if row.get('dd_improvement', 0) > params['recovery_threshold']:
            return False, "5d decline but RECOVERY - allowing"
        # Allow if RSI oversold
        if row['rsi'] < 30:
            return False, "5d decline but RSI oversold - allowing"
        return True, f"5-day decline: {returns_5d:.2f}%"
    
    # THIRD: Check consecutive red days (made less aggressive)
    consecutive_red = row.get('consecutive_red', 0)
    if consecutive_red >= 4:  # Was 3, now 4
        returns_3d = row.get('3d_return', 0)
        if pd.notna(returns_3d) and returns_3d < -15:  # Was -10, now -15
            # Check for bottom
            if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
                return False, "Red days but BOTTOM DETECTED - allowing"
            # Allow if RSI oversold
            if row['rsi'] < 25:
                return False, "Red days but RSI very oversold - allowing"
            return True, f"{consecutive_red} consecutive red days: {returns_3d:.2f}%"
    
    # FOURTH: Intraday panic check (made less aggressive)
    intraday_range = row.get('intraday_range', 0)
    if pd.notna(intraday_range) and intraday_range > 15.0:  # Was 10, now 15
        if pd.notna(gap) and gap < -5.0:  # Was -3, now -5
            # Even in panic, check for bottom
            if row['rsi'] < params['rsi_bottom']:
                return False, "Panic but RSI oversold - allowing"
            # Only block if also in drawdown
            if row['drawdown'] < -10:
                return True, f"Panic selling: {intraday_range:.2f}% range"
    
    # FINALLY: Apply original smart crash protection
    if row['drawdown'] < params['dd_threshold']:
        # Check for bottom detection (override block)
        if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
            return False, "BOTTOM DETECTED - allowing trade"
        
        # Check for recovery
        if row['dd_improvement'] > params['recovery_threshold']:
            return False, "RECOVERY - allowing trade"
        
        # BLOCK the trade
        return True, f"Drawdown {row['drawdown']:.1f}% with RSI {row['rsi']:.1f}"
    
    return False, "Normal conditions"

def run_strategy_with_protection(df, strategies, strategy_name, protection_type='none'):
    """Run strategy with specified protection type"""
    
    # Load settings
    settings = load_settings()
    start_balance = float(settings.get('start_balance', 500))
    invest_pct = float(settings.get('invest_pct', 0.99))
    monthly_top_up = float(settings.get('monthly_top_up', 100))
    
    # Protection parameters
    crash_params = {
        'timeframe_days': 3,
        'dd_threshold': -10,
        'rsi_bottom': 20,
        'vol_spike': 1.5,
        'recovery_threshold': -3
    } if protection_type != 'none' else None
    
    # Calculate indicators based on protection type
    if protection_type == 'enhanced':
        daily_indicators = calculate_enhanced_daily_indicators(df, crash_params['timeframe_days'])
        should_block_func = should_block_trade_enhanced
    elif protection_type == 'original':
        daily_indicators = calc_daily_orig(df, crash_params['timeframe_days'])
        should_block_func = should_block_trade_original
    else:
        daily_indicators = None
        should_block_func = lambda x, y, z: (False, "No protection")
    
    # Initialize tracking
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
    
    balance = start_balance
    current_position = None
    trades = []
    blocked_trades = 0
    allowed_bottoms = 0
    blocked_reasons = {}
    
    # Track balance for drawdown
    peak_balance = start_balance
    max_drawdown = 0
    max_drawdown_date = None
    
    # Monthly top-up tracking
    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]
    
    for current_date in trading_days:
        # Monthly top-up
        if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up
        
        # Get day candles
        day_candles = df[df['date'] == current_date].copy()
        if day_candles.empty:
            continue
        day_candles['snapshotTime'] = day_candles['timestamp']
        day_candles['time'] = pd.to_datetime(day_candles['snapshotTime']).dt.time
        day_candles = day_candles.sort_values('snapshotTime').reset_index(drop=True)
        
        # Exit previous position
        if current_position:
            # Check stop-loss
            stop_hit = False
            for _, candle in day_candles.iterrows():
                if candle['lowPrice'] <= current_position['stop_loss']:
                    exit_price = current_position['stop_loss']
                    price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                    notional_value = current_position['notional_value']
                    gross_pnl = notional_value * price_change_pct
                    fees = calculate_trading_costs(notional_value, 'long', is_overnight=True)
                    net_pnl = gross_pnl - fees
                    balance += net_pnl
                    trades.append({
                        'entry_date': current_position['entry_date'],
                        'exit_date': current_date,
                        'pnl': net_pnl,
                        'signal': current_position['signal']
                    })
                    current_position = None
                    stop_hit = True
                    break
            
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice')
                if exit_price is None:
                    exit_price = current_position['entry_price']
                
                price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
                notional_value = current_position['notional_value']
                gross_pnl = notional_value * price_change_pct
                fees = calculate_trading_costs(notional_value, 'long', is_overnight=False)
                net_pnl = gross_pnl - fees
                balance += net_pnl
                
                trades.append({
                    'entry_date': current_position['entry_date'],
                    'exit_date': current_date,
                    'pnl': net_pnl,
                    'signal': current_position['signal']
                })
                current_position = None
        
        # Check for new entry
        if current_position is None:
            # Check crash protection
            if daily_indicators is not None and crash_params:
                should_block, reason = should_block_func(daily_indicators, current_date, crash_params)
                if should_block:
                    blocked_trades += 1
                    blocked_reasons[current_date] = reason
                    continue
                elif "BOTTOM" in reason or "RECOVERY" in reason:
                    allowed_bottoms += 1
            
            # Get historical data
            hist = df[df['date'] <= current_date].copy()
            
            # Evaluate signals
            fired = eval_signals(hist, strategies)
            best_signal, signal_config = select_best_signal(fired, strategies)
            
            entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
            if best_signal is None or entry_price is None or balance <= 0:
                continue
            
            # Enter position
            leverage = signal_config['leverage']
            stop_loss_pct = signal_config['stop_loss_pct']
            
            investment = balance * invest_pct
            notional_value = investment * leverage
            stop_loss = entry_price * (1 - stop_loss_pct / 100)
            
            current_position = {
                'entry_date': current_date,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'notional_value': notional_value,
                'signal': best_signal
            }
        
        # Update drawdown
        if balance > peak_balance:
            peak_balance = balance
        current_drawdown = ((peak_balance - balance) / peak_balance) * 100 if peak_balance > 0 else 0
        if current_drawdown > max_drawdown:
            max_drawdown = current_drawdown
            max_drawdown_date = current_date
    
    # Calculate statistics
    total_return = ((balance - start_balance) / start_balance) * 100
    winning_trades = [t for t in trades if t['pnl'] > 0]
    win_rate = (len(winning_trades) / len(trades) * 100) if trades else 0
    
    return {
        'strategy': strategy_name,
        'protection': protection_type,
        'final_balance': balance,
        'total_return': total_return,
        'total_trades': len(trades),
        'win_rate': win_rate,
        'blocked_trades': blocked_trades,
        'allowed_bottoms': allowed_bottoms,
        'max_drawdown': max_drawdown,
        'max_drawdown_date': max_drawdown_date,
        'sample_blocks': list(blocked_reasons.items())[:5]
    }

def main():
    """Test strategies with original vs enhanced protection"""
    print("="*100)
    print("TESTING ENHANCED CRASH PROTECTION WITH SMART BOTTOM DETECTION")
    print("="*100)
    print("Comparing:")
    print("  1. NO protection")
    print("  2. ORIGINAL protection (smart bottom detection)")
    print("  3. ENHANCED protection (gaps + smart bottom detection)")
    print("="*100)
    
    # Load data
    df = load_data()
    print(f"Loaded {len(df)} candles from {df['date'].min()} to {df['date'].max()}\n")
    
    # Test configurations
    test_configs = [
        # All 6 Signals
        ("All 6 Signals", STRATEGIES['all_6_signals']),
        ("Two RSI Only", STRATEGIES['two_rsi_only']),
        ("Test6 - 8 Signals", STRATEGIES['test6']),
        ("Test7 - 9 Signals", STRATEGIES['test7']),
    ]
    
    results = []
    
    for strategy_name, strategies in test_configs:
        print(f"\n{strategy_name}:")
        print("-"*60)
        
        # Test each protection type
        for protection in ['none', 'original', 'enhanced']:
            protection_label = {
                'none': 'No Protection',
                'original': 'Original (Smart)',
                'enhanced': 'ENHANCED (Gap+Smart)'
            }[protection]
            
            result = run_strategy_with_protection(df, strategies, f"{strategy_name} ({protection_label})", protection)
            results.append(result)
            
            print(f"{protection_label:20} ${result['final_balance']:>12,.0f} "
                  f"({result['total_return']:>8.1f}%) "
                  f"DD: -{result['max_drawdown']:>5.1f}% "
                  f"Trades: {result['total_trades']:>3} "
                  f"Blocked: {result['blocked_trades']:>2}", end="")
            
            if result['allowed_bottoms'] > 0:
                print(f" Bottoms: {result['allowed_bottoms']:>2}", end="")
            print()
    
    # Summary comparison
    print("\n" + "="*100)
    print("PROTECTION COMPARISON SUMMARY")
    print("="*100)
    
    strategies_list = ["All 6 Signals", "Two RSI Only", "Test6 - 8 Signals", "Test7 - 9 Signals"]
    
    for strat in strategies_list:
        strat_results = [r for r in results if strat in r['strategy']]
        
        none_result = next((r for r in strat_results if 'No Protection' in r['strategy']), None)
        orig_result = next((r for r in strat_results if 'Original' in r['strategy']), None)
        enh_result = next((r for r in strat_results if 'ENHANCED' in r['strategy']), None)
        
        if none_result and orig_result and enh_result:
            print(f"\n{strat}:")
            print(f"  No Protection:  ${none_result['final_balance']:>10,.0f} (baseline)")
            print(f"  Original:       ${orig_result['final_balance']:>10,.0f} ", end="")
            
            orig_diff = orig_result['final_balance'] - none_result['final_balance']
            if orig_diff > 0:
                print(f"(+${orig_diff:,.0f})")
            else:
                print(f"(-${abs(orig_diff):,.0f})")
            
            print(f"  Enhanced:       ${enh_result['final_balance']:>10,.0f} ", end="")
            
            enh_diff = enh_result['final_balance'] - none_result['final_balance']
            if enh_diff > 0:
                print(f"(+${enh_diff:,.0f})")
            else:
                print(f"(-${abs(enh_diff):,.0f})")
            
            # Compare enhanced vs original
            enh_vs_orig = enh_result['final_balance'] - orig_result['final_balance']
            if enh_vs_orig != 0:
                print(f"  Enhanced vs Original: ", end="")
                if enh_vs_orig > 0:
                    print(f"+${enh_vs_orig:,.0f} BETTER!")
                else:
                    print(f"-${abs(enh_vs_orig):,.0f} worse")
            
            # Show drawdown improvement
            if enh_result['max_drawdown'] < orig_result['max_drawdown']:
                dd_improve = orig_result['max_drawdown'] - enh_result['max_drawdown']
                print(f"  Drawdown improved: {dd_improve:.1f}% less")
    
    # Show sample blocks from enhanced
    print("\n" + "="*100)
    print("SAMPLE ENHANCED PROTECTION BLOCKS:")
    print("="*100)
    
    enh_all6 = next((r for r in results if 'All 6 Signals' in r['strategy'] and 'ENHANCED' in r['strategy']), None)
    if enh_all6 and enh_all6['sample_blocks']:
        for date, reason in enh_all6['sample_blocks'][:5]:
            print(f"{date.strftime('%Y-%m-%d')}: {reason}")

if __name__ == "__main__":
    main()
