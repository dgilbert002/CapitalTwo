#!/usr/bin/env python3
"""EXACT copy of elite Test1.py logic - NO threshold for ROC"""

import os
import sys
from datetime import time as dt_time
import pandas as pd
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Scripts.db_utils import load_epic_df, load_settings

ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

# EXACT elite strategies
STRATEGIES = {
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
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0
    },
    'roc_below_threshold': {
        'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0
    },
    'macd_positive': {
        'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 
        'threshold': 0.05, 'stop_loss_pct': 4.0,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0
    }
}

def load_data():
    ROOT = os.path.dirname(os.path.abspath(__file__))
    settings_path = os.path.join(ROOT, 'settings.txt')
    settings = load_settings(settings_path)
    epic = str(settings.get('epic', 'TECL'))
    start_date = settings.get('start_date')
    end_date = settings.get('end_date')

    df = load_epic_df('database_av.db', epic)
    if 'snapshotTime' not in df.columns and 'timestamp' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    if start_date:
        start = pd.to_datetime(start_date)
        df = df[df['snapshotTime'] >= start]
    if end_date:
        end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
        df = df[df['snapshotTime'] < end]
    return df.sort_values('snapshotTime').reset_index(drop=True)

def nearest_candle(candles: pd.DataFrame, target_time: dt_time):
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

def eval_signals(hist: pd.DataFrame) -> Dict[str, bool]:
    """EXACT elite signal evaluation - NO threshold for ROC"""
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
                period=STRATEGIES['rsi_oversold']['period'], 
                threshold=STRATEGIES['rsi_oversold']['threshold']
            )
        except Exception:
            pass
    
    # Bollinger Bands Lower Break
    fired['bb_lower_break'] = False
    if 'bb_lower_break' in conds:
        try:
            fired['bb_lower_break'] = conds['bb_lower_break'](
                hist, idx,
                period=STRATEGIES['bb_lower_break']['period'],
                std_dev=STRATEGIES['bb_lower_break']['std_dev']
            )
        except Exception:
            pass
    
    # RSI Bullish Cross 50
    fired['rsi_bullish_cross_50'] = False
    if 'rsi_bullish_cross_50' in conds:
        try:
            fired['rsi_bullish_cross_50'] = conds['rsi_bullish_cross_50'](
                hist, idx,
                period=STRATEGIES['rsi_bullish_cross_50']['period']
            )
        except Exception:
            pass
    
    # Price Above VWAP
    fired['price_above_vwap'] = False
    if 'price_above_vwap' in conds:
        try:
            fired['price_above_vwap'] = conds['price_above_vwap'](
                hist, idx,
                threshold=STRATEGIES['price_above_vwap']['threshold']
            )
        except Exception:
            pass
    
    # ROC Below Threshold - NO THRESHOLD PARAMETER (uses default)
    fired['roc_below_threshold'] = False
    if 'roc_below_threshold' in conds:
        try:
            # CRITICAL: Elite model does NOT pass threshold, uses default from indicators.py
            fired['roc_below_threshold'] = conds['roc_below_threshold'](
                hist, idx,
                period=STRATEGIES['roc_below_threshold']['period']
                # NO threshold parameter!
            )
        except Exception:
            pass
    
    # MACD Positive
    fired['macd_positive'] = False
    if 'macd_positive' in conds:
        try:
            fired['macd_positive'] = conds['macd_positive'](
                hist, idx,
                fast_period=STRATEGIES['macd_positive']['fast_period'],
                slow_period=STRATEGIES['macd_positive']['slow_period'],
                signal_period=STRATEGIES['macd_positive']['signal_period'],
                threshold=STRATEGIES['macd_positive']['threshold']
            )
        except Exception:
            pass
    
    return fired

def select_best_signal(fired_signals: Dict[str, bool]) -> Tuple[str, Dict]:
    """Select the signal with highest win_rate from fired signals"""
    fired_list = [s for s, v in fired_signals.items() if v]
    if not fired_list:
        return None, None
    
    # Sort by win_rate (descending), then by sharpe_ratio, then by final_balance
    best_signal = max(fired_list, key=lambda s: (
        STRATEGIES[s]['win_rate'],
        STRATEGIES[s]['sharpe_ratio'],
        STRATEGIES[s]['final_balance']
    ))
    
    return best_signal, STRATEGIES[best_signal]

def run_strategy(df: pd.DataFrame) -> Dict:
    ROOT = os.path.dirname(os.path.abspath(__file__))
    settings = load_settings(os.path.join(ROOT, 'settings.txt'))
    epic = str(settings.get('epic', 'TECL'))
    start_balance = 500.0  # Use $500 to match your expected $376k result
    invest_pct = float(settings.get('invest_pct', 0.99))
    monthly_top_up = float(settings.get('monthly_top_up', 0.0))

    all_dates = sorted(df['date'].unique())
    trading_days = [d for d in all_dates if pd.Timestamp(d).weekday() < 5]

    balance = start_balance
    starting_balance = start_balance
    total_contributions = 0.0
    current_position = None
    trades: List[Dict] = []

    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]

    print(f"Running FINAL elite-matching strategy...")
    print(f"Start balance: ${start_balance}")
    print(f"Investment: {invest_pct * 100}%")

    for current_date in trading_days:
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
            market_hours = day_candles[(day_candles['time'] >= dt_time(0, 0)) & 
                                      (day_candles['time'] <= dt_time(23, 59, 59))]
            for _, c in market_hours.iterrows():
                if c['lowPrice'] <= stop_price:
                    stop_hit = True
                    exit_price = stop_price
                    exit_ts = c['snapshotTime']
                    exit_reason = 'STOP_LOSS'
                    break
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice')
                exit_ts = pd.Timestamp.combine(current_date, EXIT_TIME)
                exit_reason = 'NORMAL_EXIT'
                if exit_price is None:
                    exit_price = current_position['entry_price']
                    exit_reason = 'NO_EXIT_PRICE'

            price_change_pct = (exit_price - current_position['entry_price']) / current_position['entry_price']
            gross_pnl = current_position['notional_value'] * price_change_pct
            fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
            net_pnl = gross_pnl - fees
            balance += net_pnl

            trades.append({
                'entry_date': current_position['entry_date'],
                'exit_date': current_date,
                'entry_price': current_position['entry_price'],
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'leverage': current_position['leverage'],
                'stop_loss_pct': sl_pct,
                'notional_value': current_position['notional_value'],
                'pnl_net': net_pnl,
                'balance_after': balance,
                'selected_signal': current_position['selected_signal']
            })
            current_position = None

        # Entry evaluation
        hist = df[df['date'] <= current_date]
        if hist.empty:
            continue
        fired = eval_signals(hist)
        best_signal, signal_config = select_best_signal(fired)
        
        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if best_signal is None or entry_price is None or balance <= 0 or current_position is not None:
            continue

        leverage = signal_config['leverage']
        stop_loss_pct = signal_config['stop_loss_pct']
        notional_value = balance * invest_pct * leverage
        
        current_position = {
            'entry_date': current_date,
            'entry_ts': pd.Timestamp.combine(current_date, ENTRY_TIME),
            'entry_price': entry_price,
            'notional_value': notional_value,
            'leverage': leverage,
            'stop_loss_pct': stop_loss_pct,
            'selected_signal': best_signal,
            'signal_win_rate': signal_config['win_rate'],
        }

        # Same-day after-hours stop
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
                        'exit_date': current_date,
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'exit_reason': 'STOP_LOSS',
                        'leverage': leverage,
                        'stop_loss_pct': stop_loss_pct,
                        'notional_value': notional_value,
                        'pnl_net': net_pnl,
                        'balance_after': balance,
                        'selected_signal': best_signal
                    })
                    current_position = None
                    break

    final_balance = balance if balance > 0 else 0
    total_return_pct = ((final_balance - starting_balance - total_contributions) / starting_balance) * 100

    print(f"\nFINAL RESULTS")
    print("=" * 48)
    print(f"Final Balance: ${final_balance:,.2f}")
    print(f"Total Return: {total_return_pct:+.1f}%")
    print(f"Trades: {len(trades)}")
    
    # Check specific trades
    if len(trades) > 280:
        print(f"\nTrade 280:")
        t = trades[279]
        print(f"  Entry: {t['entry_date']} @ ${t['entry_price']:.2f}")
        print(f"  Signal: {t['selected_signal']}")
        print(f"  Balance: ${t['balance_after']:.2f}")
    
    return {
        'final_balance': final_balance,
        'total_return_pct': total_return_pct,
        'trades': len(trades)
    }

def main():
    print("FINAL ELITE MODEL MATCH")
    print("=" * 60)
    
    df = load_data()
    print(f"Loaded {len(df):,} candles\n")
    
    res = run_strategy(df)
    
    print(f"\nTarget (Elite Test1.py): $303,567")
    print(f"Difference: ${303567 - res['final_balance']:.2f}")
    
    if abs(res['final_balance'] - 303567) < 100:
        print("\n✅ SUCCESS! We match the elite model!")
    else:
        print("\n❌ Still not matching. Checking ROC threshold...")
        # Debug ROC
        from indicators import create_indicator_library
        import pandas as pd
        from datetime import date
        
        target_date = date(2025, 3, 3)
        hist = df[df['date'] <= target_date]
        lib = create_indicator_library(hist)
        conds = lib.get_conditions()
        
        if 'roc_below_threshold' in conds:
            # Test with NO threshold (uses default)
            result_default = conds['roc_below_threshold'](hist, len(hist)-1, period=10)
            print(f"  ROC fires with default threshold: {result_default}")

if __name__ == '__main__':
    main()
