import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time
import warnings
import talib
warnings.filterwarnings("ignore")

class HybridIntelligentSystem:
    """Complete AI-powered trading logic matching the uploaded strategy files exactly."""

    def __init__(self):
        # Real Capital.com fees
        self.SPREAD_COST = 0.00019  # 0.019% per trade
        self.OVERNIGHT_FUNDING_LONG = -0.00023  # -0.023% per day for longs
        self.OVERNIGHT_FUNDING_SHORT = 0.0000071  # +0.00071% per day for shorts

    def calculate_technical_indicators(self, df):
        """Calculate comprehensive technical indicators for AI analysis"""
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
        df['sma_5'] = talib.SMA(df['closePrice'], timeperiod=5)
        df['sma_20'] = talib.SMA(df['closePrice'], timeperiod=20)
        df['sma_50'] = talib.SMA(df['closePrice'], timeperiod=50)
        df['ema_12'] = talib.EMA(df['closePrice'], timeperiod=12)
        df['ema_26'] = talib.EMA(df['closePrice'], timeperiod=26)
        
        # Momentum indicators
        df['rsi'] = talib.RSI(df['closePrice'], timeperiod=14)
        df['macd'], df['macd_signal'], df['macd_hist'] = talib.MACD(df['closePrice'])
        df['stoch_k'], df['stoch_d'] = talib.STOCH(df['highPrice'], df['lowPrice'], df['closePrice'])
        
        # Volatility indicators
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = talib.BBANDS(df['closePrice'], timeperiod=20)
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
        df['volatility'] = df['price_change'].rolling(window=20).std()
        
        return df

    def analyze_market_conditions(self, day_data, historical_data, current_date):
        """Enhanced AI-powered market condition analysis - EXACT match to uploaded files"""
        
        if day_data.empty or len(historical_data) < 50:
            return {
                'trade_signal': 'hold',
                'confidence': 0.0,
                'direction': 'long',
                'reasoning': 'Insufficient data'
            }
        
        # Get latest indicators
        latest = historical_data.iloc[-1]
        prev = historical_data.iloc[-2] if len(historical_data) > 1 else latest
        
        # Initialize scoring system
        bullish_signals = 0
        bearish_signals = 0
        confidence_factors = []
        
        # 1. Trend Analysis (Weight: 3)
        if latest['closePrice'] > latest['sma_20']:
            bullish_signals += 3
            confidence_factors.append("Price above 20-day SMA")
        else:
            bearish_signals += 3
            confidence_factors.append("Price below 20-day SMA")
        
        if latest['sma_5'] > latest['sma_20']:
            bullish_signals += 2
            confidence_factors.append("Short-term uptrend")
        else:
            bearish_signals += 2
            confidence_factors.append("Short-term downtrend")
        
        # 2. Momentum Analysis (Weight: 2)
        if 30 < latest['rsi'] < 70:
            bullish_signals += 2
            confidence_factors.append("RSI in healthy range")
        elif latest['rsi'] > 70:
            bearish_signals += 2
            confidence_factors.append("RSI overbought")
        elif latest['rsi'] < 30:
            bullish_signals += 2  # Oversold can be bullish
            confidence_factors.append("RSI oversold - potential reversal")
        
        if latest['macd'] > latest['macd_signal']:
            bullish_signals += 2
            confidence_factors.append("MACD bullish crossover")
        else:
            bearish_signals += 2
            confidence_factors.append("MACD bearish")
        
        # 3. Volume Analysis (Weight: 1)
        if latest['volume_ratio'] > 1.2:
            bullish_signals += 1
            confidence_factors.append("High volume confirmation")
        elif latest['volume_ratio'] < 0.8:
            bearish_signals += 1
            confidence_factors.append("Low volume - weak signal")
        
        # 4. Volatility Analysis (Weight: 1)
        if latest['atr'] < historical_data['atr'].rolling(20).mean().iloc[-1]:
            bullish_signals += 1
            confidence_factors.append("Low volatility - stable conditions")
        else:
            bearish_signals += 1
            confidence_factors.append("High volatility - risky conditions")
        
        # 5. Day of Week Bias (Weight: 2)
        day_of_week = current_date.strftime('%A')
        if day_of_week == 'Tuesday':
            bullish_signals += 3
            confidence_factors.append("Tuesday - optimal day")
        elif day_of_week == 'Friday':
            bullish_signals += 2
            confidence_factors.append("Friday - good day")
        elif day_of_week == 'Wednesday':
            bullish_signals += 1
            confidence_factors.append("Wednesday - decent day")
        elif day_of_week == 'Thursday':
            bearish_signals += 3
            confidence_factors.append("Thursday - avoid trading")
        
        # 6. Recent Performance (Weight: 2)
        recent_returns = historical_data['price_change'].tail(5).mean()
        if recent_returns > 0.01:  # 1% average daily gain
            bullish_signals += 2
            confidence_factors.append("Strong recent momentum")
        elif recent_returns < -0.01:
            bearish_signals += 2
            confidence_factors.append("Weak recent performance")
        
        # 7. Bollinger Bands Position (Weight: 1)
        bb_position = (latest['closePrice'] - latest['bb_lower']) / (latest['bb_upper'] - latest['bb_lower'])
        if 0.2 < bb_position < 0.8:
            bullish_signals += 1
            confidence_factors.append("Price in BB middle range")
        elif bb_position > 0.8:
            bearish_signals += 1
            confidence_factors.append("Price near BB upper - potential reversal")
        elif bb_position < 0.2:
            bullish_signals += 1
            confidence_factors.append("Price near BB lower - potential bounce")
        
        # 8. Price Momentum (Weight: 2)
        if latest['price_momentum'] > 0.02:  # 2% momentum
            bullish_signals += 2
            confidence_factors.append("Strong positive momentum")
        elif latest['price_momentum'] < -0.02:
            bearish_signals += 2
            confidence_factors.append("Strong negative momentum")
        
        # Calculate final decision
        total_signals = bullish_signals + bearish_signals
        if total_signals == 0:
            return {
                'trade_signal': 'hold',
                'confidence': 0.0,
                'direction': 'long',
                'reasoning': 'No clear signals'
            }
        
        bullish_ratio = bullish_signals / total_signals
        confidence = abs(bullish_ratio - 0.5) * 2  # 0 to 1 scale
        
        # Enhanced decision logic
        if bullish_ratio > 0.65:
            trade_signal = 'buy'
            direction = 'long'
        elif bullish_ratio < 0.35:
            trade_signal = 'sell'
            direction = 'short'
        else:
            trade_signal = 'hold'
            direction = 'long'
        
        reasoning = f"Bullish: {bullish_signals}, Bearish: {bearish_signals}, Ratio: {bullish_ratio:.2f}, Confidence: {confidence:.2f}"
        
        return {
            'trade_signal': trade_signal,
            'confidence': confidence,
            'direction': direction,
            'reasoning': reasoning,
            'factors': confidence_factors[:3],
            'bullish_signals': bullish_signals,
            'bearish_signals': bearish_signals
        }

    def calculate_trading_costs(self, position_size, direction, is_overnight=True):
        """Calculate real Capital.com trading costs"""
        spread_cost = position_size * self.SPREAD_COST * 2  # Entry + exit
        
        overnight_cost = 0
        if is_overnight:
            if direction == 'long':
                overnight_cost = position_size * self.OVERNIGHT_FUNDING_LONG
            else:
                overnight_cost = position_size * self.OVERNIGHT_FUNDING_SHORT
        
        return spread_cost + overnight_cost

    def check_stop_loss_hit(self, day_data, entry_price, entry_time, direction, stop_loss_pct):
        """Check if stop loss is hit during the day - candle by candle monitoring"""
        if day_data.empty:
            return False, None, None
        
        # Convert entry_time to datetime for comparison if it's a time object
        if isinstance(entry_time, time):
            entry_datetime = datetime.combine(datetime.today(), entry_time)
        else:
            entry_datetime = entry_time
        
        # Filter data after entry time
        trading_data = day_data.copy()
        if 'time' in trading_data.columns:
            trading_data = trading_data[trading_data['time'] > entry_time].copy()
        
        if trading_data.empty:
            return False, None, None
        
        # Check each candle for stop loss hit
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
        """Get price at specific time, or closest available"""
        if day_data.empty:
            return None
        
        if 'time' not in day_data.columns:
            # If no time column, return the last available price
            return day_data.iloc[-1][price_type]
        
        day_data = day_data.copy()
        day_data['time_diff'] = day_data['time'].apply(
            lambda t: abs((datetime.combine(datetime.today(), t) - 
                          datetime.combine(datetime.today(), target_time)).total_seconds())
        )
        
        closest_row = day_data.loc[day_data['time_diff'].idxmin()]
        return closest_row[price_type]
