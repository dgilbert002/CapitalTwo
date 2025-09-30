#!/usr/bin/env python3
"""
Indicator library for multi-strategy trading system.
Contains the 6 strategies from TEST1:
- RSI Oversold
- Bollinger Bands Lower Break  
- RSI Bullish Cross 50
- Price Above VWAP
- ROC Below Threshold
- MACD Positive
"""

import pandas as pd
import numpy as np
import talib

class IndicatorLibrary:
    """Library of technical indicator conditions for trading strategies"""
    
    def __init__(self, df):
        """Initialize with historical data DataFrame"""
        self.df = df.copy()
        self._prepare_indicators()
    
    def _prepare_indicators(self):
        """Pre-calculate all indicators needed for strategies"""
        # Ensure correct column names for talib
        if 'closePrice' not in self.df.columns:
            self.df.rename(columns={
                'close': 'closePrice',
                'open': 'openPrice', 
                'high': 'highPrice',
                'low': 'lowPrice',
                'volume': 'lastTradedVolume'
            }, inplace=True)
        
        # RSI calculations (for multiple periods)
        self.df['rsi_7'] = talib.RSI(self.df['closePrice'], timeperiod=7)
        self.df['rsi_14'] = talib.RSI(self.df['closePrice'], timeperiod=14)
        
        # Bollinger Bands
        self.df['bb_upper_20'], self.df['bb_middle_20'], self.df['bb_lower_20'] = talib.BBANDS(
            self.df['closePrice'], timeperiod=20, nbdevup=2.5, nbdevdn=2.5, matype=0
        )
        
        # VWAP calculation
        typical_price = (self.df['highPrice'] + self.df['lowPrice'] + self.df['closePrice']) / 3
        volume = self.df['lastTradedVolume'] if 'lastTradedVolume' in self.df.columns else self.df.get('volume', 1)
        self.df['vwap'] = (typical_price * volume).cumsum() / volume.cumsum()
        
        # Rate of Change
        self.df['roc_10'] = talib.ROC(self.df['closePrice'], timeperiod=10)
        
        # MACD
        self.df['macd'], self.df['macd_signal'], self.df['macd_hist'] = talib.MACD(
            self.df['closePrice'], fastperiod=13, slowperiod=30, signalperiod=9
        )
    
    def get_conditions(self):
        """Return dictionary of condition functions"""
        return {
            'rsi_oversold': self._rsi_oversold,
            'bb_lower_break': self._bb_lower_break,
            'rsi_bullish_cross_50': self._rsi_bullish_cross_50,
            'price_above_vwap': self._price_above_vwap,
            'roc_below_threshold': self._roc_below_threshold,
            'macd_positive': self._macd_positive
        }
    
    def _rsi_oversold(self, df, idx, period=7, threshold=25):
        """Check if RSI is oversold (below threshold)"""
        try:
            rsi_col = f'rsi_{period}'
            if rsi_col not in df.columns:
                # Calculate on the fly if not pre-calculated
                rsi = talib.RSI(df['closePrice'], timeperiod=period)
                return rsi.iloc[idx] < threshold if not pd.isna(rsi.iloc[idx]) else False
            return df[rsi_col].iloc[idx] < threshold if not pd.isna(df[rsi_col].iloc[idx]) else False
        except:
            return False
    
    def _bb_lower_break(self, df, idx, period=20, std_dev=2.5):
        """Check if price breaks below lower Bollinger Band"""
        try:
            bb_lower_col = f'bb_lower_{period}'
            if bb_lower_col not in df.columns:
                # Calculate on the fly
                upper, middle, lower = talib.BBANDS(
                    df['closePrice'], timeperiod=period, nbdevup=std_dev, nbdevdn=std_dev, matype=0
                )
                return df['closePrice'].iloc[idx] < lower.iloc[idx] if not pd.isna(lower.iloc[idx]) else False
            return df['closePrice'].iloc[idx] < df[bb_lower_col].iloc[idx] if not pd.isna(df[bb_lower_col].iloc[idx]) else False
        except:
            return False
    
    def _rsi_bullish_cross_50(self, df, idx, period=7):
        """Check if RSI crosses above 50 (bullish momentum)"""
        try:
            rsi_col = f'rsi_{period}'
            if rsi_col not in df.columns:
                rsi = talib.RSI(df['closePrice'], timeperiod=period)
            else:
                rsi = df[rsi_col]
            
            if idx < 1:
                return False
            
            # Check for cross above 50
            current = rsi.iloc[idx]
            previous = rsi.iloc[idx-1]
            
            if pd.isna(current) or pd.isna(previous):
                return False
                
            return previous <= 50 and current > 50
        except:
            return False
    
    def _price_above_vwap(self, df, idx, threshold=-0.01):
        """Check if price is above VWAP by threshold percentage"""
        try:
            if 'vwap' not in df.columns:
                # Calculate VWAP on the fly
                typical_price = (df['highPrice'] + df['lowPrice'] + df['closePrice']) / 3
                volume = df['lastTradedVolume'] if 'lastTradedVolume' in df.columns else df.get('volume', 1)
                vwap = (typical_price * volume).cumsum() / volume.cumsum()
            else:
                vwap = df['vwap']
            
            current_price = df['closePrice'].iloc[idx]
            current_vwap = vwap.iloc[idx]
            
            if pd.isna(current_vwap) or current_vwap == 0:
                return False
            
            # Calculate percentage difference
            pct_diff = (current_price - current_vwap) / current_vwap
            return pct_diff > threshold
        except:
            return False
    
    def _roc_below_threshold(self, df, idx, period=10, threshold=-0.5):
        """Check if Rate of Change is below threshold (potential reversal)"""
        try:
            roc_col = f'roc_{period}'
            if roc_col not in df.columns:
                roc = talib.ROC(df['closePrice'], timeperiod=period)
            else:
                roc = df[roc_col]
            
            current_roc = roc.iloc[idx]
            if pd.isna(current_roc):
                return False
                
            return current_roc < threshold
        except:
            return False
    
    def _macd_positive(self, df, idx, fast_period=13, slow_period=30, signal_period=9, threshold=0.05):
        """Check if MACD is positive and above threshold"""
        try:
            # Check if we need to recalculate with different parameters
            if 'macd' not in df.columns or fast_period != 12 or slow_period != 26 or signal_period != 9:
                macd, macd_signal, macd_hist = talib.MACD(
                    df['closePrice'], fastperiod=fast_period, slowperiod=slow_period, signalperiod=signal_period
                )
            else:
                macd = df['macd']
                macd_signal = df['macd_signal']
                macd_hist = df['macd_hist']
            
            current_macd = macd.iloc[idx]
            current_signal = macd_signal.iloc[idx]
            
            if pd.isna(current_macd) or pd.isna(current_signal):
                return False
            
            # Check if MACD is above signal and above threshold
            return current_macd > current_signal and current_macd > threshold
        except:
            return False


def create_indicator_library(df):
    """Factory function to create indicator library"""
    return IndicatorLibrary(df)
