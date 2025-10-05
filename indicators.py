#!/usr/bin/env python3
"""
COMPREHENSIVE TECHNICAL INDICATORS LIBRARY
Dynamic indicator calculations with configurable parameters

This library provides a unified interface for calculating technical indicators
with customizable parameters, allowing for dynamic testing and optimization.

Usage:
    from indicators import IndicatorLibrary
    
    lib = IndicatorLibrary(df)
    
    # Calculate RSI with custom period
    rsi_14 = lib.rsi(period=14)
    rsi_7 = lib.rsi(period=7)
    
    # Calculate MACD with custom parameters
    macd = lib.macd(fast_period=12, slow_period=26, signal_period=9)
    
    # Get indicator conditions
    conditions = lib.get_conditions()
    rsi_oversold = conditions['rsi_oversold'](df, idx, period=14, threshold=30)
"""

import pandas as pd
import numpy as np
import talib
from typing import Dict, Callable, Any, Optional, Tuple, List

class IndicatorLibrary:
    """
    Comprehensive technical indicators library with configurable parameters
    """
    
    def __init__(self, df: pd.DataFrame):
        """
        Initialize the indicator library with price data
        
        Args:
            df: DataFrame with columns: openPrice, highPrice, lowPrice, closePrice, lastTradedVolume
        """
        self.df = df.copy()
        self.open = df['openPrice'].values
        self.high = df['highPrice'].values
        self.low = df['lowPrice'].values
        self.close = df['closePrice'].values
        self.volume = df['lastTradedVolume'].values
        
        # Cache for calculated indicators
        self._cache = {}
    
    def _get_cache_key(self, indicator_name: str, **kwargs) -> str:
        """Generate cache key for indicator with parameters"""
        params = '_'.join([f"{k}={v}" for k, v in sorted(kwargs.items())])
        return f"{indicator_name}_{params}" if params else indicator_name
    
    # ============================================================================
    # RSI INDICATORS
    # ============================================================================
    
    def rsi(self, period: int = 14) -> np.ndarray:
        """
        Calculate RSI (Relative Strength Index)
        
        Args:
            period: RSI calculation period (default: 14)
            
        Returns:
            RSI values as numpy array
        """
        cache_key = self._get_cache_key('rsi', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.RSI(self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def connors_rsi(self, rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100) -> np.ndarray:
        """
        Calculate ConnorsRSI (3-component RSI system)
        
        Args:
            rsi_period: RSI component period (default: 3)
            streak_period: Streak RSI period (default: 2)
            rank_period: Percent rank lookback period (default: 100)
            
        Returns:
            ConnorsRSI values as numpy array
        """
        cache_key = self._get_cache_key('connors_rsi', rsi_period=rsi_period, 
                                       streak_period=streak_period, rank_period=rank_period)
        
        if cache_key not in self._cache:
            # Component 1: Standard RSI
            rsi = talib.RSI(self.close, timeperiod=rsi_period)
            
            # Component 2: Streak RSI
            price_change = pd.Series(self.close).diff()
            streak = price_change.copy()
            
            for i in range(1, len(streak)):
                if pd.isna(streak.iloc[i]):
                    continue
                if streak.iloc[i] * streak.iloc[i-1] > 0:  # Same direction
                    streak.iloc[i] = streak.iloc[i-1] + (1 if streak.iloc[i] > 0 else -1)
                else:  # Direction change
                    streak.iloc[i] = 1 if streak.iloc[i] > 0 else -1
            
            streak_rsi = talib.RSI(streak.values, timeperiod=streak_period)
            
            # Component 3: Percent Rank
            returns = pd.Series(self.close).pct_change()
            percent_rank = returns.rolling(rank_period).rank(pct=True) * 100
            
            # Combine components
            connors_rsi = (rsi + streak_rsi + percent_rank.values) / 3
            self._cache[cache_key] = connors_rsi
            
        return self._cache[cache_key]
    
    def stochastic_rsi(self, period: int = 14, fastk_period: int = 5, fastd_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Stochastic RSI
        
        Args:
            period: RSI period for Stochastic calculation (default: 14)
            fastk_period: Fast %K period (default: 5)
            fastd_period: Fast %D period (default: 3)
            
        Returns:
            Tuple of (Fast %K, Fast %D) as numpy arrays
        """
        cache_key = self._get_cache_key('stoch_rsi', period=period, 
                                       fastk_period=fastk_period, fastd_period=fastd_period)
        
        if cache_key not in self._cache:
            fastk, fastd = talib.STOCHRSI(self.close, timeperiod=period, 
                                         fastk_period=fastk_period, fastd_period=fastd_period)
            self._cache[cache_key] = (fastk, fastd)
            
        return self._cache[cache_key]
    
    # ============================================================================
    # MACD INDICATORS
    # ============================================================================
    
    def macd(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate MACD (Moving Average Convergence Divergence)
        
        Args:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line EMA period (default: 9)
            
        Returns:
            Tuple of (MACD line, Signal line, Histogram) as numpy arrays
        """
        cache_key = self._get_cache_key('macd', fast_period=fast_period, 
                                       slow_period=slow_period, signal_period=signal_period)
        
        if cache_key not in self._cache:
            macd_line, signal_line, histogram = talib.MACD(self.close, 
                                                          fastperiod=fast_period,
                                                          slowperiod=slow_period, 
                                                          signalperiod=signal_period)
            self._cache[cache_key] = (macd_line, signal_line, histogram)
            
        return self._cache[cache_key]
    
    # ============================================================================
    # STOCHASTIC INDICATORS
    # ============================================================================
    
    def stochastic(self, fastk_period: int = 5, slowk_period: int = 3, slowd_period: int = 3) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Stochastic Oscillator
        
        Args:
            fastk_period: Fast %K period (default: 5)
            slowk_period: Slow %K period (default: 3)
            slowd_period: Slow %D period (default: 3)
            
        Returns:
            Tuple of (Slow %K, Slow %D) as numpy arrays
        """
        cache_key = self._get_cache_key('stochastic', fastk_period=fastk_period,
                                       slowk_period=slowk_period, slowd_period=slowd_period)
        
        if cache_key not in self._cache:
            slowk, slowd = talib.STOCH(self.high, self.low, self.close,
                                      fastk_period=fastk_period, slowk_period=slowk_period,
                                      slowk_matype=0, slowd_period=slowd_period, slowd_matype=0)
            self._cache[cache_key] = (slowk, slowd)
            
        return self._cache[cache_key]
    
    # ============================================================================
    # BOLLINGER BANDS
    # ============================================================================
    
    def bollinger_bands(self, period: int = 20, std_dev: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Bollinger Bands
        
        Args:
            period: Moving average period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            
        Returns:
            Tuple of (Upper band, Middle band, Lower band) as numpy arrays
        """
        cache_key = self._get_cache_key('bb', period=period, std_dev=std_dev)
        
        if cache_key not in self._cache:
            upper, middle, lower = talib.BBANDS(self.close, timeperiod=period, 
                                               nbdevup=std_dev, nbdevdn=std_dev)
            self._cache[cache_key] = (upper, middle, lower)
            
        return self._cache[cache_key]
    
    def bb_position(self, period: int = 20, std_dev: float = 2.0) -> np.ndarray:
        """
        Calculate position within Bollinger Bands (0 = lower band, 1 = upper band)
        
        Args:
            period: Moving average period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            
        Returns:
            Position values as numpy array
        """
        upper, middle, lower = self.bollinger_bands(period, std_dev)
        return (self.close - lower) / (upper - lower)
    
    def bb_width(self, period: int = 20, std_dev: float = 2.0) -> np.ndarray:
        """
        Calculate Bollinger Bands width (normalized by middle band)
        
        Args:
            period: Moving average period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)
            
        Returns:
            Width values as numpy array
        """
        upper, middle, lower = self.bollinger_bands(period, std_dev)
        return (upper - lower) / middle
    
    # ============================================================================
    # OTHER OSCILLATORS
    # ============================================================================
    
    def williams_r(self, period: int = 14) -> np.ndarray:
        """
        Calculate Williams %R
        
        Args:
            period: Lookback period (default: 14)
            
        Returns:
            Williams %R values as numpy array
        """
        cache_key = self._get_cache_key('willr', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.WILLR(self.high, self.low, self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def cci(self, period: int = 14) -> np.ndarray:
        """
        Calculate Commodity Channel Index (CCI)
        
        Args:
            period: Calculation period (default: 14)
            
        Returns:
            CCI values as numpy array
        """
        cache_key = self._get_cache_key('cci', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.CCI(self.high, self.low, self.close, timeperiod=period)
        return self._cache[cache_key]
    
    # ============================================================================
    # VOLATILITY INDICATORS
    # ============================================================================
    
    def atr(self, period: int = 14) -> np.ndarray:
        """
        Calculate Average True Range (ATR)
        
        Args:
            period: ATR period (default: 14)
            
        Returns:
            ATR values as numpy array
        """
        cache_key = self._get_cache_key('atr', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.ATR(self.high, self.low, self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def atr_percent(self, period: int = 14) -> np.ndarray:
        """
        Calculate ATR as percentage of close price
        
        Args:
            period: ATR period (default: 14)
            
        Returns:
            ATR percentage values as numpy array
        """
        atr_values = self.atr(period)
        return (atr_values / self.close) * 100
    
    # ============================================================================
    # TREND INDICATORS
    # ============================================================================
    
    def parabolic_sar(self, acceleration: float = 0.02, maximum: float = 0.2) -> np.ndarray:
        """
        Calculate Parabolic SAR
        
        Args:
            acceleration: Acceleration factor (default: 0.02)
            maximum: Maximum acceleration (default: 0.2)
            
        Returns:
            SAR values as numpy array
        """
        cache_key = self._get_cache_key('sar', acceleration=acceleration, maximum=maximum)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.SAR(self.high, self.low, 
                                              acceleration=acceleration, maximum=maximum)
        return self._cache[cache_key]
    
    def adx(self, period: int = 14) -> np.ndarray:
        """
        Calculate Average Directional Index (ADX)
        
        Args:
            period: ADX period (default: 14)
            
        Returns:
            ADX values as numpy array
        """
        cache_key = self._get_cache_key('adx', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.ADX(self.high, self.low, self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def aroon(self, period: int = 14) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Aroon Up and Aroon Down
        
        Args:
            period: Aroon period (default: 14)
            
        Returns:
            Tuple of (Aroon Up, Aroon Down) as numpy arrays
        """
        cache_key = self._get_cache_key('aroon', period=period)
        if cache_key not in self._cache:
            aroon_up, aroon_down = talib.AROON(self.high, self.low, timeperiod=period)
            self._cache[cache_key] = (aroon_up, aroon_down)
        return self._cache[cache_key]
    
    # ============================================================================
    # MOVING AVERAGES
    # ============================================================================
    
    def sma(self, period: int = 20) -> np.ndarray:
        """
        Calculate Simple Moving Average (SMA)
        
        Args:
            period: SMA period (default: 20)
            
        Returns:
            SMA values as numpy array
        """
        cache_key = self._get_cache_key('sma', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.SMA(self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def ema(self, period: int = 20) -> np.ndarray:
        """
        Calculate Exponential Moving Average (EMA)
        
        Args:
            period: EMA period (default: 20)
            
        Returns:
            EMA values as numpy array
        """
        cache_key = self._get_cache_key('ema', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.EMA(self.close, timeperiod=period)
        return self._cache[cache_key]
    
    # ============================================================================
    # VOLUME INDICATORS
    # ============================================================================
    
    def obv(self) -> np.ndarray:
        """
        Calculate On-Balance Volume (OBV)
        
        Returns:
            OBV values as numpy array
        """
        cache_key = 'obv'
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.OBV(self.close, self.volume)
        return self._cache[cache_key]
    
    def volume_sma(self, period: int = 20) -> np.ndarray:
        """
        Calculate Volume Simple Moving Average
        
        Args:
            period: SMA period (default: 20)
            
        Returns:
            Volume SMA values as numpy array
        """
        cache_key = self._get_cache_key('volume_sma', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.SMA(self.volume, timeperiod=period)
        return self._cache[cache_key]
    
    def volume_ratio(self, period: int = 20) -> np.ndarray:
        """
        Calculate Volume Ratio (current volume / average volume)
        
        Args:
            period: Average volume period (default: 20)
            
        Returns:
            Volume ratio values as numpy array
        """
        volume_avg = self.volume_sma(period)
        return self.volume / volume_avg
    
    def vwap(self) -> np.ndarray:
        """
        Calculate Volume Weighted Average Price (VWAP)
        
        Returns:
            VWAP values as numpy array
        """
        cache_key = 'vwap'
        if cache_key not in self._cache:
            typical_price = (self.high + self.low + self.close) / 3
            cumulative_volume = np.cumsum(self.volume)
            cumulative_pv = np.cumsum(typical_price * self.volume)
            
            # Avoid division by zero
            vwap = np.where(cumulative_volume != 0, cumulative_pv / cumulative_volume, typical_price)
            self._cache[cache_key] = vwap
            
        return self._cache[cache_key]
    
    def vwap_deviation(self) -> np.ndarray:
        """
        Calculate deviation from VWAP as percentage
        
        Returns:
            VWAP deviation values as numpy array
        """
        vwap_values = self.vwap()
        return (self.close - vwap_values) / vwap_values
    
    # ============================================================================
    # MOMENTUM INDICATORS
    # ============================================================================
    
    def momentum(self, period: int = 10) -> np.ndarray:
        """
        Calculate Momentum
        
        Args:
            period: Momentum period (default: 10)
            
        Returns:
            Momentum values as numpy array
        """
        cache_key = self._get_cache_key('momentum', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.MOM(self.close, timeperiod=period)
        return self._cache[cache_key]
    
    def roc(self, period: int = 10) -> np.ndarray:
        """
        Calculate Rate of Change (ROC)
        
        Args:
            period: ROC period (default: 10)
            
        Returns:
            ROC values as numpy array
        """
        cache_key = self._get_cache_key('roc', period=period)
        if cache_key not in self._cache:
            self._cache[cache_key] = talib.ROC(self.close, timeperiod=period)
        return self._cache[cache_key]
    
    # ============================================================================
    # MODERN INDICATORS (ADDED)
    # ============================================================================
    
    def supertrend(self, period: int = 10, multiplier: float = 3.0) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Supertrend indicator
        
        Args:
            period: ATR period (default: 10)
            multiplier: ATR multiplier (default: 3.0)
            
        Returns:
            Tuple of (supertrend_line, direction) where direction is 1 for bullish, -1 for bearish
        """
        cache_key = self._get_cache_key('supertrend', period=period, multiplier=multiplier)
        if cache_key not in self._cache:
            atr = self.atr(period)
            hl_avg = (self.high + self.low) / 2
            
            # Calculate basic bands
            upper_band = hl_avg + (multiplier * atr)
            lower_band = hl_avg - (multiplier * atr)
            
            # Initialize arrays
            supertrend = np.zeros_like(self.close)
            direction = np.zeros_like(self.close)
            
            # Calculate Supertrend
            for i in range(period, len(self.close)):
                # Update bands
                if lower_band[i] > lower_band[i-1] or self.close[i-1] < lower_band[i-1]:
                    lower_band[i] = lower_band[i]
                else:
                    lower_band[i] = lower_band[i-1]
                
                if upper_band[i] < upper_band[i-1] or self.close[i-1] > upper_band[i-1]:
                    upper_band[i] = upper_band[i]
                else:
                    upper_band[i] = upper_band[i-1]
                
                # Determine trend direction
                if i == period:
                    if self.close[i] <= upper_band[i]:
                        direction[i] = -1
                        supertrend[i] = upper_band[i]
                    else:
                        direction[i] = 1
                        supertrend[i] = lower_band[i]
                else:
                    if direction[i-1] == 1:
                        if self.close[i] <= lower_band[i]:
                            direction[i] = -1
                            supertrend[i] = upper_band[i]
                        else:
                            direction[i] = 1
                            supertrend[i] = lower_band[i]
                    else:
                        if self.close[i] >= upper_band[i]:
                            direction[i] = 1
                            supertrend[i] = lower_band[i]
                        else:
                            direction[i] = -1
                            supertrend[i] = upper_band[i]
            
            self._cache[cache_key] = (supertrend, direction)
        return self._cache[cache_key]
    
    def keltner_channels(self, period: int = 20, multiplier: float = 2.0) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Keltner Channels
        
        Args:
            period: EMA period (default: 20)
            multiplier: ATR multiplier (default: 2.0)
            
        Returns:
            Tuple of (middle_band, upper_band, lower_band)
        """
        cache_key = self._get_cache_key('keltner_channels', period=period, multiplier=multiplier)
        if cache_key not in self._cache:
            middle = self.ema(period)
            atr = self.atr(period)
            upper = middle + (multiplier * atr)
            lower = middle - (multiplier * atr)
            self._cache[cache_key] = (middle, upper, lower)
        return self._cache[cache_key]
    
    def ttm_squeeze(self, bb_period: int = 20, bb_std: float = 2.0, 
                    kc_period: int = 20, kc_mult: float = 1.5) -> np.ndarray:
        """
        Calculate TTM Squeeze indicator
        
        Args:
            bb_period: Bollinger Bands period (default: 20)
            bb_std: Bollinger Bands standard deviation (default: 2.0)
            kc_period: Keltner Channel period (default: 20)
            kc_mult: Keltner Channel ATR multiplier (default: 1.5)
            
        Returns:
            Squeeze values: 1 for squeeze on, 0 for squeeze off
        """
        cache_key = self._get_cache_key('ttm_squeeze', bb_period=bb_period, bb_std=bb_std,
                                       kc_period=kc_period, kc_mult=kc_mult)
        if cache_key not in self._cache:
            # Get Bollinger Bands
            bb_middle, bb_upper, bb_lower = self.bollinger_bands(bb_period, bb_std)
            
            # Get Keltner Channels
            kc_middle, kc_upper, kc_lower = self.keltner_channels(kc_period, kc_mult)
            
            # Squeeze is on when BB are inside KC
            squeeze = (bb_upper < kc_upper) & (bb_lower > kc_lower)
            self._cache[cache_key] = squeeze.astype(float)
        return self._cache[cache_key]
    
    def fisher_transform(self, period: int = 10) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Fisher Transform
        
        Args:
            period: Lookback period (default: 10)
            
        Returns:
            Tuple of (fisher, trigger) values
        """
        cache_key = self._get_cache_key('fisher_transform', period=period)
        if cache_key not in self._cache:
            # Calculate normalized price
            min_low = pd.Series(self.low).rolling(period).min()
            max_high = pd.Series(self.high).rolling(period).max()
            
            # Normalize price to -1 to 1
            value = np.zeros_like(self.close)
            for i in range(period, len(self.close)):
                if max_high.iloc[i] != min_low.iloc[i]:
                    value[i] = 2 * ((self.close[i] - min_low.iloc[i]) / 
                                  (max_high.iloc[i] - min_low.iloc[i]) - 0.5)
                    # Constrain to avoid infinity
                    value[i] = np.clip(value[i], -0.999, 0.999)
            
            # Apply Fisher Transform
            fisher = np.zeros_like(self.close)
            for i in range(1, len(self.close)):
                fisher[i] = 0.5 * fisher[i-1] + 0.5 * np.log((1 + value[i]) / (1 - value[i]))
            
            # Trigger is the previous Fisher value
            trigger = np.roll(fisher, 1)
            
            self._cache[cache_key] = (fisher, trigger)
        return self._cache[cache_key]
    
    def chaikin_money_flow(self, period: int = 20) -> np.ndarray:
        """
        Calculate Chaikin Money Flow (CMF)
        
        Args:
            period: Lookback period (default: 20)
            
        Returns:
            CMF values
        """
        cache_key = self._get_cache_key('chaikin_money_flow', period=period)
        if cache_key not in self._cache:
            # Calculate Money Flow Multiplier
            mf_mult = ((self.close - self.low) - (self.high - self.close)) / (self.high - self.low)
            mf_mult = np.nan_to_num(mf_mult, 0)  # Handle division by zero
            
            # Calculate Money Flow Volume
            mf_volume = mf_mult * self.volume
            
            # Calculate CMF
            cmf = pd.Series(mf_volume).rolling(period).sum() / pd.Series(self.volume).rolling(period).sum()
            self._cache[cache_key] = cmf.values
        return self._cache[cache_key]
    
    def donchian_channels(self, period: int = 20) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Donchian Channels
        
        Args:
            period: Lookback period (default: 20)
            
        Returns:
            Tuple of (middle, upper, lower) channels
        """
        cache_key = self._get_cache_key('donchian_channels', period=period)
        if cache_key not in self._cache:
            upper = pd.Series(self.high).rolling(period).max().values
            lower = pd.Series(self.low).rolling(period).min().values
            middle = (upper + lower) / 2
            self._cache[cache_key] = (middle, upper, lower)
        return self._cache[cache_key]
    
    def trix(self, period: int = 14) -> np.ndarray:
        """
        Calculate TRIX (Triple Exponential Average)
        
        Args:
            period: EMA period (default: 14)
            
        Returns:
            TRIX values (rate of change of triple EMA)
        """
        cache_key = self._get_cache_key('trix', period=period)
        if cache_key not in self._cache:
            # Calculate triple exponential moving average
            ema1 = talib.EMA(self.close, timeperiod=period)
            ema2 = talib.EMA(ema1, timeperiod=period)
            ema3 = talib.EMA(ema2, timeperiod=period)
            
            # Calculate rate of change
            trix = talib.ROC(ema3, timeperiod=1)
            self._cache[cache_key] = trix
        return self._cache[cache_key]
    
    def true_strength_index(self, fast_period: int = 13, slow_period: int = 25) -> np.ndarray:
        """
        Calculate True Strength Index (TSI)
        
        Args:
            fast_period: Fast EMA period (default: 13)
            slow_period: Slow EMA period (default: 25)
            
        Returns:
            TSI values
        """
        cache_key = self._get_cache_key('true_strength_index', fast_period=fast_period, slow_period=slow_period)
        if cache_key not in self._cache:
            # Calculate price momentum
            mom = pd.Series(self.close).diff()
            
            # Calculate double smoothed momentum
            ema_slow = mom.ewm(span=slow_period, adjust=False).mean()
            ema_fast = ema_slow.ewm(span=fast_period, adjust=False).mean()
            
            # Calculate double smoothed absolute momentum
            abs_mom = mom.abs()
            abs_ema_slow = abs_mom.ewm(span=slow_period, adjust=False).mean()
            abs_ema_fast = abs_ema_slow.ewm(span=fast_period, adjust=False).mean()
            
            # Calculate TSI
            tsi = 100 * (ema_fast / abs_ema_fast)
            self._cache[cache_key] = tsi.values
        return self._cache[cache_key]

    # ============================================================================
    # CRASH PROTECTION & RECOVERY INDICATORS
    # ============================================================================
    
    def ulcer_index(self, period: int = 14) -> np.ndarray:
        """
        Calculate Ulcer Index - measures downside volatility and crash risk
        Higher values indicate greater downside risk/stress
        
        Parameters:
            period: Lookback period for calculation (default: 14)
            
        Returns:
            Array of Ulcer Index values
        """
        cache_key = f'ulcer_index_{period}'
        if cache_key not in self._cache:
            close = self.df['closePrice'].values
            
            # Calculate rolling maximum (peak)
            rolling_max = pd.Series(close).rolling(window=period, min_periods=1).max()
            
            # Calculate percentage drawdown from peak
            drawdown_pct = ((close - rolling_max) / rolling_max) * 100
            
            # Square the drawdowns (penalizes larger drawdowns more)
            squared_dd = drawdown_pct ** 2
            
            # Calculate mean of squared drawdowns
            mean_squared_dd = pd.Series(squared_dd).rolling(window=period, min_periods=1).mean()
            
            # Take square root to get Ulcer Index
            ulcer_index = np.sqrt(mean_squared_dd)
            
            self._cache[cache_key] = ulcer_index.values
        return self._cache[cache_key]
    
    def maximum_drawdown(self, period: int = 252) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Maximum Drawdown indicator
        Tracks running drawdown percentage from recent peak
        
        Parameters:
            period: Lookback period for rolling maximum (default: 252 for 1 year)
            
        Returns:
            Tuple of (drawdown_pct, drawdown_duration)
        """
        cache_key = f'maximum_drawdown_{period}'
        if cache_key not in self._cache:
            close = self.df['closePrice'].values
            
            # Calculate rolling maximum (peak)
            rolling_max = pd.Series(close).rolling(window=period, min_periods=1).max()
            
            # Calculate percentage drawdown from peak
            drawdown_pct = ((close - rolling_max) / rolling_max) * 100
            
            # Calculate drawdown duration (bars since last peak)
            duration = np.zeros(len(close))
            for i in range(1, len(close)):
                if close[i] >= rolling_max.iloc[i]:
                    duration[i] = 0
                else:
                    duration[i] = duration[i-1] + 1
            
            self._cache[cache_key] = (drawdown_pct.values, duration)
        return self._cache[cache_key]
    
    def coppock_curve(self, roc1_period: int = 14, roc2_period: int = 11, wma_period: int = 10) -> np.ndarray:
        """
        Calculate Coppock Curve - identifies major market bottoms
        Designed specifically to identify buying opportunities after major declines
        
        Parameters:
            roc1_period: First ROC period (default: 14)
            roc2_period: Second ROC period (default: 11)
            wma_period: Weighted MA period (default: 10)
            
        Returns:
            Array of Coppock Curve values
        """
        cache_key = f'coppock_curve_{roc1_period}_{roc2_period}_{wma_period}'
        if cache_key not in self._cache:
            close = self.df['closePrice'].values
            
            # Calculate two ROC values
            roc1 = self.roc(period=roc1_period)
            roc2 = self.roc(period=roc2_period)
            
            # Sum the ROCs
            roc_sum = roc1 + roc2
            
            # Apply weighted moving average
            weights = np.arange(1, wma_period + 1)
            coppock = pd.Series(roc_sum).rolling(window=wma_period, min_periods=wma_period).apply(
                lambda x: np.dot(x, weights) / weights.sum() if len(x) == wma_period else np.nan
            )
            
            self._cache[cache_key] = coppock.values
        return self._cache[cache_key]
    
    def volatility_stop(self, period: int = 20, multiplier: float = 2.5) -> Tuple[np.ndarray, np.ndarray]:
        """
        Calculate Volatility Stop (Chandelier Exit)
        Dynamic stop loss that adapts to market volatility
        
        Parameters:
            period: ATR period (default: 20)
            multiplier: ATR multiplier (default: 2.5)
            
        Returns:
            Tuple of (long_stop, short_stop)
        """
        cache_key = f'volatility_stop_{period}_{multiplier}'
        if cache_key not in self._cache:
            high = self.df['highPrice'].values
            low = self.df['lowPrice'].values
            close = self.df['closePrice'].values
            
            atr = self.atr(period)
            
            # Calculate highest high and lowest low
            highest = pd.Series(high).rolling(window=period, min_periods=1).max().values
            lowest = pd.Series(low).rolling(window=period, min_periods=1).min().values
            
            # Calculate stops
            long_stop = highest - (atr * multiplier)
            short_stop = lowest + (atr * multiplier)
            
            self._cache[cache_key] = (long_stop, short_stop)
        return self._cache[cache_key]
    
    def market_regime(self, adx_period: int = 14, adx_threshold: float = 25) -> np.ndarray:
        """
        Calculate Market Regime Filter
        Identifies trending vs ranging vs crash markets
        
        Parameters:
            adx_period: Period for ADX calculation (default: 14)
            adx_threshold: Threshold for trend strength (default: 25)
            
        Returns:
            Array of regime values: 2=Strong Trend, 1=Weak Trend, 0=Range, -1=Crash
        """
        cache_key = f'market_regime_{adx_period}_{adx_threshold}'
        if cache_key not in self._cache:
            close = self.df['closePrice'].values
            
            # Get ADX for trend strength
            adx = self.adx(adx_period)
            
            # Get drawdown for crash detection
            dd_pct, _ = self.maximum_drawdown(period=20)
            
            # Calculate short and long MAs for trend direction
            ma_short = pd.Series(close).rolling(window=10, min_periods=1).mean().values
            ma_long = pd.Series(close).rolling(window=50, min_periods=1).mean().values
            
            # Determine regime
            regime = np.zeros(len(close))
            for i in range(len(close)):
                if dd_pct[i] < -10:  # Crash mode
                    regime[i] = -1
                elif adx[i] > adx_threshold:  # Trending
                    if ma_short[i] > ma_long[i]:
                        regime[i] = 2  # Strong uptrend
                    else:
                        regime[i] = -2  # Strong downtrend
                else:  # Ranging
                    regime[i] = 0
            
            self._cache[cache_key] = regime
        return self._cache[cache_key]
    
    def accumulation_distribution(self) -> np.ndarray:
        """
        Calculate Accumulation/Distribution Line
        Shows if smart money is accumulating or distributing
        
        Returns:
            Array of A/D Line values
        """
        cache_key = 'accumulation_distribution'
        if cache_key not in self._cache:
            high = self.df['highPrice'].values
            low = self.df['lowPrice'].values
            close = self.df['closePrice'].values
            volume = self.df['lastTradedVolume'].values
            
            # Calculate money flow multiplier
            mfm = np.where(high != low,
                          ((close - low) - (high - close)) / (high - low),
                          0)
            
            # Calculate money flow volume
            mfv = mfm * volume
            
            # Calculate cumulative A/D Line
            ad_line = np.cumsum(mfv)
            
            self._cache[cache_key] = ad_line
        return self._cache[cache_key]
    
    def inverse_fisher_rsi(self, period: int = 5) -> np.ndarray:
        """
        Calculate Inverse Fisher Transform of RSI
        Provides sharper, more binary signals (-1 to +1)
        
        Parameters:
            period: RSI period (default: 5)
            
        Returns:
            Array of IFT RSI values (-1 to +1)
        """
        cache_key = f'inverse_fisher_rsi_{period}'
        if cache_key not in self._cache:
            # Get RSI
            rsi = self.rsi(period)
            
            # Normalize RSI to -1 to +1
            normalized_rsi = 0.1 * (rsi - 50)
            
            # Apply Inverse Fisher Transform
            ift_rsi = (np.exp(2 * normalized_rsi) - 1) / (np.exp(2 * normalized_rsi) + 1)
            
            self._cache[cache_key] = ift_rsi
        return self._cache[cache_key]
    
    def heikin_ashi(self) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Heikin-Ashi candles
        Smoothed candles that filter out market noise
        
        Returns:
            Tuple of (ha_open, ha_high, ha_low, ha_close)
        """
        cache_key = 'heikin_ashi'
        if cache_key not in self._cache:
            open_price = self.df['openPrice'].values
            high = self.df['highPrice'].values
            low = self.df['lowPrice'].values
            close = self.df['closePrice'].values
            
            ha_close = (open_price + high + low + close) / 4
            ha_open = np.zeros(len(close))
            ha_high = np.zeros(len(close))
            ha_low = np.zeros(len(close))
            
            # First candle
            ha_open[0] = (open_price[0] + close[0]) / 2
            ha_high[0] = high[0]
            ha_low[0] = low[0]
            
            # Calculate rest
            for i in range(1, len(close)):
                ha_open[i] = (ha_open[i-1] + ha_close[i-1]) / 2
                ha_high[i] = max(high[i], ha_open[i], ha_close[i])
                ha_low[i] = min(low[i], ha_open[i], ha_close[i])
            
            self._cache[cache_key] = (ha_open, ha_high, ha_low, ha_close)
        return self._cache[cache_key]
    
    def pivot_points(self, pivot_type: str = 'camarilla') -> Dict[str, np.ndarray]:
        """
        Calculate Pivot Points (Camarilla or Classic)
        Key support and resistance levels
        
        Parameters:
            pivot_type: 'camarilla' or 'classic' (default: 'camarilla')
            
        Returns:
            Dictionary with pivot levels (PP, R1-R4, S1-S4)
        """
        cache_key = f'pivot_points_{pivot_type}'
        if cache_key not in self._cache:
            high = self.df['highPrice'].values
            low = self.df['lowPrice'].values
            close = self.df['closePrice'].values
            
            # Calculate pivot point
            pp = (high + low + close) / 3
            
            levels = {'PP': pp}
            
            if pivot_type == 'camarilla':
                # Camarilla pivot points
                range_hl = high - low
                levels['R4'] = close + range_hl * 1.1 / 2
                levels['R3'] = close + range_hl * 1.1 / 4
                levels['R2'] = close + range_hl * 1.1 / 6
                levels['R1'] = close + range_hl * 1.1 / 12
                levels['S1'] = close - range_hl * 1.1 / 12
                levels['S2'] = close - range_hl * 1.1 / 6
                levels['S3'] = close - range_hl * 1.1 / 4
                levels['S4'] = close - range_hl * 1.1 / 2
            else:  # classic
                levels['R3'] = pp + 2 * (high - low)
                levels['R2'] = pp + (high - low)
                levels['R1'] = 2 * pp - low
                levels['S1'] = 2 * pp - high
                levels['S2'] = pp - (high - low)
                levels['S3'] = pp - 2 * (high - low)
            
            self._cache[cache_key] = levels
        return self._cache[cache_key]
    
    def volume_weighted_macd(self, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """
        Calculate Volume-Weighted MACD
        MACD that considers volume for confirmation
        
        Parameters:
            fast_period: Fast EMA period (default: 12)
            slow_period: Slow EMA period (default: 26)
            signal_period: Signal line period (default: 9)
            
        Returns:
            Tuple of (vwmacd_line, vwmacd_signal, vwmacd_histogram)
        """
        cache_key = f'volume_weighted_macd_{fast_period}_{slow_period}_{signal_period}'
        if cache_key not in self._cache:
            close = self.df['closePrice'].values
            volume = self.df['lastTradedVolume'].values
            
            # Calculate volume-weighted price
            vwp = close * volume
            
            # Calculate volume-weighted EMAs
            vwp_series = pd.Series(vwp)
            vol_series = pd.Series(volume)
            
            # Fast VWMA
            vwp_fast_ema = vwp_series.ewm(span=fast_period, adjust=False).mean()
            vol_fast_ema = vol_series.ewm(span=fast_period, adjust=False).mean()
            vwma_fast = vwp_fast_ema / vol_fast_ema
            
            # Slow VWMA
            vwp_slow_ema = vwp_series.ewm(span=slow_period, adjust=False).mean()
            vol_slow_ema = vol_series.ewm(span=slow_period, adjust=False).mean()
            vwma_slow = vwp_slow_ema / vol_slow_ema
            
            # VWMACD line
            vwmacd_line = vwma_fast - vwma_slow
            
            # Signal line
            vwmacd_signal = vwmacd_line.ewm(span=signal_period, adjust=False).mean()
            
            # Histogram
            vwmacd_hist = vwmacd_line - vwmacd_signal
            
            self._cache[cache_key] = (vwmacd_line.values, vwmacd_signal.values, vwmacd_hist.values)
        return self._cache[cache_key]

    # ============================================================================
    # CONDITION FUNCTIONS
    # ============================================================================
    
    def get_conditions(self) -> Dict[str, Callable]:
        """
        Get dictionary of condition functions for strategy testing
        
        Returns:
            Dictionary mapping condition names to callable functions
        """
        
        def safe_get_value(arr: np.ndarray, idx: int, default: float = np.nan) -> float:
            """Safely get value from array at index"""
            if idx < 0 or idx >= len(arr) or np.isnan(arr[idx]):
                return default
            return arr[idx]
        
        def safe_get_prev_value(arr: np.ndarray, idx: int, default: float = np.nan) -> float:
            """Safely get previous value from array"""
            if idx <= 0 or idx >= len(arr) or np.isnan(arr[idx-1]):
                return default
            return arr[idx-1]
        
        conditions = {
            # RSI Conditions
            'rsi_oversold': lambda df, idx, period=14, threshold=30: (
                safe_get_value(self.rsi(period), idx) < threshold
            ),
            'rsi_overbought': lambda df, idx, period=14, threshold=70: (
                safe_get_value(self.rsi(period), idx) > threshold
            ),
            'rsi_bullish_cross_50': lambda df, idx, period=14, cross_level=50: (
                safe_get_value(self.rsi(period), idx) > cross_level and 
                safe_get_prev_value(self.rsi(period), idx) <= cross_level
            ),
            'rsi_bearish_cross_50': lambda df, idx, period=14, cross_level=50: (
                safe_get_value(self.rsi(period), idx) < cross_level and 
                safe_get_prev_value(self.rsi(period), idx) >= cross_level
            ),
            
            # ConnorsRSI Conditions
            'connors_rsi_oversold': lambda df, idx, rsi_period=3, streak_period=2, rank_period=100, threshold=25: (
                safe_get_value(self.connors_rsi(rsi_period, streak_period, rank_period), idx) < threshold
            ),
            'connors_rsi_very_oversold': lambda df, idx, rsi_period=3, streak_period=2, rank_period=100, threshold=20: (
                safe_get_value(self.connors_rsi(rsi_period, streak_period, rank_period), idx) < threshold
            ),
            'connors_rsi_overbought': lambda df, idx, rsi_period=3, streak_period=2, rank_period=100, threshold=75: (
                safe_get_value(self.connors_rsi(rsi_period, streak_period, rank_period), idx) > threshold
            ),
            'connors_rsi_bullish_cross': lambda df, idx, rsi_period=3, streak_period=2, rank_period=100, cross_level=50: (
                safe_get_value(self.connors_rsi(rsi_period, streak_period, rank_period), idx) > cross_level and 
                safe_get_prev_value(self.connors_rsi(rsi_period, streak_period, rank_period), idx) <= cross_level
            ),
            
            # MACD Conditions
            'macd_positive': lambda df, idx, fast_period=12, slow_period=26, signal_period=9, threshold=0: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[0], idx) > threshold
            ),
            'macd_negative': lambda df, idx, fast_period=12, slow_period=26, signal_period=9, threshold=0: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[0], idx) < threshold
            ),
            'macd_bullish_cross': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[0], idx) > 
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[1], idx) and
                safe_get_prev_value(self.macd(fast_period, slow_period, signal_period)[0], idx) <= 
                safe_get_prev_value(self.macd(fast_period, slow_period, signal_period)[1], idx)
            ),
            'macd_bearish_cross': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[0], idx) < 
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[1], idx) and
                safe_get_prev_value(self.macd(fast_period, slow_period, signal_period)[0], idx) >= 
                safe_get_prev_value(self.macd(fast_period, slow_period, signal_period)[1], idx)
            ),
            'macd_histogram_positive': lambda df, idx, fast_period=12, slow_period=26, signal_period=9, threshold=0: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[2], idx) > threshold
            ),
            'macd_histogram_negative': lambda df, idx, fast_period=12, slow_period=26, signal_period=9, threshold=0: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[2], idx) < threshold
            ),
            'macd_histogram_increasing': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.macd(fast_period, slow_period, signal_period)[2], idx) > 
                safe_get_prev_value(self.macd(fast_period, slow_period, signal_period)[2], idx)
            ),
            
            # Stochastic Conditions
            'stoch_oversold': lambda df, idx, fastk_period=5, slowk_period=3, slowd_period=3, threshold=20: (
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) < threshold and
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx) < threshold
            ),
            'stoch_overbought': lambda df, idx, fastk_period=5, slowk_period=3, slowd_period=3, threshold=80: (
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) > threshold and
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx) > threshold
            ),
            'stoch_rsi_oversold': lambda df, idx, period=14, fastk_period=5, fastd_period=3, threshold=0.2: (
                safe_get_value(self.stochastic_rsi(period, fastk_period, fastd_period)[0], idx) < threshold
            ),
            'stoch_rsi_overbought': lambda df, idx, period=14, fastk_period=5, fastd_period=3, threshold=0.8: (
                safe_get_value(self.stochastic_rsi(period, fastk_period, fastd_period)[0], idx) > threshold
            ),
            'stoch_bullish_cross': lambda df, idx, fastk_period=5, slowk_period=3, slowd_period=3: (
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) >
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx) and
                safe_get_prev_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) <=
                safe_get_prev_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx)
            ),
            'stoch_bearish_cross': lambda df, idx, fastk_period=5, slowk_period=3, slowd_period=3: (
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) <
                safe_get_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx) and
                safe_get_prev_value(self.stochastic(fastk_period, slowk_period, slowd_period)[0], idx) >=
                safe_get_prev_value(self.stochastic(fastk_period, slowk_period, slowd_period)[1], idx)
            ),
            
            # Bollinger Bands Conditions
            'bb_oversold': lambda df, idx, period=20, std_dev=2.0, threshold=0.2: (
                safe_get_value(self.bb_position(period, std_dev), idx) < threshold
            ),
            'bb_very_oversold': lambda df, idx, period=20, std_dev=2.0, threshold=0.1: (
                safe_get_value(self.bb_position(period, std_dev), idx) < threshold
            ),
            'bb_overbought': lambda df, idx, period=20, std_dev=2.0, threshold=0.8: (
                safe_get_value(self.bb_position(period, std_dev), idx) > threshold
            ),
            'bb_very_overbought': lambda df, idx, period=20, std_dev=2.0, threshold=0.9: (
                safe_get_value(self.bb_position(period, std_dev), idx) > threshold
            ),
            'bb_squeeze': lambda df, idx, period=20, std_dev=2.0, threshold=0.02: (
                safe_get_value(self.bb_width(period, std_dev), idx) < threshold
            ),
            'bb_expansion': lambda df, idx, period=20, std_dev=2.0, threshold=0.05: (
                safe_get_value(self.bb_width(period, std_dev), idx) > threshold
            ),
            'bb_upper_break': lambda df, idx, period=20, std_dev=2.0: (
                safe_get_value(self.close, idx) > safe_get_value(self.bollinger_bands(period, std_dev)[0], idx)
            ),
            'bb_lower_break': lambda df, idx, period=20, std_dev=2.0: (
                safe_get_value(self.close, idx) < safe_get_value(self.bollinger_bands(period, std_dev)[2], idx)
            ),
            
            # Williams %R Conditions
            'willr_oversold': lambda df, idx, period=14, threshold=-80: (
                safe_get_value(self.williams_r(period), idx) < threshold
            ),
            'willr_very_oversold': lambda df, idx, period=14, threshold=-90: (
                safe_get_value(self.williams_r(period), idx) < threshold
            ),
            'willr_overbought': lambda df, idx, period=14, threshold=-20: (
                safe_get_value(self.williams_r(period), idx) > threshold
            ),
            'willr_very_overbought': lambda df, idx, period=14, threshold=-10: (
                safe_get_value(self.williams_r(period), idx) > threshold
            ),
            
            # CCI Conditions
            'cci_oversold': lambda df, idx, period=14, threshold=-100: (
                safe_get_value(self.cci(period), idx) < threshold
            ),
            'cci_very_oversold': lambda df, idx, period=14, threshold=-200: (
                safe_get_value(self.cci(period), idx) < threshold
            ),
            'cci_overbought': lambda df, idx, period=14, threshold=100: (
                safe_get_value(self.cci(period), idx) > threshold
            ),
            'cci_very_overbought': lambda df, idx, period=14, threshold=200: (
                safe_get_value(self.cci(period), idx) > threshold
            ),
            'cci_bullish_cross_zero': lambda df, idx, period=14, cross_level=0: (
                safe_get_value(self.cci(period), idx) > cross_level and 
                safe_get_prev_value(self.cci(period), idx) <= cross_level
            ),
            'cci_bearish_cross_zero': lambda df, idx, period=14, cross_level=0: (
                safe_get_value(self.cci(period), idx) < cross_level and 
                safe_get_prev_value(self.cci(period), idx) >= cross_level
            ),
            
            # ATR Conditions
            'atr_high_volatility': lambda df, idx, period=14, percentile_period=50, percentile_threshold=0.8: (
                idx >= percentile_period and
                safe_get_value(self.atr_percent(period), idx) > 
                np.nanpercentile(self.atr_percent(period)[max(0, idx-percentile_period):idx+1], percentile_threshold*100)
            ),
            'atr_low_volatility': lambda df, idx, period=14, percentile_period=50, percentile_threshold=0.2: (
                idx >= percentile_period and
                safe_get_value(self.atr_percent(period), idx) < 
                np.nanpercentile(self.atr_percent(period)[max(0, idx-percentile_period):idx+1], percentile_threshold*100)
            ),
            'atr_above_threshold': lambda df, idx, period=14, threshold=2.0: (
                safe_get_value(self.atr_percent(period), idx) > threshold
            ),
            'atr_below_threshold': lambda df, idx, period=14, threshold=1.0: (
                safe_get_value(self.atr_percent(period), idx) < threshold
            ),
            
            # SAR Conditions
            'sar_bullish': lambda df, idx, acceleration=0.02, maximum=0.2: (
                safe_get_value(self.close, idx) > safe_get_value(self.parabolic_sar(acceleration, maximum), idx)
            ),
            'sar_bearish': lambda df, idx, acceleration=0.02, maximum=0.2: (
                safe_get_value(self.close, idx) < safe_get_value(self.parabolic_sar(acceleration, maximum), idx)
            ),
            'sar_bullish_cross': lambda df, idx, acceleration=0.02, maximum=0.2: (
                safe_get_value(self.close, idx) > safe_get_value(self.parabolic_sar(acceleration, maximum), idx) and
                safe_get_prev_value(self.close, idx) <= safe_get_prev_value(self.parabolic_sar(acceleration, maximum), idx)
            ),
            'sar_bearish_cross': lambda df, idx, acceleration=0.02, maximum=0.2: (
                safe_get_value(self.close, idx) < safe_get_value(self.parabolic_sar(acceleration, maximum), idx) and
                safe_get_prev_value(self.close, idx) >= safe_get_prev_value(self.parabolic_sar(acceleration, maximum), idx)
            ),
            
            # Moving Average Conditions
            'price_above_sma': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) > safe_get_value(self.sma(period), idx)
            ),
            'price_below_sma': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) < safe_get_value(self.sma(period), idx)
            ),
            'price_above_ema': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) > safe_get_value(self.ema(period), idx)
            ),
            'price_below_ema': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) < safe_get_value(self.ema(period), idx)
            ),
            'sma_bullish_cross': lambda df, idx, fast_period=10, slow_period=20: (
                safe_get_value(self.sma(fast_period), idx) > safe_get_value(self.sma(slow_period), idx) and
                safe_get_prev_value(self.sma(fast_period), idx) <= safe_get_prev_value(self.sma(slow_period), idx)
            ),
            'sma_bearish_cross': lambda df, idx, fast_period=10, slow_period=20: (
                safe_get_value(self.sma(fast_period), idx) < safe_get_value(self.sma(slow_period), idx) and
                safe_get_prev_value(self.sma(fast_period), idx) >= safe_get_prev_value(self.sma(slow_period), idx)
            ),
            'ema_bullish_cross': lambda df, idx, fast_period=12, slow_period=26: (
                safe_get_value(self.ema(fast_period), idx) > safe_get_value(self.ema(slow_period), idx) and
                safe_get_prev_value(self.ema(fast_period), idx) <= safe_get_prev_value(self.ema(slow_period), idx)
            ),
            'ema_bearish_cross': lambda df, idx, fast_period=12, slow_period=26: (
                safe_get_value(self.ema(fast_period), idx) < safe_get_value(self.ema(slow_period), idx) and
                safe_get_prev_value(self.ema(fast_period), idx) >= safe_get_prev_value(self.ema(slow_period), idx)
            ),
            'ema12_above_ema26': lambda df, idx, fast_period=12, slow_period=26: (
                safe_get_value(self.ema(fast_period), idx) > safe_get_value(self.ema(slow_period), idx)
            ),
            'ema12_below_ema26': lambda df, idx, fast_period=12, slow_period=26: (
                safe_get_value(self.ema(fast_period), idx) < safe_get_value(self.ema(slow_period), idx)
            ),
            'sma10_above_sma20': lambda df, idx, fast_period=10, slow_period=20: (
                safe_get_value(self.sma(fast_period), idx) > safe_get_value(self.sma(slow_period), idx)
            ),
            'sma10_below_sma20': lambda df, idx, fast_period=10, slow_period=20: (
                safe_get_value(self.sma(fast_period), idx) < safe_get_value(self.sma(slow_period), idx)
            ),
            
            # Volume Conditions
            'volume_spike': lambda df, idx, period=20, threshold=2.0: (
                safe_get_value(self.volume_ratio(period), idx) > threshold
            ),
            'volume_high': lambda df, idx, period=20, threshold=1.5: (
                safe_get_value(self.volume_ratio(period), idx) > threshold
            ),
            'volume_low': lambda df, idx, period=20, threshold=0.5: (
                safe_get_value(self.volume_ratio(period), idx) < threshold
            ),
            'volume_above_sma': lambda df, idx, period=20, threshold=1.0: (
                safe_get_value(self.volume_ratio(period), idx) > threshold
            ),
            'volume_below_sma': lambda df, idx, period=20, threshold=1.0: (
                safe_get_value(self.volume_ratio(period), idx) < threshold
            ),
            
            # VWAP Conditions
            'price_above_vwap': lambda df, idx, threshold=0.01: (
                safe_get_value(self.vwap_deviation(), idx) > threshold
            ),
            'price_below_vwap': lambda df, idx, threshold=-0.01: (
                safe_get_value(self.vwap_deviation(), idx) < threshold
            ),
            'price_near_vwap': lambda df, idx, threshold=0.005: (
                abs(safe_get_value(self.vwap_deviation(), idx)) < threshold
            ),
            'vwap_bullish_cross': lambda df, idx: (
                safe_get_value(self.close, idx) > safe_get_value(self.vwap(), idx) and
                safe_get_prev_value(self.close, idx) <= safe_get_prev_value(self.vwap(), idx)
            ),
            'vwap_bearish_cross': lambda df, idx: (
                safe_get_value(self.close, idx) < safe_get_value(self.vwap(), idx) and
                safe_get_prev_value(self.close, idx) >= safe_get_prev_value(self.vwap(), idx)
            ),
            
            # Momentum Conditions
            'momentum_positive': lambda df, idx, period=10, threshold=0: (
                safe_get_value(self.momentum(period), idx) > threshold
            ),
            'momentum_negative': lambda df, idx, period=10, threshold=0: (
                safe_get_value(self.momentum(period), idx) < threshold
            ),
            'momentum_increasing': lambda df, idx, period=10: (
                safe_get_value(self.momentum(period), idx) > safe_get_prev_value(self.momentum(period), idx)
            ),
            'momentum_decreasing': lambda df, idx, period=10: (
                safe_get_value(self.momentum(period), idx) < safe_get_prev_value(self.momentum(period), idx)
            ),
            'roc_positive': lambda df, idx, period=10, threshold=0: (
                safe_get_value(self.roc(period), idx) > threshold
            ),
            'roc_negative': lambda df, idx, period=10, threshold=0: (
                safe_get_value(self.roc(period), idx) < threshold
            ),
            'roc_above_threshold': lambda df, idx, period=10, threshold=1.0: (
                safe_get_value(self.roc(period), idx) > threshold
            ),
            'roc_below_threshold': lambda df, idx, period=10, threshold=-1.0: (
                safe_get_value(self.roc(period), idx) < threshold
            ),
            
            # ADX Conditions
            'adx_trending': lambda df, idx, period=14, threshold=25: (
                safe_get_value(self.adx(period), idx) > threshold
            ),
            'adx_strong_trend': lambda df, idx, period=14, threshold=40: (
                safe_get_value(self.adx(period), idx) > threshold
            ),
            'adx_weak_trend': lambda df, idx, period=14, threshold=20: (
                safe_get_value(self.adx(period), idx) < threshold
            ),
            'adx_increasing': lambda df, idx, period=14: (
                safe_get_value(self.adx(period), idx) > safe_get_prev_value(self.adx(period), idx)
            ),
            'adx_decreasing': lambda df, idx, period=14: (
                safe_get_value(self.adx(period), idx) < safe_get_prev_value(self.adx(period), idx)
            ),
            
            # Aroon Conditions
            'aroon_bullish': lambda df, idx, period=14: (
                safe_get_value(self.aroon(period)[0], idx) > safe_get_value(self.aroon(period)[1], idx)
            ),
            'aroon_bearish': lambda df, idx, period=14: (
                safe_get_value(self.aroon(period)[0], idx) < safe_get_value(self.aroon(period)[1], idx)
            ),
            'aroon_up_strong': lambda df, idx, period=14, threshold=70: (
                safe_get_value(self.aroon(period)[0], idx) > threshold
            ),
            'aroon_down_strong': lambda df, idx, period=14, threshold=70: (
                safe_get_value(self.aroon(period)[1], idx) > threshold
            ),
            'aroon_consolidation': lambda df, idx, period=14, threshold=50: (
                safe_get_value(self.aroon(period)[0], idx) < threshold and
                safe_get_value(self.aroon(period)[1], idx) < threshold
            ),
            
            # OBV Conditions
            'obv_increasing': lambda df, idx: (
                safe_get_value(self.obv(), idx) > safe_get_prev_value(self.obv(), idx)
            ),
            'obv_decreasing': lambda df, idx: (
                safe_get_value(self.obv(), idx) < safe_get_prev_value(self.obv(), idx)
            ),
            'obv_divergence_bullish': lambda df, idx, lookback=5: (
                idx >= lookback and
                safe_get_value(self.close, idx) < safe_get_value(self.close, idx-lookback) and
                safe_get_value(self.obv(), idx) > safe_get_value(self.obv(), idx-lookback)
            ),
            'obv_divergence_bearish': lambda df, idx, lookback=5: (
                idx >= lookback and
                safe_get_value(self.close, idx) > safe_get_value(self.close, idx-lookback) and
                safe_get_value(self.obv(), idx) < safe_get_value(self.obv(), idx-lookback)
            ),
            
            # Supertrend Conditions
            'supertrend_bullish': lambda df, idx, period=10, multiplier=3.0: (
                safe_get_value(self.supertrend(period, multiplier)[1], idx) == 1
            ),
            'supertrend_bearish': lambda df, idx, period=10, multiplier=3.0: (
                safe_get_value(self.supertrend(period, multiplier)[1], idx) == -1
            ),
            'supertrend_bullish_cross': lambda df, idx, period=10, multiplier=3.0: (
                safe_get_value(self.supertrend(period, multiplier)[1], idx) == 1 and
                safe_get_prev_value(self.supertrend(period, multiplier)[1], idx) == -1
            ),
            'supertrend_bearish_cross': lambda df, idx, period=10, multiplier=3.0: (
                safe_get_value(self.supertrend(period, multiplier)[1], idx) == -1 and
                safe_get_prev_value(self.supertrend(period, multiplier)[1], idx) == 1
            ),
            
            # Keltner Channel Conditions
            'keltner_upper_break': lambda df, idx, period=20, multiplier=2.0: (
                safe_get_value(self.close, idx) > safe_get_value(self.keltner_channels(period, multiplier)[1], idx)
            ),
            'keltner_lower_break': lambda df, idx, period=20, multiplier=2.0: (
                safe_get_value(self.close, idx) < safe_get_value(self.keltner_channels(period, multiplier)[2], idx)
            ),
            'keltner_squeeze': lambda df, idx, period=20, multiplier=2.0: (
                safe_get_value(self.keltner_channels(period, multiplier)[1], idx) -
                safe_get_value(self.keltner_channels(period, multiplier)[2], idx) <
                safe_get_value(self.atr(period), idx) * 1.5  # Narrow channel
            ),
            
            # TTM Squeeze Conditions
            'ttm_squeeze_on': lambda df, idx, bb_period=20, bb_std=2.0, kc_period=20, kc_mult=1.5: (
                safe_get_value(self.ttm_squeeze(bb_period, bb_std, kc_period, kc_mult), idx) == 1
            ),
            'ttm_squeeze_off': lambda df, idx, bb_period=20, bb_std=2.0, kc_period=20, kc_mult=1.5: (
                safe_get_value(self.ttm_squeeze(bb_period, bb_std, kc_period, kc_mult), idx) == 0 and
                safe_get_prev_value(self.ttm_squeeze(bb_period, bb_std, kc_period, kc_mult), idx) == 1
            ),
            
            # Fisher Transform Conditions
            'fisher_bullish_cross': lambda df, idx, period=10: (
                safe_get_value(self.fisher_transform(period)[0], idx) > 
                safe_get_value(self.fisher_transform(period)[1], idx) and
                safe_get_prev_value(self.fisher_transform(period)[0], idx) <=
                safe_get_prev_value(self.fisher_transform(period)[1], idx)
            ),
            'fisher_bearish_cross': lambda df, idx, period=10: (
                safe_get_value(self.fisher_transform(period)[0], idx) < 
                safe_get_value(self.fisher_transform(period)[1], idx) and
                safe_get_prev_value(self.fisher_transform(period)[0], idx) >=
                safe_get_prev_value(self.fisher_transform(period)[1], idx)
            ),
            
            # Chaikin Money Flow Conditions
            'cmf_positive': lambda df, idx, period=20, threshold=0: (
                safe_get_value(self.chaikin_money_flow(period), idx) > threshold
            ),
            'cmf_negative': lambda df, idx, period=20, threshold=0: (
                safe_get_value(self.chaikin_money_flow(period), idx) < threshold
            ),
            'cmf_bullish_divergence': lambda df, idx, period=20, lookback=5: (
                idx >= lookback and
                safe_get_value(self.close, idx) < safe_get_value(self.close, idx-lookback) and
                safe_get_value(self.chaikin_money_flow(period), idx) > 
                safe_get_value(self.chaikin_money_flow(period), idx-lookback)
            ),
            
            # Donchian Channel Conditions
            'donchian_upper_break': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) >= safe_get_value(self.donchian_channels(period)[1], idx)
            ),
            'donchian_lower_break': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) <= safe_get_value(self.donchian_channels(period)[2], idx)
            ),
            'donchian_middle_cross_up': lambda df, idx, period=20: (
                safe_get_value(self.close, idx) > safe_get_value(self.donchian_channels(period)[0], idx) and
                safe_get_value(self.close, idx-1) <= safe_get_value(self.donchian_channels(period)[0], idx-1)
            ),
            
            # TRIX Conditions
            'trix_positive': lambda df, idx, period=14: (
                safe_get_value(self.trix(period), idx) > 0
            ),
            'trix_negative': lambda df, idx, period=14: (
                safe_get_value(self.trix(period), idx) < 0
            ),
            'trix_bullish_cross': lambda df, idx, period=14: (
                safe_get_value(self.trix(period), idx) > 0 and
                safe_get_prev_value(self.trix(period), idx) <= 0
            ),
            'trix_bearish_cross': lambda df, idx, period=14: (
                safe_get_value(self.trix(period), idx) < 0 and
                safe_get_prev_value(self.trix(period), idx) >= 0
            ),
            
            # True Strength Index Conditions
            'tsi_positive': lambda df, idx, fast_period=13, slow_period=25: (
                safe_get_value(self.true_strength_index(fast_period, slow_period), idx) > 0
            ),
            'tsi_negative': lambda df, idx, fast_period=13, slow_period=25: (
                safe_get_value(self.true_strength_index(fast_period, slow_period), idx) < 0
            ),
            'tsi_overbought': lambda df, idx, fast_period=13, slow_period=25, threshold=25: (
                safe_get_value(self.true_strength_index(fast_period, slow_period), idx) > threshold
            ),
            'tsi_oversold': lambda df, idx, fast_period=13, slow_period=25, threshold=-25: (
                safe_get_value(self.true_strength_index(fast_period, slow_period), idx) < threshold
            ),
            
            # ============================================================================
            # CRASH PROTECTION & RECOVERY CONDITIONS
            # ============================================================================
            
            # Ulcer Index Conditions
            'ulcer_low_risk': lambda df, idx, period=14, threshold=5: (
                safe_get_value(self.ulcer_index(period), idx) < threshold
            ),
            'ulcer_high_risk': lambda df, idx, period=14, threshold=10: (
                safe_get_value(self.ulcer_index(period), idx) > threshold
            ),
            'ulcer_extreme_risk': lambda df, idx, period=14, threshold=15: (
                safe_get_value(self.ulcer_index(period), idx) > threshold
            ),
            'ulcer_decreasing': lambda df, idx, period=14: (
                safe_get_value(self.ulcer_index(period), idx) < 
                safe_get_prev_value(self.ulcer_index(period), idx)
            ),
            
            # Maximum Drawdown Conditions
            'drawdown_shallow': lambda df, idx, period=20, threshold=-5: (
                safe_get_value(self.maximum_drawdown(period)[0], idx) > threshold
            ),
            'drawdown_moderate': lambda df, idx, period=20, threshold=-10: (
                safe_get_value(self.maximum_drawdown(period)[0], idx) < threshold
            ),
            'drawdown_deep': lambda df, idx, period=20, threshold=-20: (
                safe_get_value(self.maximum_drawdown(period)[0], idx) < threshold
            ),
            'drawdown_recovering': lambda df, idx, period=20: (
                safe_get_value(self.maximum_drawdown(period)[0], idx) > 
                safe_get_prev_value(self.maximum_drawdown(period)[0], idx)
            ),
            
            # Coppock Curve Conditions
            'coppock_buy_signal': lambda df, idx, roc1_period=14, roc2_period=11, wma_period=10: (
                safe_get_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) > 0 and
                safe_get_prev_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) <= 0
            ),
            'coppock_turning_up': lambda df, idx, roc1_period=14, roc2_period=11, wma_period=10: (
                safe_get_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) > 
                safe_get_prev_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) and
                safe_get_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) < 0
            ),
            'coppock_positive': lambda df, idx, roc1_period=14, roc2_period=11, wma_period=10: (
                safe_get_value(self.coppock_curve(roc1_period, roc2_period, wma_period), idx) > 0
            ),
            
            # Volatility Stop Conditions
            'volatility_stop_long': lambda df, idx, period=20, multiplier=2.5: (
                safe_get_value(self.df['closePrice'].values, idx) > 
                safe_get_value(self.volatility_stop(period, multiplier)[0], idx)
            ),
            'volatility_stop_short': lambda df, idx, period=20, multiplier=2.5: (
                safe_get_value(self.df['closePrice'].values, idx) < 
                safe_get_value(self.volatility_stop(period, multiplier)[1], idx)
            ),
            
            # Market Regime Conditions
            'regime_bullish': lambda df, idx, adx_period=14, adx_threshold=25: (
                safe_get_value(self.market_regime(adx_period, adx_threshold), idx) == 2
            ),
            'regime_bearish': lambda df, idx, adx_period=14, adx_threshold=25: (
                safe_get_value(self.market_regime(adx_period, adx_threshold), idx) == -2
            ),
            'regime_ranging': lambda df, idx, adx_period=14, adx_threshold=25: (
                safe_get_value(self.market_regime(adx_period, adx_threshold), idx) == 0
            ),
            'regime_crash': lambda df, idx, adx_period=14, adx_threshold=25: (
                safe_get_value(self.market_regime(adx_period, adx_threshold), idx) == -1
            ),
            
            # Accumulation/Distribution Conditions
            'ad_accumulation': lambda df, idx, ma_period=20: (
                safe_get_value(self.accumulation_distribution(), idx) > 
                pd.Series(self.accumulation_distribution()).rolling(window=ma_period, min_periods=1).mean().iloc[idx]
            ),
            'ad_distribution': lambda df, idx, ma_period=20: (
                safe_get_value(self.accumulation_distribution(), idx) < 
                pd.Series(self.accumulation_distribution()).rolling(window=ma_period, min_periods=1).mean().iloc[idx]
            ),
            'ad_divergence_bullish': lambda df, idx, lookback=10: (
                idx >= lookback and
                self.df['closePrice'].iloc[idx] < self.df['closePrice'].iloc[idx-lookback] and
                safe_get_value(self.accumulation_distribution(), idx) > 
                safe_get_value(self.accumulation_distribution(), idx-lookback)
            ),
            'ad_divergence_bearish': lambda df, idx, lookback=10: (
                idx >= lookback and
                self.df['closePrice'].iloc[idx] > self.df['closePrice'].iloc[idx-lookback] and
                safe_get_value(self.accumulation_distribution(), idx) < 
                safe_get_value(self.accumulation_distribution(), idx-lookback)
            ),
            
            # Inverse Fisher RSI Conditions
            'iftrsi_buy_signal': lambda df, idx, period=5, threshold=-0.5: (
                safe_get_value(self.inverse_fisher_rsi(period), idx) > threshold and
                safe_get_prev_value(self.inverse_fisher_rsi(period), idx) <= threshold
            ),
            'iftrsi_sell_signal': lambda df, idx, period=5, threshold=0.5: (
                safe_get_value(self.inverse_fisher_rsi(period), idx) < threshold and
                safe_get_prev_value(self.inverse_fisher_rsi(period), idx) >= threshold
            ),
            'iftrsi_extreme_oversold': lambda df, idx, period=5, threshold=-0.9: (
                safe_get_value(self.inverse_fisher_rsi(period), idx) < threshold
            ),
            'iftrsi_extreme_overbought': lambda df, idx, period=5, threshold=0.9: (
                safe_get_value(self.inverse_fisher_rsi(period), idx) > threshold
            ),
            
            # Heikin-Ashi Conditions
            'heikin_ashi_bullish': lambda df, idx: (
                safe_get_value(self.heikin_ashi()[3], idx) > safe_get_value(self.heikin_ashi()[0], idx)
            ),
            'heikin_ashi_bearish': lambda df, idx: (
                safe_get_value(self.heikin_ashi()[3], idx) < safe_get_value(self.heikin_ashi()[0], idx)
            ),
            'heikin_ashi_reversal_bull': lambda df, idx: (
                safe_get_value(self.heikin_ashi()[3], idx) > safe_get_value(self.heikin_ashi()[0], idx) and
                safe_get_prev_value(self.heikin_ashi()[3], idx) <= safe_get_prev_value(self.heikin_ashi()[0], idx)
            ),
            'heikin_ashi_reversal_bear': lambda df, idx: (
                safe_get_value(self.heikin_ashi()[3], idx) < safe_get_value(self.heikin_ashi()[0], idx) and
                safe_get_prev_value(self.heikin_ashi()[3], idx) >= safe_get_prev_value(self.heikin_ashi()[0], idx)
            ),
            
            # Pivot Point Conditions
            'pivot_above_r3': lambda df, idx, pivot_type='camarilla': (
                'R3' in self.pivot_points(pivot_type) and
                safe_get_value(self.df['closePrice'].values, idx) > 
                safe_get_value(self.pivot_points(pivot_type)['R3'], idx)
            ),
            'pivot_below_s3': lambda df, idx, pivot_type='camarilla': (
                'S3' in self.pivot_points(pivot_type) and
                safe_get_value(self.df['closePrice'].values, idx) < 
                safe_get_value(self.pivot_points(pivot_type)['S3'], idx)
            ),
            'pivot_bounce_s3': lambda df, idx, pivot_type='camarilla': (
                'S3' in self.pivot_points(pivot_type) and
                safe_get_value(self.df['lowPrice'].values, idx) <= safe_get_value(self.pivot_points(pivot_type)['S3'], idx) and
                safe_get_value(self.df['closePrice'].values, idx) > safe_get_value(self.pivot_points(pivot_type)['S3'], idx)
            ),
            'pivot_reject_r3': lambda df, idx, pivot_type='camarilla': (
                'R3' in self.pivot_points(pivot_type) and
                safe_get_value(self.df['highPrice'].values, idx) >= safe_get_value(self.pivot_points(pivot_type)['R3'], idx) and
                safe_get_value(self.df['closePrice'].values, idx) < safe_get_value(self.pivot_points(pivot_type)['R3'], idx)
            ),
            
            # Volume-Weighted MACD Conditions
            'vwmacd_bullish_cross': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[0], idx) > 
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[1], idx) and
                safe_get_prev_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[0], idx) <= 
                safe_get_prev_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[1], idx)
            ),
            'vwmacd_bearish_cross': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[0], idx) < 
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[1], idx) and
                safe_get_prev_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[0], idx) >= 
                safe_get_prev_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[1], idx)
            ),
            'vwmacd_positive': lambda df, idx, fast_period=12, slow_period=26, signal_period=9, threshold=0: (
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[0], idx) > threshold
            ),
            'vwmacd_histogram_positive': lambda df, idx, fast_period=12, slow_period=26, signal_period=9: (
                safe_get_value(self.volume_weighted_macd(fast_period, slow_period, signal_period)[2], idx) > 0
            ),
            
            # ============================================================================
            # COMBINATION CONDITIONS - CRASH PROTECTION & BOTTOM DETECTION
            # ============================================================================
            
            # CRASH_SHIELD - Prevents trading during market crashes
            # Combines: Ulcer Index + Drawdown + Market Regime
            'crash_shield_active': lambda df, idx, ulcer_threshold=10, dd_threshold=-15, lookback=5: (
                # High stress (Ulcer > threshold)
                safe_get_value(self.ulcer_index(14), idx) > ulcer_threshold and
                # Deep drawdown
                safe_get_value(self.maximum_drawdown(20)[0], idx) < dd_threshold and
                # Not recovering yet (drawdown still worsening or flat)
                (idx < lookback or 
                 safe_get_value(self.maximum_drawdown(20)[0], idx) <= 
                 safe_get_value(self.maximum_drawdown(20)[0], idx-lookback))
            ),
            
            # BOTTOM_HUNTER - Detects major market bottoms
            # Combines: RSI extreme oversold + Volume spike + Coppock turning
            'bottom_hunter_signal': lambda df, idx, rsi_threshold=30, volume_spike=1.5: (
                # Extreme oversold RSI
                safe_get_value(self.rsi(14), idx) < rsi_threshold and
                # Volume spike (comparing to 20-period average)
                (idx >= 20 and 
                 safe_get_value(self.df['lastTradedVolume'].values, idx) > 
                 pd.Series(self.df['lastTradedVolume'].values).rolling(20).mean().iloc[idx] * volume_spike) and
                # Coppock starting to turn up (or already positive after being negative)
                (safe_get_value(self.coppock_curve(), idx) > safe_get_prev_value(self.coppock_curve(), idx) or
                 (safe_get_value(self.coppock_curve(), idx) > 0 and 
                  safe_get_prev_value(self.coppock_curve(), idx) < 0))
            ),
            
            # RECOVERY_RIDER - Catches the bounce after crash
            # Combines: IFT RSI buy + Heikin-Ashi reversal + Drawdown recovering
            'recovery_rider_signal': lambda df, idx, dd_improvement=5: (
                # IFT RSI buy signal
                (safe_get_value(self.inverse_fisher_rsi(5), idx) > -0.5 and
                 safe_get_prev_value(self.inverse_fisher_rsi(5), idx) <= -0.5) and
                # Heikin-Ashi bullish reversal
                (safe_get_value(self.heikin_ashi()[3], idx) > safe_get_value(self.heikin_ashi()[0], idx) and
                 safe_get_prev_value(self.heikin_ashi()[3], idx) <= safe_get_prev_value(self.heikin_ashi()[0], idx)) and
                # Drawdown improving (less negative than 5 bars ago)
                (idx >= 5 and
                 safe_get_value(self.maximum_drawdown(20)[0], idx) > 
                 safe_get_value(self.maximum_drawdown(20)[0], idx-5) + dd_improvement)
            ),
            
            # RANGE_TRADER - Trades ranging markets safely
            # Combines: Low ADX (ranging) + BB oversold + Pivot bounce
            'range_trader_buy': lambda df, idx, adx_threshold=25: (
                # Market is ranging (low ADX)
                safe_get_value(self.adx(14), idx) < adx_threshold and
                # Price at lower Bollinger Band
                safe_get_value(self.bb_position(), idx) < 0.2 and
                # Bouncing from pivot support (S2 or S3)
                ('S2' in self.pivot_points('camarilla') and
                 safe_get_value(self.df['lowPrice'].values, idx) <= 
                 safe_get_value(self.pivot_points('camarilla')['S2'], idx) and
                 safe_get_value(self.df['closePrice'].values, idx) > 
                 safe_get_value(self.pivot_points('camarilla')['S2'], idx))
            ),
            
            # MOMENTUM_SURGE - Catches strong momentum after consolidation
            # Combines: TTM Squeeze off + VWMACD cross + Volume confirmation
            'momentum_surge_signal': lambda df, idx, volume_ratio=1.3: (
                # TTM Squeeze firing (was on, now off)
                (idx > 0 and
                 safe_get_value(self.ttm_squeeze()[2], idx) == False and
                 safe_get_prev_value(self.ttm_squeeze()[2], idx) == True) and
                # VWMACD bullish cross with volume
                (safe_get_value(self.volume_weighted_macd()[0], idx) > 
                 safe_get_value(self.volume_weighted_macd()[1], idx) and
                 safe_get_prev_value(self.volume_weighted_macd()[0], idx) <= 
                 safe_get_prev_value(self.volume_weighted_macd()[1], idx)) and
                # Volume confirmation
                (safe_get_value(self.df['lastTradedVolume'].values, idx) > 
                 pd.Series(self.df['lastTradedVolume'].values).rolling(10).mean().iloc[idx] * volume_ratio)
            ),
            
            # SMART_ENTRY - Comprehensive entry combining crash protection and opportunity
            # This is the master combination that checks everything
            'smart_entry_signal': lambda df, idx: (
                # NOT in crash mode (crash shield is off)
                not conditions['crash_shield_active'](df, idx) and
                # AND one of these opportunities exists:
                (conditions['bottom_hunter_signal'](df, idx) or  # Major bottom
                 conditions['recovery_rider_signal'](df, idx) or  # Recovery bounce
                 conditions['range_trader_buy'](df, idx) or  # Range trade
                 conditions['momentum_surge_signal'](df, idx))  # Momentum breakout
            ),
        }
        
        return conditions
    
    def get_available_indicators(self) -> List[str]:
        """
        Get list of all available indicators
        
        Returns:
            List of indicator names
        """
        return [
            'rsi', 'connors_rsi', 'stochastic_rsi', 'macd', 'stochastic',
            'bollinger_bands', 'bb_position', 'bb_width', 'williams_r', 'cci',
            'atr', 'atr_percent', 'parabolic_sar', 'adx', 'aroon',
            'sma', 'ema', 'obv', 'volume_sma', 'volume_ratio', 'vwap', 'vwap_deviation',
            'momentum', 'roc'
        ]
    
    def get_available_conditions(self) -> List[str]:
        """
        Get list of all available condition names
        
        Returns:
            List of condition names
        """
        return list(self.get_conditions().keys())
    
    def clear_cache(self):
        """Clear the indicator cache"""
        self._cache.clear()

# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def create_indicator_library(df: pd.DataFrame) -> IndicatorLibrary:
    """
    Convenience function to create an IndicatorLibrary instance
    
    Args:
        df: DataFrame with OHLCV data
        
    Returns:
        IndicatorLibrary instance
    """
    return IndicatorLibrary(df)

def get_default_parameters() -> Dict[str, Dict[str, Any]]:
    """
    Get default parameters for all indicators
    
    Returns:
        Dictionary mapping indicator names to their default parameters
    """
    return {
        'rsi': {'period': 14},
        'connors_rsi': {'rsi_period': 3, 'streak_period': 2, 'rank_period': 100},
        'stochastic_rsi': {'period': 14, 'fastk_period': 5, 'fastd_period': 3},
        'macd': {'fast_period': 12, 'slow_period': 26, 'signal_period': 9},
        'stochastic': {'fastk_period': 5, 'slowk_period': 3, 'slowd_period': 3},
        'bollinger_bands': {'period': 20, 'std_dev': 2.0},
        'williams_r': {'period': 14},
        'cci': {'period': 14},
        'atr': {'period': 14},
        'parabolic_sar': {'acceleration': 0.02, 'maximum': 0.2},
        'adx': {'period': 14},
        'aroon': {'period': 14},
        'sma': {'period': 20},
        'ema': {'period': 20},
        'volume_sma': {'period': 20},
        'momentum': {'period': 10},
        'roc': {'period': 10}
    }

# Example usage and testing
if __name__ == "__main__":
    # Example usage
    print("Technical Indicators Library")
    print("=" * 50)
    
    # Create sample data
    import numpy as np
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    sample_data = pd.DataFrame({
        'openPrice': 100 + np.cumsum(np.random.randn(100) * 0.5),
        'highPrice': 100 + np.cumsum(np.random.randn(100) * 0.5) + np.random.rand(100) * 2,
        'lowPrice': 100 + np.cumsum(np.random.randn(100) * 0.5) - np.random.rand(100) * 2,
        'closePrice': 100 + np.cumsum(np.random.randn(100) * 0.5),
        'lastTradedVolume': np.random.randint(1000, 10000, 100)
    })
    
    # Initialize library
    lib = IndicatorLibrary(sample_data)
    
    # Test indicators
    print(f"Available indicators: {len(lib.get_available_indicators())}")
    print(f"Available conditions: {len(lib.get_available_conditions())}")
    
    # Calculate some indicators
    rsi_14 = lib.rsi(period=14)
    rsi_7 = lib.rsi(period=7)
    macd_line, macd_signal, macd_hist = lib.macd()
    bb_upper, bb_middle, bb_lower = lib.bollinger_bands()
    
    print(f"\\nRSI-14 last value: {rsi_14[-1]:.2f}")
    print(f"RSI-7 last value: {rsi_7[-1]:.2f}")
    print(f"MACD last value: {macd_line[-1]:.4f}")
    print(f"BB position last value: {lib.bb_position()[-1]:.4f}")
    
    # Test conditions
    conditions = lib.get_conditions()
    idx = len(sample_data) - 1
    
    print(f"\\nCondition tests at index {idx}:")
    print(f"RSI oversold: {conditions['rsi_oversold'](sample_data, idx)}")
    print(f"MACD positive: {conditions['macd_positive'](sample_data, idx)}")
    print(f"BB oversold: {conditions['bb_oversold'](sample_data, idx)}")
    
    print("\\n✅ Library test completed successfully!")
