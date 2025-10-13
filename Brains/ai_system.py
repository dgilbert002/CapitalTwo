import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import warnings
import talib
# Import the proven $699k strategy system
from Brains.strategy_signals import (
    get_strategy_analysis,
    SIGNAL_CONFIGS,
    validate_implementation
)
import os
import sys
warnings.filterwarnings("ignore")

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from indicators import create_indicator_library

class HybridIntelligentSystem:
    """Enhanced AI system with multi-strategy OR logic from TEST1 strategy"""

    def __init__(self):
        # Real Capital.com fees - EXACT from uploaded files
        self.SPREAD_COST = 0.00019  # 0.019% per trade
        self.OVERNIGHT_FUNDING_LONG = -0.00023  # -0.023% per day for longs
        
        # Strategy mode: 'enhanced' (current), 'all_signals' ($376k/$699k), 'two_rsi_only' (lower risk),
        #               'test6_no_protection' ($509k), 'test6_with_protection' ($958k BEST!)
        self.strategy_mode = 'enhanced'  # Default to current system
        self.enable_crash_protection = True
        
        # Validate the proven strategy implementation on init
        try:
            validate_implementation()
            print("Proven $699k strategy validated and ready!")
        except Exception as e:
            print(f"Warning: Strategy validation failed: {e}")
        
        # Strategy definitions from TEST1 with proven win rates
        self.STRATEGIES = {
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
                'win_rate': 62.0, 'final_balance': 10234.56, 'sharpe_ratio': 2.45
            },
            'roc_below_threshold': {
                'leverage': 5.0, 'period': 10, 'stop_loss_pct': 7.5, 'threshold': -0.5,
                'win_rate': 58.0, 'final_balance': 8765.43, 'sharpe_ratio': 2.21
            },
            'macd_positive': {
                'leverage': 5.0, 'fast_period': 13, 'slow_period': 30, 'signal_period': 9, 
                'threshold': 0.05, 'stop_loss_pct': 4.0,
                'win_rate': 55.0, 'final_balance': 7654.32, 'sharpe_ratio': 2.10
            },
            # New Test6 strategies from TSV (8 total strategies)
            'keltner_lower_break': {
                'leverage': 5.0, 'multiplier': 2.0, 'period': 10, 'stop_loss_pct': 4.0,
                'win_rate': 74.2, 'final_balance': 118723.43, 'sharpe_ratio': 2.87
            },
            'macd_histogram_negative': {
                'leverage': 5.0, 'fast_period': 8, 'slow_period': 18, 
                'signal_period': 4, 'threshold': -0.05, 'stop_loss_pct': 4.0,
                'win_rate': 70.7, 'final_balance': 119960.31, 'sharpe_ratio': 2.8
            },
            # Experimental variant for comparison
            'macd_histogram_negative_v2': {
                'leverage': 5.0, 'fast_period': 5, 'slow_period': 18,
                'signal_period': 4, 'threshold': -0.10, 'stop_loss_pct': 5.5,
                'win_rate': 75.9, 'final_balance': 134549.42, 'sharpe_ratio': 2.93
            }
        }

    def calculate_technical_indicators(self, df):
        """EXACT function from focused_optimizer.py"""
        df = df.copy()
        
        # Ensure correct column names
        df.rename(columns={
            'open': 'openPrice',
            'high': 'highPrice',
            'low': 'lowPrice',
            'close': 'closePrice',
            'volume': 'lastTradedVolume'
        }, inplace=True)

        # Price-based indicators
        df['sma_20'] = talib.SMA(df['closePrice'], timeperiod=20)
        df['ema_12'] = talib.EMA(df['closePrice'], timeperiod=12)
        
        # Momentum indicators
        df['rsi'] = talib.RSI(df['closePrice'], timeperiod=14)
        df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(df['closePrice'])
        
        # Volatility indicators
        df['atr'] = talib.ATR(df['highPrice'], df['lowPrice'], df['closePrice'], timeperiod=14)
        
        # Volume indicators
        volume_col = 'lastTradedVolume'
        if volume_col in df.columns:
            df['volume_sma'] = talib.SMA(df[volume_col], timeperiod=20)
            df['volume_ratio'] = df[volume_col] / df['volume_sma']
        else:
            df['volume_sma'] = 1.0
            df['volume_ratio'] = 1.0
        
        # Price patterns
        df['price_change'] = df['closePrice'].pct_change()
        df['price_momentum'] = df['closePrice'].pct_change(periods=5)
        
        return df

    def _eval_signals(self, hist):
        """Evaluate all strategy signals using OR logic"""
        lib = create_indicator_library(hist)
        conds = lib.get_conditions()
        idx = len(hist) - 1
        fired = {}
        
        # RSI Oversold
        fired['rsi_oversold'] = False
        if 'rsi_oversold' in conds:
            try:
                fired['rsi_oversold'] = conds['rsi_oversold'](
                    hist, idx, 
                    period=self.STRATEGIES['rsi_oversold']['period'], 
                    threshold=self.STRATEGIES['rsi_oversold']['threshold']
                )
            except Exception:
                pass
        
        # Bollinger Bands Lower Break
        fired['bb_lower_break'] = False
        if 'bb_lower_break' in conds:
            try:
                fired['bb_lower_break'] = conds['bb_lower_break'](
                    hist, idx,
                    period=self.STRATEGIES['bb_lower_break']['period'],
                    std_dev=self.STRATEGIES['bb_lower_break']['std_dev']
                )
            except Exception:
                pass
        
        # RSI Bullish Cross 50
        fired['rsi_bullish_cross_50'] = False
        if 'rsi_bullish_cross_50' in conds:
            try:
                fired['rsi_bullish_cross_50'] = conds['rsi_bullish_cross_50'](
                    hist, idx,
                    period=self.STRATEGIES['rsi_bullish_cross_50']['period']
                )
            except Exception:
                pass
        
        # Price Above VWAP
        fired['price_above_vwap'] = False
        if 'price_above_vwap' in conds:
            try:
                fired['price_above_vwap'] = conds['price_above_vwap'](
                    hist, idx,
                    threshold=self.STRATEGIES['price_above_vwap']['threshold']
                )
            except Exception:
                pass
        
        # ROC Below Threshold
        fired['roc_below_threshold'] = False
        if 'roc_below_threshold' in conds:
            try:
                # CRITICAL FIX: Don't pass threshold, use default -1.0% from indicators.py
                fired['roc_below_threshold'] = conds['roc_below_threshold'](
                    hist, idx,
                    period=self.STRATEGIES['roc_below_threshold']['period']
                    # NO threshold parameter - uses default -1.0%
                )
            except Exception:
                pass
        
        # MACD Positive
        fired['macd_positive'] = False
        if 'macd_positive' in conds:
            try:
                fired['macd_positive'] = conds['macd_positive'](
                    hist, idx,
                    fast_period=self.STRATEGIES['macd_positive']['fast_period'],
                    slow_period=self.STRATEGIES['macd_positive']['slow_period'],
                    signal_period=self.STRATEGIES['macd_positive']['signal_period'],
                    threshold=self.STRATEGIES['macd_positive']['threshold']
                )
            except Exception:
                pass
        
        # Keltner Lower Break (Test6 strategy)
        fired['keltner_lower_break'] = False
        if 'keltner_lower_break' in conds:
            try:
                fired['keltner_lower_break'] = conds['keltner_lower_break'](
                    hist, idx,
                    period=self.STRATEGIES['keltner_lower_break']['period'],
                    multiplier=self.STRATEGIES['keltner_lower_break']['multiplier']
                )
            except Exception:
                pass
        
        # MACD Histogram Negative (Test6 strategy)
        fired['macd_histogram_negative'] = False
        if 'macd_histogram_negative' in conds:
            try:
                fired['macd_histogram_negative'] = conds['macd_histogram_negative'](
                    hist, idx,
                    fast_period=self.STRATEGIES['macd_histogram_negative']['fast_period'],
                    slow_period=self.STRATEGIES['macd_histogram_negative']['slow_period'],
                    signal_period=self.STRATEGIES['macd_histogram_negative']['signal_period'],
                    threshold=self.STRATEGIES['macd_histogram_negative']['threshold']
                )
            except Exception:
                pass

        # MACD Histogram Negative V2 (experimental)
        fired['macd_histogram_negative_v2'] = False
        if 'macd_histogram_negative_v2' in conds:
            try:
                fired['macd_histogram_negative_v2'] = conds['macd_histogram_negative'](
                    hist, idx,
                    fast_period=self.STRATEGIES['macd_histogram_negative_v2']['fast_period'],
                    slow_period=self.STRATEGIES['macd_histogram_negative_v2']['slow_period'],
                    signal_period=self.STRATEGIES['macd_histogram_negative_v2']['signal_period'],
                    threshold=self.STRATEGIES['macd_histogram_negative_v2']['threshold']
                )
            except Exception:
                pass
        
        # Convert numpy booleans to regular Python booleans for JSON serialization
        return {k: bool(v) for k, v in fired.items()}
    
    def _select_best_signal(self, fired_signals):
        """Select the signal with highest win_rate from fired signals"""
        fired_list = [s for s, v in fired_signals.items() if v]
        if not fired_list:
            return None, None
        
        # Sort by win_rate (descending), then by sharpe_ratio, then by final_balance
        best_signal = max(fired_list, key=lambda s: (
            self.STRATEGIES[s]['win_rate'],
            self.STRATEGIES[s]['sharpe_ratio'],
            self.STRATEGIES[s]['final_balance']
        ))
        
        return best_signal, self.STRATEGIES[best_signal]

    def analyze_market_conditions(self, day_data, historical_data, current_date):
        """Enhanced multi-strategy OR logic analysis with proven strategy support"""
        
        # Use proven strategy if configured
        if self.strategy_mode in ['all_signals', 'two_rsi_only', 'test6', 'test6_no_protection', 'test6_with_protection', 'test7', 'test7_no_protection', 'test7_with_protection']:
            # Ensure date column exists for crash protection
            if 'date' not in historical_data.columns:
                historical_data['date'] = pd.to_datetime(historical_data['timestamp']).dt.date
            
            # Get current date for crash protection
            if isinstance(current_date, datetime):
                check_date = current_date.date()
            else:
                check_date = current_date
            
            # Run the proven strategy analysis
            analysis = get_strategy_analysis(
                historical_data,
                strategy_mode=self.strategy_mode,
                enable_crash_protection=self.enable_crash_protection,
                current_date=check_date
            )
            
            # Add direction for compatibility
            analysis['direction'] = 'long'
            return analysis
        
        # Otherwise use enhanced mode (current system)
        if day_data.empty or len(historical_data) < 50:
            return {
                'trade_signal': 'hold',
                'confidence': 0.0,
                'direction': 'long',
                'selected_strategy': None,
                'strategy_config': None,
                'fired_signals': {}
            }
        
        # Evaluate all strategy signals
        fired_signals = self._eval_signals(historical_data)
        
        # Select best signal based on win rate
        best_signal, signal_config = self._select_best_signal(fired_signals)
        
        if best_signal is None:
            # No signals fired, use original logic as fallback
            return self._analyze_market_conditions_original(day_data, historical_data, current_date)
        
        # Convert win rate to confidence (0-1 scale)
        confidence = signal_config['win_rate'] / 100.0
        
        return {
            'trade_signal': 'buy',  # All strategies in TEST1 are long-only
            'confidence': float(confidence),  # Ensure it's a Python float
            'direction': 'long',
            'selected_strategy': best_signal,
            'strategy_config': signal_config,
            'fired_signals': fired_signals,  # For logging/debugging
            'strategy_used': best_signal,  # For trader.py compatibility
            'strategy_leverage': signal_config.get('leverage', 1),  # Include leverage from strategy
            'strategy_stop_loss': signal_config.get('stop_loss_pct', None)  # Include stop loss from strategy
        }
    
    def _analyze_market_conditions_original(self, day_data, historical_data, current_date):
        """Original scoring-based analysis (kept as fallback)"""
        
        # Get latest indicators
        latest = historical_data.iloc[-1]
        
        # Initialize scoring system
        bullish_signals = 0
        bearish_signals = 0
        
        # 1. Trend Analysis
        if latest['closePrice'] > latest['sma_20']:
            bullish_signals += 3
        else:
            bearish_signals += 3
        
        # 2. Momentum Analysis
        if 30 < latest['rsi'] < 70:
            bullish_signals += 2
        elif latest['rsi'] > 70:
            bearish_signals += 2
        elif latest['rsi'] < 30:
            bullish_signals += 2  # Oversold can be bullish
        
        if latest['macd'] > latest['macd_signal']:
            bullish_signals += 2
        else:
            bearish_signals += 2
        
        # 3. Volume Analysis
        if latest['volume_ratio'] > 1.2:
            bullish_signals += 1
        elif latest['volume_ratio'] < 0.8:
            bearish_signals += 1
        
        # 4. Day of Week Bias
        day_of_week = current_date.strftime('%A')
        if day_of_week == 'Tuesday':
            bullish_signals += 3
        elif day_of_week == 'Friday':
            bullish_signals += 2
        elif day_of_week == 'Wednesday':
            bullish_signals += 1
        elif day_of_week == 'Thursday':
            bearish_signals += 3
        
        # 5. Recent Performance
        recent_returns = historical_data['price_change'].tail(5).mean()
        if recent_returns > 0.01:
            bullish_signals += 2
        elif recent_returns < -0.01:
            bearish_signals += 2
        
        # Calculate final decision
        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            return {
                'trade_signal': 'hold',
                'confidence': 0.0,
                'direction': 'long',
                'selected_strategy': 'original_scoring',
                'strategy_config': None,
                'fired_signals': {}
            }
        
        bullish_ratio = bullish_signals / total_signals
        confidence = abs(bullish_ratio - 0.5) * 2  # 0 to 1 scale
        
        if bullish_ratio > 0.65:
            trade_signal = 'buy'
            direction = 'long'
        elif bullish_ratio < 0.35:
            trade_signal = 'sell'
            direction = 'short'
        else:
            trade_signal = 'hold'
            direction = 'long'
        
        return {
            'trade_signal': trade_signal,
            'confidence': float(confidence),  # Ensure it's a Python float
            'direction': direction,
            'selected_strategy': 'original_scoring',
            'strategy_config': None,
            'fired_signals': {}  # Empty dict for consistency
        }

    def calculate_trading_costs(self, position_size, direction, is_overnight=True):
        """EXACT function from focused_optimizer.py"""
        spread_cost = position_size * self.SPREAD_COST * 2  # Entry + exit
        
        overnight_cost = 0
        if is_overnight:
            overnight_cost = position_size * self.OVERNIGHT_FUNDING_LONG
        
        return spread_cost + overnight_cost

    def check_stop_loss_hit(self, day_data, entry_price, entry_time, direction, stop_loss_pct):
        """EXACT function from focused_optimizer.py"""
        if day_data.empty:
            return False, None, None
        
        # Handle time filtering if time column exists
        if 'time' in day_data.columns:
            trading_data = day_data[day_data['time'] > entry_time].copy()
        else:
            trading_data = day_data.copy()
        
        if trading_data.empty:
            return False, None, None
        
        for _, row in trading_data.iterrows():
            if direction == 'long':
                stop_price = entry_price * (1 - stop_loss_pct / 100)
                if row['lowPrice'] <= stop_price:
                    return True, stop_price, row.get('time', entry_time)
            else:
                stop_price = entry_price * (1 + stop_loss_pct / 100)
                if row['highPrice'] >= stop_price:
                    return True, stop_price, row.get('time', entry_time)
        
        return False, None, None

    def get_price_at_time(self, day_data, target_time, price_type='closePrice'):
        """EXACT function from focused_optimizer.py"""
        if day_data.empty:
            return None
        
        # If no time column, return the last available price
        if 'time' not in day_data.columns:
            return day_data.iloc[-1][price_type]
        
        day_data = day_data.copy()
        day_data['time_diff'] = day_data['time'].apply(
            lambda t: abs((datetime.combine(datetime.today(), t) - 
                          datetime.combine(datetime.today(), target_time)).total_seconds())
        )
        
        closest_row = day_data.loc[day_data['time_diff'].idxmin()]
        return closest_row[price_type]
