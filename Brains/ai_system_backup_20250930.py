import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import warnings
import talib
warnings.filterwarnings("ignore")

class HybridIntelligentSystem:
    """EXACT AI system from uploaded focused_optimizer.py - NO MODIFICATIONS"""

    def __init__(self):
        # Real Capital.com fees - EXACT from uploaded files
        self.SPREAD_COST = 0.00019  # 0.019% per trade
        self.OVERNIGHT_FUNDING_LONG = -0.00023  # -0.023% per day for longs

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

    def analyze_market_conditions(self, day_data, historical_data, current_date):
        """EXACT function from focused_optimizer.py"""
        
        if day_data.empty or len(historical_data) < 50:
            return {
                'trade_signal': 'hold',
                'confidence': 0.0,
                'direction': 'long'
            }
        
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
                'direction': 'long'
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
            'confidence': confidence,
            'direction': direction
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
