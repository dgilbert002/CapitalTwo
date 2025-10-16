#!/usr/bin/env python3
"""
TEST5: Using ONLY rsi_bullish_cross_50 and rsi_oversold signals
Keeping original leverage from the strategies
"""

import os
import sys
from datetime import time as dt_time
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Test3 import (
    load_data, calculate_daily_indicators,
    should_block_trade, calculate_metrics, ENTRY_TIME, EXIT_TIME,
    get_price_at_time, calculate_trading_costs, nearest_candle,
    create_indicator_library, STRATEGIES
)
from Scripts.db_utils import load_settings

# Only use these two signals
ALLOWED_SIGNALS = ['rsi_bullish_cross_50', 'rsi_oversold']

def run_two_signals_strategy(df, use_crash_protection=True):
    """Run strategy with only two RSI signals"""
    
    # Best crash protection from Test3
    crash_params = {
        'timeframe_days': 3,
        'dd_threshold': -10,
        'rsi_bottom': 20,
        'vol_spike': 1.5,
        'recovery_threshold': -3
    } if use_crash_protection else None
    
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    settings = load_settings(os.path.join(ROOT, 'settings.txt'))
    epic = str(settings.get('epic', 'TECL'))
    start_balance = float(settings.get('start_balance', 100.0))
    invest_pct = float(settings.get('invest_pct', 0.99))
    monthly_top_up = float(settings.get('monthly_top_up', 0.0))
    
    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]
    
    balance = start_balance
    starting_balance = start_balance
    total_contributions = 0.0
    current_position = None
    trades = []
    blocked_trades = 0
    skipped_signals = 0
    
    # Calculate daily indicators for crash protection
    daily_indicators = None
    if crash_params:
        daily_indicators = calculate_daily_indicators(df, crash_params['timeframe_days'])
    
    # Monthly contribution setup
    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]
    
    protection_str = "WITH crash protection" if use_crash_protection else "WITHOUT crash protection"
    print(f"🔄 Running TWO SIGNALS strategy {protection_str}...")
    print(f"   Using only: {', '.join(ALLOWED_SIGNALS)}")
    
    for current_date in trading_days:
        # Monthly top-up
        if current_date in contribution_dates and monthly_top_up > 0 and balance > 0:
            balance += monthly_top_up
            total_contributions += monthly_top_up
        
        day_candles = df[df['date'] == current_date].copy()
        if day_candles.empty:
            continue
        
        # Exit position if held
        if current_position is not None:
            sl_pct = current_position['stop_loss_pct']
            stop_price = current_position['entry_price'] * (1 - sl_pct / 100)
            stop_hit = False
            
            # Check for stop loss through all hours
            market_hours = day_candles[(day_candles['time'] >= dt_time(0, 0)) & 
                                      (day_candles['time'] <= dt_time(23, 59, 59))]
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
            
            # Calculate P&L
            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross_pnl = current_position['notional_value'] * price_change_pct
            fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
            net_pnl = gross_pnl - fees
            balance += net_pnl
            
            trades.append({
                'entry_date': current_position['entry_date'],
                'entry_price': current_position['entry_price'],
                'exit_date': current_date,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'leverage': current_position['leverage'],
                'stop_loss_pct': sl_pct,
                'pnl_net': net_pnl,
                'balance_after': balance,
                'selected_signal': current_position['selected_signal']
            })
            current_position = None
        
        # Entry evaluation
        hist = df[df['date'] <= current_date]
        if hist.empty:
            continue
        
        # Get signals but only evaluate our two allowed signals
        lib_today = create_indicator_library(hist)
        conds = lib_today.get_conditions()
        idx = len(hist) - 1
        
        fired_signals = {}
        
        # Check RSI Bullish Cross 50
        if 'rsi_bullish_cross_50' in ALLOWED_SIGNALS and 'rsi_bullish_cross_50' in STRATEGIES:
            try:
                signal_fired = conds['rsi_bullish_cross_50'](
                    hist, idx,
                    period=STRATEGIES['rsi_bullish_cross_50']['period']
                )
                if signal_fired:
                    fired_signals['rsi_bullish_cross_50'] = STRATEGIES['rsi_bullish_cross_50']
            except Exception:
                pass
        
        # Check RSI Oversold
        if 'rsi_oversold' in ALLOWED_SIGNALS and 'rsi_oversold' in STRATEGIES:
            try:
                signal_fired = conds['rsi_oversold'](
                    hist, idx,
                    period=STRATEGIES['rsi_oversold']['period'],
                    threshold=STRATEGIES['rsi_oversold']['threshold']
                )
                if signal_fired:
                    fired_signals['rsi_oversold'] = STRATEGIES['rsi_oversold']
            except Exception:
                pass
        
        # Select best signal if multiple fire (use highest win rate)
        best_signal = None
        signal_config = None
        if fired_signals:
            # If multiple signals, pick the one with highest win rate
            best_win_rate = 0
            for signal_name, config in fired_signals.items():
                if config['win_rate'] > best_win_rate:
                    best_win_rate = config['win_rate']
                    best_signal = signal_name
                    signal_config = config
        
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if best_signal is None or entry_price is None or balance <= 0 or current_position is not None:
            if best_signal is None and entry_price is not None and balance > 0 and current_position is None:
                # A signal would have fired but it wasn't one of our allowed signals
                skipped_signals += 1
            continue
        
        # CRASH PROTECTION
        if crash_params and daily_indicators is not None:
            should_block, reason, is_bottom = should_block_trade(daily_indicators, current_date, crash_params)
            if should_block:
                blocked_trades += 1
                continue
        
        # Get parameters - USE ORIGINAL LEVERAGE
        leverage = signal_config['leverage']
        stop_loss_pct = signal_config['stop_loss_pct']
        
        # Calculate position size
        notional_value = balance * invest_pct * leverage
        
        current_position = {
            'entry_date': current_date,
            'entry_price': entry_price,
            'notional_value': notional_value,
            'leverage': leverage,
            'stop_loss_pct': stop_loss_pct,
            'selected_signal': best_signal,
        }
        
        # Check same-day stop loss
        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME) & 
                                  (day_candles['time'] <= dt_time(20, 0))]
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
                        'pnl_net': net_pnl,
                        'balance_after': balance,
                        'selected_signal': best_signal
                    })
                    current_position = None
                    break
    
    # Calculate final metrics
    final_balance = balance if balance > 0 else 0
    total_return_pct = ((final_balance - starting_balance - total_contributions) / starting_balance) * 100
    
    metrics = calculate_metrics(trades, starting_balance)
    
    # Find minimum balance
    min_balance = starting_balance
    for trade in trades:
        if trade['balance_after'] < min_balance:
            min_balance = trade['balance_after']
    
    # Count trades by signal
    signal_counts = {}
    for trade in trades:
        signal = trade['selected_signal']
        signal_counts[signal] = signal_counts.get(signal, 0) + 1
    
    return {
        'final_balance': final_balance,
        'total_return_pct': total_return_pct,
        'trades': len(trades),
        'blocked_trades': blocked_trades,
        'min_balance': min_balance,
        'signal_counts': signal_counts,
        **metrics
    }


def main():
    print("=" * 80)
    print("TEST5: TWO SIGNALS ONLY STRATEGY")
    print("=" * 80)
    print("Using only rsi_bullish_cross_50 and rsi_oversold with original leverage\n")
    
    print("📊 Loading data...")
    df = load_data()
    print(f"✅ Loaded {len(df):,} candles\n")
    
    # Test with and without crash protection
    print("Testing configurations...")
    print("-" * 80)
    
    # Run without crash protection
    print("\n[1/2] WITHOUT crash protection")
    res_no_protection = run_two_signals_strategy(df, use_crash_protection=False)
    print(f"  Final Balance: ${res_no_protection['final_balance']:,.0f}")
    print(f"  Min Balance: ${res_no_protection['min_balance']:,.0f}")
    print(f"  Total Trades: {res_no_protection['trades']}")
    if res_no_protection['signal_counts']:
        print("  Trades by signal:")
        for signal, count in res_no_protection['signal_counts'].items():
            print(f"    - {signal}: {count}")
    
    # Run with crash protection
    print("\n[2/2] WITH crash protection (3-day, -10% DD)")
    res_with_protection = run_two_signals_strategy(df, use_crash_protection=True)
    print(f"  Final Balance: ${res_with_protection['final_balance']:,.0f}")
    print(f"  Min Balance: ${res_with_protection['min_balance']:,.0f}")
    print(f"  Total Trades: {res_with_protection['trades']} (Blocked: {res_with_protection['blocked_trades']})")
    if res_with_protection['signal_counts']:
        print("  Trades by signal:")
        for signal, count in res_with_protection['signal_counts'].items():
            print(f"    - {signal}: {count}")
    
    # Compare results
    print("\n" + "=" * 80)
    print("🏆 COMPARISON")
    print("=" * 80)
    
    print(f"\nWITHOUT crash protection: ${res_no_protection['final_balance']:,.0f}")
    print(f"WITH crash protection:    ${res_with_protection['final_balance']:,.0f}")
    
    improvement = ((res_with_protection['final_balance'] - res_no_protection['final_balance']) / 
                  res_no_protection['final_balance'] * 100)
    print(f"\nCrash protection impact: {improvement:+.1f}%")
    
    # Compare to Test3 baseline ($699,074)
    test3_baseline = 699074
    print(f"\nvs Test3 (all signals): ")
    print(f"  Two signals only:      {((res_with_protection['final_balance'] - test3_baseline) / test3_baseline * 100):+.1f}%")
    
    if res_with_protection['final_balance'] >= 1000000:
        print(f"\n🎉 TARGET ACHIEVED! Exceeded $1,000,000!")
    else:
        progress = (res_with_protection['final_balance'] / 1000000) * 100
        print(f"\n📈 Progress to $1M: {progress:.1f}%")
        print(f"   Still need: ${1000000 - res_with_protection['final_balance']:,.0f}")
    
    # Show the actual leverage values being used
    print(f"\n📊 Signal Details:")
    if 'rsi_bullish_cross_50' in STRATEGIES:
        cfg = STRATEGIES['rsi_bullish_cross_50']
        print(f"  rsi_bullish_cross_50: {cfg['leverage']}x leverage, {cfg['stop_loss_pct']}% stop, {cfg['win_rate']}% win rate")
    if 'rsi_oversold' in STRATEGIES:
        cfg = STRATEGIES['rsi_oversold']
        print(f"  rsi_oversold: {cfg['leverage']}x leverage, {cfg['stop_loss_pct']}% stop, {cfg['win_rate']}% win rate")


if __name__ == '__main__':
    main()
