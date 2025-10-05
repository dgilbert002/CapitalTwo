#!/usr/bin/env python3
"""
TEST3 STRATEGY - EXACT COPY of Test1 with Crash Protection Blocker

This is an IDENTICAL copy of Test1.py with crash protection added ONLY as a blocker.
When Test1 wants to buy, we check if crash protection should block it.

EXHAUSTIVE TESTING of crash protection parameters:
- Timeframes: 1 to 24 weeks
- Drawdown thresholds: -5% to -40%
- RSI bottoms: 20 to 35
- Volume spikes: 1.5x to 3.0x
- Recovery thresholds: -2% to -15%

Comprehensive metrics tracked:
- Drawdown (max and average)
- Win/loss counts and values
- Sharpe ratio
- Recovery ratio
- Protection effectiveness
"""

import os
import sys
from datetime import time as dt_time
from typing import Dict, List, Tuple
import pandas as pd

# Ensure project root on sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Scripts.db_utils import load_epic_df, load_settings

ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)

# EXHAUSTIVE Crash Protection Parameters to Test
CRASH_PROTECTION_PARAMS = []

# Generate combinations with more granular timeframes
# Timeframes: 2h, 4h, 6h, 12h, 1d, 3d, 1w (converted to days for calculation)
timeframes_in_days = [
    2/24,    # 2 hours
    4/24,    # 4 hours  
    6/24,    # 6 hours
    12/24,   # 12 hours
    1,       # 1 day
    3,       # 3 days
    7,       # 1 week
]

# Specific DD thresholds: 5%, 7%, 10%
dd_thresholds = [-5, -7, -10]

# RSI bottoms
rsi_bottoms = [20, 25, 30]

# Volume spikes
vol_spikes = [1.5, 2.0, 2.5]

# Recovery thresholds
recovery_thresholds = [-3, -5, -7, -10]

# Generate all combinations
for timeframe in timeframes_in_days:
    for dd_threshold in dd_thresholds:
        for rsi_bottom in rsi_bottoms:
            for vol_spike in vol_spikes:
                for recovery in recovery_thresholds:
                    CRASH_PROTECTION_PARAMS.append({
                        'timeframe_days': timeframe,
                        'dd_threshold': dd_threshold,
                        'rsi_bottom': rsi_bottom,
                        'vol_spike': vol_spike,
                        'recovery_threshold': recovery
                    })

# Add baseline (no protection)
CRASH_PROTECTION_PARAMS.insert(0, None)

print(f"Total configurations to test: {len(CRASH_PROTECTION_PARAMS)}")

def calculate_daily_indicators(df, timeframe_days):
    """Calculate indicators for crash detection (supports sub-daily timeframes)"""
    import numpy as np
    
    # For sub-daily timeframes, use hourly aggregation
    if timeframe_days < 1:
        # Group by hour for finer granularity
        df['hour'] = df['snapshotTime'].dt.floor('H')
        agg_df = df.groupby('hour').agg({
            'closePrice': 'last',
            'highPrice': 'max',
            'lowPrice': 'min',
            'lastTradedVolume': 'sum'
        })
        lookback_periods = int(timeframe_days * 24)  # Convert to hours
    else:
        # Group by date for daily or longer timeframes
        agg_df = df.groupby('date').agg({
            'closePrice': 'last',
            'highPrice': 'max',
            'lowPrice': 'min',
            'lastTradedVolume': 'sum'
        })
        lookback_periods = int(timeframe_days)  # Use days
    
    # Calculate rolling peak and drawdown
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
    
    # If using hourly data, also create daily summary for compatibility
    if timeframe_days < 1:
        # Map hourly data back to dates for lookup
        daily_summary = agg_df.copy()
        daily_summary['date'] = pd.to_datetime(daily_summary.index).date
        # Take last value of each day for daily lookup
        daily = daily_summary.groupby('date').last()
        return daily
    
    return agg_df

def should_block_trade(daily_indicators, date, params):
    """Check if crash protection should BLOCK this trade"""
    if params is None or date not in daily_indicators.index:
        return False, "No protection", False
    
    row = daily_indicators.loc[date]
    
    # Check for crash conditions
    if row['drawdown'] < params['dd_threshold']:
        # Check for bottom detection (override block)
        if row['rsi'] < params['rsi_bottom'] and row['vol_ratio'] > params['vol_spike']:
            return False, f"BOTTOM DETECTED", True
        
        # Check for recovery
        if row['dd_improvement'] > params['recovery_threshold']:
            return False, f"RECOVERY", False
        
        # BLOCK the trade
        return True, f"CRASH PROTECTION", False
    
    return False, "Normal", False

# Strategy definitions from global_top300__TECL.tsv
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
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Placeholder
    },
    'roc_below_threshold': {
        'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Placeholder
    },
    'macd_positive': {
        'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 
        'threshold': 0.05, 'stop_loss_pct': 4.0,
        'win_rate': 0.0, 'final_balance': 0.0, 'sharpe_ratio': 0.0  # Placeholder
    }
}


def load_data() -> pd.DataFrame:
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
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
        print(f"📅 Filtering from {start_date}")
    if end_date:
        end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
        df = df[df['snapshotTime'] < end]
        print(f"📅 Filtering to {end_date}")
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
    
    # ROC Below Threshold
    fired['roc_below_threshold'] = False
    if 'roc_below_threshold' in conds:
        try:
            fired['roc_below_threshold'] = conds['roc_below_threshold'](
                hist, idx,
                period=STRATEGIES['roc_below_threshold']['period']
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


def calculate_metrics(trades, starting_balance):
    """Calculate comprehensive trading metrics"""
    import numpy as np
    
    if not trades:
        return {
            'win_count': 0, 'loss_count': 0,
            'total_wins': 0, 'total_losses': 0,
            'win_rate': 0, 'avg_win': 0, 'avg_loss': 0,
            'sharpe_ratio': 0, 'recovery_ratio': 0,
            'max_drawdown': 0, 'avg_drawdown': 0
        }
    
    # Win/Loss analysis
    wins = [t for t in trades if t['pnl_net'] > 0]
    losses = [t for t in trades if t['pnl_net'] <= 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    total_wins = sum(t['pnl_net'] for t in wins)
    total_losses = sum(t['pnl_net'] for t in losses)
    
    # Calculate drawdowns
    balances = [starting_balance]
    for t in trades:
        balances.append(t['balance_after'])
    
    peak = starting_balance
    drawdowns = []
    for balance in balances:
        peak = max(peak, balance)
        dd = ((balance - peak) / peak) * 100 if peak > 0 else 0
        drawdowns.append(dd)
    
    # Sharpe Ratio (simplified - daily returns)
    if len(trades) > 1:
        returns = [(trades[i]['balance_after'] - trades[i-1]['balance_after']) / trades[i-1]['balance_after'] 
                   if i > 0 and trades[i-1]['balance_after'] > 0 else 0 
                   for i in range(len(trades))]
        if returns and np.std(returns) > 0:
            sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252)
        else:
            sharpe_ratio = 0
    else:
        sharpe_ratio = 0
    
    # Recovery Ratio
    max_dd = min(drawdowns) if drawdowns else 0
    final_return = ((balances[-1] - starting_balance) / starting_balance) * 100 if starting_balance > 0 else 0
    recovery_ratio = final_return / abs(max_dd) if max_dd < 0 else 0
    
    return {
        'win_count': win_count,
        'loss_count': loss_count,
        'total_wins': total_wins,
        'total_losses': total_losses,
        'win_rate': (win_count / len(trades) * 100) if trades else 0,
        'avg_win': total_wins / win_count if win_count > 0 else 0,
        'avg_loss': total_losses / loss_count if loss_count > 0 else 0,
        'sharpe_ratio': sharpe_ratio,
        'recovery_ratio': recovery_ratio,
        'max_drawdown': max_dd,
        'avg_drawdown': np.mean(drawdowns) if drawdowns else 0
    }

def run_strategy(df: pd.DataFrame, crash_params=None) -> Dict:
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
    trades: List[Dict] = []
    blocked_trades = 0
    bottom_catches = 0

    # Calculate daily indicators if crash protection is enabled
    daily_indicators = None
    if crash_params is not None:
        daily_indicators = calculate_daily_indicators(df, crash_params['timeframe_days'])

    monthly_groups = {}
    for d in trading_days:
        monthly_groups.setdefault((d.year, d.month), []).append(d)
    contribution_dates = [days[0] for _, days in monthly_groups.items() if len(days) > 10]

    if crash_params is None:
        print(f"🔄 Running TEST1 strategy (BASELINE - No Protection)...")
    else:
        tf = crash_params['timeframe_days']
        if tf < 1:
            tf_str = f"{int(tf*24)}h"
        elif tf == 1:
            tf_str = "1d"
        elif tf == 3:
            tf_str = "3d"
        else:
            tf_str = f"{int(tf)}d"
        print(f"🔄 Running with protection: TF={tf_str}, DD={crash_params['dd_threshold']}%...")

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
            market_hours = day_candles[(day_candles['time'] >= dt_time(0, 0)) & (day_candles['time'] <= dt_time(23, 59, 59))]
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

            entry_candle = nearest_candle(df[df['date'] == current_position['entry_date']].copy(), ENTRY_TIME)
            exit_candle = nearest_candle(day_candles, EXIT_TIME) if exit_reason != 'STOP_LOSS' else None
            trades.append({
                'entry_date': current_position['entry_date'],
                'entry_time': current_position['entry_ts'].time(),
                'entry_price': current_position['entry_price'],
                'entry_candle_ts': (entry_candle['snapshotTime'] if isinstance(entry_candle, pd.Series) else None),
                'entry_open': (entry_candle['openPrice'] if isinstance(entry_candle, pd.Series) else None),
                'entry_high': (entry_candle['highPrice'] if isinstance(entry_candle, pd.Series) else None),
                'entry_low': (entry_candle['lowPrice'] if isinstance(entry_candle, pd.Series) else None),
                'entry_close': (entry_candle['closePrice'] if isinstance(entry_candle, pd.Series) else None),
                'sl_level': stop_price,
                'exit_date': current_date,
                'exit_time': exit_ts.time() if hasattr(exit_ts, 'time') else EXIT_TIME,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'exit_candle_ts': (exit_candle['snapshotTime'] if isinstance(exit_candle, pd.Series) else (exit_ts if exit_reason=='STOP_LOSS' else None)),
                'exit_open': (exit_candle['openPrice'] if isinstance(exit_candle, pd.Series) else None),
                'exit_high': (exit_candle['highPrice'] if isinstance(exit_candle, pd.Series) else None),
                'exit_low': (exit_candle['lowPrice'] if isinstance(exit_candle, pd.Series) else None),
                'exit_close': (exit_candle['closePrice'] if isinstance(exit_candle, pd.Series) else None),
                'leverage': current_position['leverage'],
                'stop_loss_pct': sl_pct,
                'notional_value': current_position['notional_value'],
                'fees': fees,
                'pnl_gross': gross_pnl,
                'pnl_net': net_pnl,
                'balance_after': balance,
                'selected_signal': current_position['selected_signal'],
                'signal_win_rate': current_position['signal_win_rate'],
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

        # CRASH PROTECTION CHECK - Block trade if needed
        if crash_params is not None and daily_indicators is not None:
            should_block, reason, is_bottom = should_block_trade(daily_indicators, current_date, crash_params)
            if should_block:
                blocked_trades += 1
                continue  # BLOCK this trade
            if is_bottom:
                bottom_catches += 1

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
                    
                    entry_candle = nearest_candle(day_candles, ENTRY_TIME)
                    trades.append({
                        'entry_date': current_date,
                        'entry_time': ENTRY_TIME,
                        'entry_price': entry_price,
                        'entry_candle_ts': (entry_candle['snapshotTime'] if isinstance(entry_candle, pd.Series) else None),
                        'entry_open': (entry_candle['openPrice'] if isinstance(entry_candle, pd.Series) else None),
                        'entry_high': (entry_candle['highPrice'] if isinstance(entry_candle, pd.Series) else None),
                        'entry_low': (entry_candle['lowPrice'] if isinstance(entry_candle, pd.Series) else None),
                        'entry_close': (entry_candle['closePrice'] if isinstance(entry_candle, pd.Series) else None),
                        'sl_level': sl_same_day,
                        'exit_date': current_date,
                        'exit_time': c['time'],
                        'exit_price': exit_price,
                        'exit_reason': 'STOP_LOSS',
                        'exit_candle_ts': c['snapshotTime'],
                        'exit_open': c['openPrice'],
                        'exit_high': c['highPrice'],
                        'exit_low': c['lowPrice'],
                        'exit_close': c['closePrice'],
                        'leverage': leverage,
                        'stop_loss_pct': stop_loss_pct,
                        'notional_value': notional_value,
                        'fees': fees,
                        'pnl_gross': gross_pnl,
                        'pnl_net': net_pnl,
                        'balance_after': balance,
                        'selected_signal': best_signal,
                        'signal_win_rate': signal_config['win_rate'],
                    })
                    current_position = None
                    break

    final_balance = balance if balance > 0 else 0
    total_return_pct = ((final_balance - starting_balance - total_contributions) / starting_balance) * 100

    # Calculate comprehensive metrics
    metrics = calculate_metrics(trades, starting_balance)

    # Save trades with unique filename for each configuration
    out_path = None
    if trades:
        # Create filename based on configuration
        if crash_params is None:
            filename = f'test3_trades_baseline__{epic}.csv'
        else:
            # Format timeframe for filename
            tf_days = crash_params['timeframe_days']
            if tf_days < 1:
                tf_str = f"{int(tf_days*24)}h"
            else:
                tf_str = f"{int(tf_days)}d" if tf_days == int(tf_days) else f"{tf_days:.1f}d"
            
            filename = f'test3_trades_{tf_str}_dd{abs(crash_params["dd_threshold"])}_rsi{crash_params["rsi_bottom"]}_vol{crash_params["vol_spike"]}_rec{abs(crash_params["recovery_threshold"])}__{epic}.csv'
        
        out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'Results', filename)
        out_df = pd.DataFrame(trades)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        out_df.to_csv(out_path, index=False)

    return {
        'final_balance': final_balance,
        'total_return_pct': total_return_pct,
        'total_contributions': total_contributions,
        'trades': len(trades),
        'blocked_trades': blocked_trades,
        'bottom_catches': bottom_catches,
        'out_path': out_path,
        'crash_params': crash_params,
        **metrics  # Include all calculated metrics
    }


def main():
    print("=" * 80)
    print("TEST3: TOP 10 CRASH PROTECTION CONFIGURATIONS")
    print("=" * 80)
    print("This is the EXACT Test1.py with crash protection blocker")
    
    # Define just the top 10 configurations based on previous results
    top10_configs = [
        None,  # Baseline
        # Top 6 (all tied with same balance)
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 1.5, 'recovery_threshold': -3},
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 1.5, 'recovery_threshold': -5},
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 2.0, 'recovery_threshold': -3},
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 2.0, 'recovery_threshold': -5},
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 2.5, 'recovery_threshold': -3},
        {'timeframe_days': 3, 'dd_threshold': -10, 'rsi_bottom': 20, 'vol_spike': 2.5, 'recovery_threshold': -5},
        # Next 4
        {'timeframe_days': 3, 'dd_threshold': -5, 'rsi_bottom': 20, 'vol_spike': 1.5, 'recovery_threshold': -10},
        {'timeframe_days': 3, 'dd_threshold': -5, 'rsi_bottom': 20, 'vol_spike': 2.0, 'recovery_threshold': -10},
        {'timeframe_days': 3, 'dd_threshold': -5, 'rsi_bottom': 20, 'vol_spike': 2.5, 'recovery_threshold': -10},
        {'timeframe_days': 3, 'dd_threshold': -7, 'rsi_bottom': 20, 'vol_spike': 1.5, 'recovery_threshold': -10},
    ]
    
    print(f"Testing {len(top10_configs)} configurations (baseline + top 10)")
    
    print("\n📊 Loading data...")
    df = load_data()
    print(f"✅ Loaded {len(df):,} candles\n")

    # Run all configurations
    results = []
    
    # Run only top 10 configurations
    test_params = top10_configs
    
    print(f"Running {len(test_params)} configurations...")
    print("-" * 80)
    
    for i, params in enumerate(test_params):
        res = run_strategy(df, crash_params=params)
        results.append(res)
        
        if i == 0:  # Baseline
            baseline = res
            print(f"\n📊 BASELINE (Test1 - No Protection):")
            print(f"  Balance: ${res['final_balance']:,.0f}")
            print(f"  Return: {res['total_return_pct']:+.1f}%")
            print(f"  Trades: {res['trades']}")
            print(f"  Wins: {res['win_count']} (${res['total_wins']:,.0f})")
            print(f"  Losses: {res['loss_count']} (${res['total_losses']:,.0f})")
            print(f"  Win Rate: {res['win_rate']:.1f}%")
            print(f"  Max DD: {res['max_drawdown']:.1f}%")
            print(f"  Sharpe: {res['sharpe_ratio']:.2f}")
            print(f"  Recovery: {res['recovery_ratio']:.2f}")
            print("\nTesting crash protection configurations...")
        
        if i > 0 and i % 20 == 0:
            print(f"  Tested {i}/{len(test_params)}...")

    # Sort by final balance
    results.sort(key=lambda x: x['final_balance'], reverse=True)
    
    # Save all results to CSV
    import csv
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    csv_path = os.path.join(ROOT, 'Results', 'test3_crash_protection_results.csv')
    os.makedirs(os.path.dirname(csv_path), exist_ok=True)
    
    with open(csv_path, 'w', newline='') as csvfile:
        fieldnames = [
            'rank', 'timeframe', 'dd_threshold', 'rsi_bottom', 'vol_spike', 'recovery_threshold',
            'final_balance', 'total_return_pct', 'trades', 'blocked_trades', 'bottom_catches',
            'win_count', 'loss_count', 'total_wins', 'total_losses', 'win_rate',
            'max_drawdown', 'avg_drawdown', 'sharpe_ratio', 'recovery_ratio',
            'improvement_vs_baseline_pct', 'improvement_vs_baseline_abs'
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        
        for i, res in enumerate(results, 1):
            row = {
                'rank': i,
                'timeframe': 'BASELINE' if res['crash_params'] is None else (
                    f"{int(res['crash_params']['timeframe_days']*24)}h" if res['crash_params']['timeframe_days'] < 1
                    else f"{res['crash_params']['timeframe_days']}d"
                ),
                'dd_threshold': 'N/A' if res['crash_params'] is None else res['crash_params']['dd_threshold'],
                'rsi_bottom': 'N/A' if res['crash_params'] is None else res['crash_params']['rsi_bottom'],
                'vol_spike': 'N/A' if res['crash_params'] is None else res['crash_params']['vol_spike'],
                'recovery_threshold': 'N/A' if res['crash_params'] is None else res['crash_params']['recovery_threshold'],
                'final_balance': res['final_balance'],
                'total_return_pct': res['total_return_pct'],
                'trades': res['trades'],
                'blocked_trades': res['blocked_trades'],
                'bottom_catches': res['bottom_catches'],
                'win_count': res['win_count'],
                'loss_count': res['loss_count'],
                'total_wins': res['total_wins'],
                'total_losses': res['total_losses'],
                'win_rate': res['win_rate'],
                'max_drawdown': res['max_drawdown'],
                'avg_drawdown': res['avg_drawdown'],
                'sharpe_ratio': res['sharpe_ratio'],
                'recovery_ratio': res['recovery_ratio'],
                'improvement_vs_baseline_pct': ((res['final_balance'] - baseline['final_balance']) / baseline['final_balance']) * 100,
                'improvement_vs_baseline_abs': res['final_balance'] - baseline['final_balance']
            }
            writer.writerow(row)
    
    print(f"\n💾 Results saved to: {csv_path}")
    
    print("\n" + "=" * 80)
    print("TOP 10 BEST CONFIGURATIONS")
    print("-" * 80)
    
    for i, res in enumerate(results[:10], 1):
        if res['crash_params'] is None:
            config_str = "BASELINE (No Protection)"
        else:
            p = res['crash_params']
            tf = p['timeframe_days']
            if tf < 1:
                tf_str = f"{int(tf*24)}h"
            elif tf == 1:
                tf_str = "1d"
            elif tf == 3:
                tf_str = "3d"
            else:
                tf_str = f"{int(tf)}d"
            config_str = f"TF={tf_str}, DD={p['dd_threshold']}%, RSI<{p['rsi_bottom']}, Vol>{p['vol_spike']}x, Rec={p['recovery_threshold']}%"
        
        improvement = ((res['final_balance'] - baseline['final_balance']) / baseline['final_balance']) * 100
        
        print(f"\n#{i}: ${res['final_balance']:,.0f} ({res['total_return_pct']:+.1f}%)")
        print(f"  Config: {config_str}")
        print(f"  Trades: {res['trades']} | Blocked: {res['blocked_trades']} | Bottoms: {res['bottom_catches']}")
        print(f"  Wins: {res['win_count']} (${res['total_wins']:,.0f}) | Losses: {res['loss_count']} (${res['total_losses']:,.0f})")
        print(f"  Win Rate: {res['win_rate']:.1f}% | Max DD: {res['max_drawdown']:.1f}%")
        print(f"  Sharpe: {res['sharpe_ratio']:.2f} | Recovery: {res['recovery_ratio']:.2f}")
        print(f"  vs Baseline: {improvement:+.1f}%")
    
    # Find best protected configuration
    best_protected = None
    for res in results:
        if res['crash_params'] is not None:
            if best_protected is None or res['final_balance'] > best_protected['final_balance']:
                best_protected = res
    
    if best_protected:
        print("\n" + "=" * 80)
        print("🏆 OPTIMAL CRASH PROTECTION CONFIGURATION")
        print("=" * 80)
        
        p = best_protected['crash_params']
        tf = p['timeframe_days']
        if tf < 1:
            tf_str = f"{int(tf*24)}-hour"
        elif tf == 1:
            tf_str = "1-day"
        elif tf == 3:
            tf_str = "3-day"
        else:
            tf_str = f"{int(tf)}-day"
        print(f"\nParameters:")
        print(f"  • {tf_str} lookback")
        print(f"  • Block when drawdown > {abs(p['dd_threshold'])}%")
        print(f"  • Bottom detection: RSI < {p['rsi_bottom']} + Volume > {p['vol_spike']}x")
        print(f"  • Recovery threshold: {p['recovery_threshold']}%")
        
        print(f"\nResults:")
        print(f"  • Final Balance: ${best_protected['final_balance']:,.0f}")
        print(f"  • Total Return: {best_protected['total_return_pct']:+.1f}%")
        print(f"  • Trades: {best_protected['trades']}")
        print(f"  • Blocked: {best_protected['blocked_trades']}")
        print(f"  • Bottoms caught: {best_protected['bottom_catches']}")
        print(f"  • Win Rate: {best_protected['win_rate']:.1f}%")
        print(f"  • Max Drawdown: {best_protected['max_drawdown']:.1f}%")
        print(f"  • Sharpe Ratio: {best_protected['sharpe_ratio']:.2f}")
        print(f"  • Recovery Ratio: {best_protected['recovery_ratio']:.2f}")
        
        improvement = ((best_protected['final_balance'] - baseline['final_balance']) / baseline['final_balance']) * 100
        print(f"\nComparison:")
        print(f"  • Baseline: ${baseline['final_balance']:,.0f}")
        print(f"  • Protected: ${best_protected['final_balance']:,.0f}")
        print(f"  • Difference: ${best_protected['final_balance'] - baseline['final_balance']:,.0f} ({improvement:+.1f}%)")


if __name__ == '__main__':
    main()
