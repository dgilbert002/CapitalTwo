# 🧠 BRAINS-GOSPEL TRADING BOT IMPLEMENTATION ROADMAP

## ⚠️ SACRED PRINCIPLES - THE BRAINS FOLDER IS GOSPEL
The `Brains/ai_system.py` and `Brains/trader.py` files are **VERBATIM**, **UNCHANGEABLE**, and **GODLY**. Every calculation, every indicator, every decision threshold MUST be exactly as written in these files.

---

## 📋 EXECUTIVE SUMMARY

This roadmap implements a trading bot that:
1. **Closes all positions** 30 seconds before market close
2. **Analyzes market conditions** 15 seconds before market close using EXACT Brains logic
3. **Executes trades** based on the Brains AI decision with proper position sizing
4. **Uses Dubai timezone** for all market timing calculations
5. **Respects all dealing rules** from Capital.com API

---

## 🎯 PHASE 1: MARKET TIMING INFRASTRUCTURE

### 1.1 Fix Market Time Manager for Dubai Timezone
**File to modify:** `bot/market_time.py`

```python
import pytz
from datetime import datetime, time, timedelta

class MarketTimeManager:
    def __init__(self, settings):
        self.settings = settings
        self.dubai_tz = pytz.timezone('Asia/Dubai')  # UTC+4, no DST
        
    def get_next_market_event(self, market_info):
        """
        EXACT LOGIC from legacy PopulateMarketTimes (lines 879-934):
        1. Get opening hours in UTC from API
        2. Find next closing time
        3. Convert to Dubai time (+4 hours)
        """
        if not market_info or 'instrument' not in market_info:
            return {'error': 'No market info'}
            
        # Get current time in UTC and Dubai
        now_utc = datetime.now(pytz.UTC)
        now_dubai = now_utc.astimezone(self.dubai_tz)
        
        # Get opening hours (format: {'mon': ['13:30 - 20:00'], ...})
        opening_hours = market_info.get('instrument', {}).get('openingHours', {})
        
        # Days of week as in legacy (line 888)
        days_of_week = ['sunday', 'monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday']
        current_day_index = now_utc.weekday()  # Monday=0, Sunday=6
        if current_day_index == 6:  # Convert Sunday to 0
            current_day_index = 0
        else:
            current_day_index += 1
            
        # Find next session closing time (EXACT from lines 892-918)
        for i in range(7):
            day_index = (current_day_index + i) % 7
            day_name = days_of_week[day_index]
            day_key = day_name[:3]  # 'mon', 'tue', etc.
            
            times = opening_hours.get(day_key, [])
            if times:
                # Parse "13:30 - 20:00" format
                time_range = times[0]
                parts = time_range.split(' - ')
                open_time = datetime.strptime(parts[0], '%H:%M').time()
                close_time = datetime.strptime(parts[1], '%H:%M').time()
                
                # Calculate closing datetime in UTC
                close_date = now_utc.date() + timedelta(days=i)
                closing_utc = datetime.combine(close_date, close_time).replace(tzinfo=pytz.UTC)
                
                # Handle overnight sessions (close < open)
                if close_time < open_time:
                    closing_utc += timedelta(days=1)
                    
                # Check if this closing time is in the future
                if closing_utc > now_utc:
                    # Convert to Dubai time (EXACT from line 922: AddHours(4))
                    closing_dubai = closing_utc.astimezone(self.dubai_tz)
                    
                    # Calculate time until close
                    time_until = (closing_dubai - now_dubai).total_seconds()
                    
                    return {
                        'is_open': time_until > 0,
                        'next_event': 'close',
                        'next_event_time_utc': closing_utc.isoformat(),
                        'next_event_time_dubai': closing_dubai.isoformat(),
                        'time_until_seconds': time_until,
                        'market_status': 'OPEN' if time_until > 0 else 'CLOSED'
                    }
                    
        return {'is_open': False, 'market_status': 'CLOSED'}
```

---

## 🎯 PHASE 2: TIMER-BASED TRADE EXECUTOR

### 2.1 Create the Timer Executor
**New file:** `bot/trade_executor.py`

```python
import asyncio
import logging
import pandas as pd
from datetime import datetime, time
from typing import Optional, Dict, Any

# GOSPEL IMPORTS - These are SACRED
from Brains.ai_system import HybridIntelligentSystem
from Brains.trader import TradingBot as BrainsLogic

logger = logging.getLogger(__name__)

class TimerBasedTradeExecutor:
    """
    EXACT implementation of legacy timing logic:
    - 30 seconds before close: Close all positions
    - 15 seconds before close: Analyze and create new position
    """
    
    def __init__(self, api, db_manager, settings):
        self.api = api
        self.db_manager = db_manager
        self.settings = settings
        
        # GOSPEL: Initialize the sacred AI system
        self.ai_system = HybridIntelligentSystem()
        
        # Timing parameters (from legacy lines 371, 384)
        self.seconds_before_close_to_exit = 30
        self.seconds_before_close_to_trade = 15
        
        # Flags from legacy (lines 410-411)
        self.trade_closed = False
        self.trade_opened = False
        self.last_trade_date = None
        
        # Market info cache
        self.market_info = {}
        self.epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
        
    async def execute_timer_strategy(self):
        """Main timer loop - checks every second when market is open"""
        
        # Get market info
        self.market_info = await self.api.get_market_info(self.epic)
        market_event = self._get_market_event()
        
        if not market_event.get('is_open'):
            # Reset flags for next session
            self.trade_closed = False
            self.trade_opened = False
            return
            
        time_until_close = market_event.get('time_until_seconds', float('inf'))
        current_date = datetime.now().date()
        
        # Only trade once per day
        if current_date == self.last_trade_date:
            return
            
        # EXACT TIMING from legacy (lines 371-398)
        
        # Step 1: Close positions 30 seconds before market close
        if time_until_close <= self.seconds_before_close_to_exit and not self.trade_closed:
            logger.info(f"⏰ {time_until_close:.0f}s until close - CLOSING ALL POSITIONS")
            await self._close_all_positions()
            self.trade_closed = True
            
        # Step 2: Analyze and trade 15 seconds before market close  
        elif time_until_close <= self.seconds_before_close_to_trade and not self.trade_opened:
            logger.info(f"⏰ {time_until_close:.0f}s until close - RUNNING BRAINS ANALYSIS")
            await self._analyze_and_trade()
            self.trade_opened = True
            self.last_trade_date = current_date
            
    async def _close_all_positions(self):
        """Close all open positions (EXACT from legacy CloseExistingTradeAsync)"""
        try:
            positions = await self.api.get_positions()
            for position in positions:
                deal_id = position.get('position', {}).get('dealId')
                if deal_id:
                    logger.info(f"Closing position: {deal_id}")
                    await self.api.close_position(deal_id)
                    
            logger.info("All positions closed successfully")
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
            
    async def _analyze_and_trade(self):
        """
        GOSPEL FUNCTION: Run EXACT Brains analysis and execute trade
        This is the HEART of the system - uses Brains folder logic VERBATIM
        """
        try:
            # STEP 1: Prepare data EXACTLY as Brains expects
            candles = self.db_manager.get_candles(self.epic, limit=200)
            if len(candles) < 50:
                logger.warning("Not enough data for Brains analysis (need 50+)")
                return
                
            # Convert to DataFrame with EXACT column names from Brains
            df = pd.DataFrame(candles, columns=["epic", "timestamp", "open", "high", "low", "close", "volume"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df.set_index("timestamp", inplace=True)
            
            # Calculate indicators using GOSPEL function
            historical_data = self.ai_system.calculate_technical_indicators(df)
            
            # Get current date for day data
            current_date = datetime.now().date()
            day_data = df[df.index.date == current_date].copy() if not df.empty else pd.DataFrame()
            
            # STEP 2: Run GOSPEL AI analysis
            ai_analysis = self.ai_system.analyze_market_conditions(
                day_data, 
                historical_data, 
                datetime.now()
            )
            
            logger.info(f"🧠 BRAINS ANALYSIS: Signal={ai_analysis['trade_signal']}, "
                       f"Confidence={ai_analysis['confidence']:.2%}, "
                       f"Direction={ai_analysis['direction']}")
            
            # STEP 3: Check confidence threshold from settings
            confidence_threshold = self.settings.getfloat("BOT_CONFIG", "ai_confidence_threshold", 30.0) / 100.0
            
            # STEP 4: Execute trade if AI approves
            if (ai_analysis['trade_signal'] in ['buy', 'sell'] and 
                ai_analysis['confidence'] > confidence_threshold):
                
                await self._create_position_with_dealing_rules(ai_analysis)
            else:
                logger.info(f"No trade: Signal={ai_analysis['trade_signal']}, "
                           f"Confidence={ai_analysis['confidence']:.2%} < {confidence_threshold:.2%}")
                
        except Exception as e:
            logger.error(f"Error in Brains analysis: {e}")
            
    async def _create_position_with_dealing_rules(self, ai_analysis):
        """
        Create position with EXACT dealing rules calculation from legacy
        Lines 685-778 in frmCapitalOne.vb
        """
        try:
            # Get current market snapshot
            market_data = self.market_info
            snapshot = market_data.get('snapshot', {})
            dealing_rules = market_data.get('dealingRules', {})
            
            # EXACT from legacy lines 688-690
            bid_price = snapshot.get('bid', 0)
            ask_price = snapshot.get('offer', 0)
            mid_price = (bid_price + ask_price) / 2
            
            logger.info(f"Prices - Bid: {bid_price}, Ask: {ask_price}, Mid: {mid_price}")
            
            # Get dealing rules (EXACT from lines 697-700)
            min_deal_size = dealing_rules.get('minDealSize', {}).get('value', 0.1)
            max_deal_size = dealing_rules.get('maxDealSize', {}).get('value', 1000)
            min_size_increment = dealing_rules.get('minSizeIncrement', {}).get('value', 0.1)
            
            logger.info(f"Dealing Rules - Min: {min_deal_size}, Max: {max_deal_size}, Increment: {min_size_increment}")
            
            # Get account balance
            accounts = await self.api.get_accounts()
            if not accounts:
                logger.error("No accounts available")
                return
                
            account = accounts[0]  # Use first account or configured one
            available_balance = account.get('balance', {}).get('available', 0)
            
            logger.info(f"Available Balance: ${available_balance}")
            
            # Get leverage from settings
            leverage = self.settings.getfloat("BOT_CONFIG", "leverage", 4.0)
            
            # Calculate position size (EXACT from legacy line 740)
            # tradeSize = AccountBalance * (AccountBalancePerc / 100) * leverage / currentPrice
            investment_pct = self.settings.getfloat("BOT_CONFIG", "investment_pct", 99.0)
            current_price = bid_price  # Use bid for calculation as in legacy line 728
            
            trade_size = available_balance * (investment_pct / 100.0) * leverage / current_price
            
            logger.info(f"Calculated trade size (before adjustment): {trade_size}")
            
            # Apply dealing rules (EXACT from lines 746-752)
            if trade_size < min_deal_size:
                trade_size = min_deal_size
            elif trade_size > max_deal_size:
                trade_size = max_deal_size
                
            # Floor to increment (EXACT from line 752)
            import math
            trade_size = math.floor(trade_size / min_size_increment) * min_size_increment
            
            logger.info(f"Final trade size (after dealing rules): {trade_size}")
            
            # Calculate stop loss (EXACT from lines 756-758)
            stop_loss_pct = self.settings.getfloat("BOT_CONFIG", "stop_loss_pct", 2.0)
            if ai_analysis['direction'] == 'long':
                stop_level = bid_price * (1 - stop_loss_pct / 100.0)
                direction = 'BUY'
            else:
                stop_level = bid_price * (1 + stop_loss_pct / 100.0)
                direction = 'SELL'
                
            logger.info(f"Stop Loss Level: {stop_level} ({stop_loss_pct}% from {bid_price})")
            
            # Create the position (EXACT from line 761)
            result = await self.api.create_position(
                epic=self.epic,
                direction=direction,
                size=trade_size,
                stop_level=stop_level
            )
            
            if result:
                logger.info(f"✅ TRADE EXECUTED: {direction} {trade_size} @ {bid_price}, Stop: {stop_level}")
            else:
                logger.error("Failed to create position")
                
        except Exception as e:
            logger.error(f"Error creating position: {e}")
            
    def _get_market_event(self):
        """Get market event from MarketTimeManager"""
        from bot.market_time import MarketTimeManager
        market_timer = MarketTimeManager(self.settings)
        return market_timer.get_next_market_event(self.market_info)
```

---

## 🎯 PHASE 3: INTEGRATE WITH MAIN BOT

### 3.1 Modify Main TradingBot
**File to modify:** `bot/trader.py`

```python
# Add to imports
from bot.trade_executor import TimerBasedTradeExecutor

class TradingBot:
    def __init__(self):
        # ... existing init code ...
        
        # Add timer executor
        self.timer_executor = None
        
    async def run(self):
        """Main trading loop with timer-based execution"""
        self.is_running = True
        logger.info("Trading bot started with TIMER-BASED BRAINS SYSTEM")
        
        # Initialize timer executor
        self.timer_executor = TimerBasedTradeExecutor(
            self.api, 
            self.db_manager, 
            self.settings
        )
        
        while self.is_running:
            await self.update_data()
            
            # Execute timer-based strategy
            await self.timer_executor.execute_timer_strategy()
            
            # Check every second for precise timing
            await asyncio.sleep(1)
```

---

## 🎯 PHASE 4: SETTINGS CONFIGURATION

### 4.1 Update settings.txt
**File:** `settings.txt`

```ini
[BOT_CONFIG]
bot_name = AI Hybrid Trader
epic = TECL
leverage = 4.0
investment_pct = 99.0
stop_loss_pct = 2.0
ai_confidence_threshold = 30.0

# Timing settings (seconds before market close)
seconds_before_close_to_exit = 30
seconds_before_close_to_trade = 15

[CREDENTIALS]
# ... existing credentials ...
```

---

## 🧠 GOSPEL CALCULATIONS FROM BRAINS

### AI Analysis Scoring (EXACT from Brains/ai_system.py)

```python
# THESE ARE THE SACRED CALCULATIONS - DO NOT MODIFY

1. TREND ANALYSIS (Weight: 3)
   - Price > SMA20: +3 bullish / -3 bearish
   - SMA5 > SMA20: +2 bullish / -2 bearish

2. MOMENTUM ANALYSIS (Weight: 2)
   - 30 < RSI < 70: +2 bullish
   - RSI > 70: +2 bearish
   - RSI < 30: +2 bullish (oversold)
   - MACD > Signal: +2 bullish / -2 bearish

3. VOLUME ANALYSIS (Weight: 1)
   - Volume Ratio > 1.2: +1 bullish
   - Volume Ratio < 0.8: +1 bearish

4. DAY OF WEEK BIAS
   - Tuesday: +3 bullish
   - Friday: +2 bullish
   - Wednesday: +1 bullish
   - Thursday: -3 bearish

5. RECENT PERFORMANCE (Weight: 2)
   - 5-bar avg return > 1%: +2 bullish
   - 5-bar avg return < -1%: +2 bearish

FINAL DECISION:
- bullish_ratio = bullish_signals / (bullish_signals + bearish_signals)
- BUY if ratio > 0.65
- SELL if ratio < 0.35
- HOLD otherwise
- Confidence = |ratio - 0.5| * 2
```

### Position Sizing (EXACT from legacy + Brains)

```python
# SACRED FORMULA - DO NOT CHANGE
trade_size = available_balance * (investment_pct / 100) * leverage / current_price

# Apply dealing rules
if trade_size < min_deal_size:
    trade_size = min_deal_size
elif trade_size > max_deal_size:
    trade_size = max_deal_size
    
# Floor to increment
trade_size = floor(trade_size / min_size_increment) * min_size_increment
```

---

## 📊 TESTING CHECKLIST

### Pre-Launch Verification
- [ ] Market timer shows correct Dubai time (UTC+4)
- [ ] Countdown matches Capital.com market close time
- [ ] 30-second close trigger works
- [ ] 15-second analysis trigger works
- [ ] Brains AI analysis returns valid signals
- [ ] Position sizing respects dealing rules
- [ ] Stop loss calculated correctly
- [ ] Only one trade per day enforced

### Live Testing Steps
1. **Start bot 5 minutes before market close**
2. **Monitor countdown timer**
3. **Verify at T-30s: All positions close**
4. **Verify at T-15s: AI analysis runs**
5. **Check trade execution if signal approved**
6. **Verify stop loss level set correctly**

---

## ⚠️ CRITICAL REMINDERS

1. **THE BRAINS FOLDER IS GOSPEL** - Never modify `Brains/ai_system.py` or `Brains/trader.py`
2. **Dubai Time = UTC+4** - All market times must be converted
3. **30 seconds to close, 15 seconds to trade** - These timings are sacred
4. **99% investment, 2% stop loss** - Default from settings
5. **Confidence threshold 30%** - Configurable but default is sacred

---

## 🚀 IMPLEMENTATION ORDER

1. **First:** Update `bot/market_time.py` with Dubai timezone logic
2. **Second:** Create `bot/trade_executor.py` with timer logic
3. **Third:** Integrate timer executor into `bot/trader.py`
4. **Fourth:** Update `settings.txt` with timing parameters
5. **Fifth:** Test countdown timer accuracy
6. **Sixth:** Test with paper trading
7. **Seventh:** Go live with small position

---

## 📝 LOGGING FOR VERIFICATION

Every critical action must be logged:

```python
logger.info(f"⏰ Market closes in {time_until_close}s (Dubai time: {dubai_time})")
logger.info(f"🔴 CLOSING POSITIONS at T-{time_until_close}s")
logger.info(f"🧠 RUNNING BRAINS ANALYSIS at T-{time_until_close}s")
logger.info(f"📊 BRAINS DECISION: {signal} @ {confidence}% confidence")
logger.info(f"✅ TRADE EXECUTED: {direction} {size} @ {price}")
```

---

## END OF ROADMAP

This roadmap is COMPLETE and SACRED. Follow it EXACTLY to implement the timer-based trading bot that honors the BRAINS folder as GOSPEL.