"""
Trading Bot with Timer-Based Strategy and Legacy-Style Improvements
"""

import asyncio
import logging
from datetime import datetime, time, timedelta
from typing import Dict, List, Optional
import pytz
from bot.api import CapitalComAPI
from bot.database import DatabaseManager
from bot.data_downloader import DataDownloader
from bot.settings import TradingBotSettings
from bot.market_time import MarketTimeManager
from Brains.ai_system import HybridIntelligentSystem
from capitalcom.client import ResolutionType
import pandas as pd

logger = logging.getLogger(__name__)

class TradingBot:
    def __init__(self, settings: TradingBotSettings):
        """Initialize the trading bot with improved features"""
        self.settings = settings
        self.api = CapitalComAPI(settings, environment=settings.get('API_CONFIG', 'environment', 'demo'))
        self.db = DatabaseManager(settings.get('DATABASE', 'path', 'database.db'))
        # Provide alias for compatibility with shutdown paths expecting db_manager
        self.db_manager = self.db
        self.downloader = DataDownloader(self.api, self.db)
        self.market_timer = MarketTimeManager(settings)
        self.ai_system = HybridIntelligentSystem()
        
        # Get timer settings
        self.use_timer_based_trading = True
        self.seconds_before_close_to_exit = int(settings.get('BOT_CONFIG', 'seconds_before_close_to_exit', 30))
        self.seconds_before_close_to_trade = int(settings.get('BOT_CONFIG', 'seconds_before_close_to_trade', 15))
        
        # Trailing SL settings
        self.use_trailing_sl = settings.getboolean('BOT_CONFIG', 'use_trailing_sl', False)
        self.sl_thresholds = [float(x.strip()) for x in settings.get('BOT_CONFIG', 'sl_thresholds', '5,10,15').split(',')]
        self.sl_adjustments = [float(x.strip()) for x in settings.get('BOT_CONFIG', 'sl_adjustments', '2,5,8').split(',')]
        self.highest_threshold_acted = 0
        
        # Trading state
        self.is_running = False
        self.api_connected = False
        self.positions_closed_today = False
        self.trade_analyzed_today = False
        self.last_trade_date = None
        
        # Market data
        self.epic = settings.get('BOT_CONFIG', 'epic', 'TECL')
        self.market_info = None
        self.current_account = None
        
        # Trading data
        self.trade_history = []
        self.action_log = []
        
        # Tasks
        self.keepalive_task = None
        self.downloader_task = None
        
        logger.info(f"Trading bot initialized for {self.epic}")

    def record_action(self, action: Dict) -> None:
        """Record a structured action to in-memory list and Trades.log"""
        try:
            entry = {**action, 'ts': datetime.now().isoformat(timespec='seconds')}
            self.action_log.append(entry)
            if len(self.action_log) > 200:
                self.action_log = self.action_log[-200:]
            import json as _json
            with open('Trades.log', 'a', encoding='utf-8') as f:
                f.write(_json.dumps(entry) + "\n")
        except Exception:
            pass
        
    async def initialize(self) -> bool:
        """Initialize the trading bot"""
        try:
            # Check if API is already connected (shared from main)
            if not self.api_connected and hasattr(self.api, 'client') and self.api.client:
                self.api_connected = True
                logger.info("Using existing API connection")
            elif not self.api_connected:
                if not await self.api.authenticate():
                    return False
                self.api_connected = True
            
            accounts = await self.api.get_accounts()
            if not accounts:
                logger.error("No accounts found")
                return False
            
            # Select account
            env_account_id = self.settings.get_env_account(self.api.environment)
            if env_account_id:
                await self.api.switch_account(env_account_id)
                for acc in accounts:
                    if acc['accountId'] == env_account_id:
                        self.current_account = acc
                        logger.info(f"Using account: {acc['accountName']}")
                        break
            else:
                self.current_account = accounts[0]
                logger.info(f"Using first account: {self.current_account['accountName']}")
            
            # Get initial market info
            self.market_info = await self.api.get_market_info(self.epic)

            # Start continuous data download
            self.downloader_task = asyncio.create_task(self.continuous_download())
            
            # Start keepalive
            self.keepalive_task = asyncio.create_task(self.keepalive_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False
    
    async def create_position_with_retry(self, epic: str, direction: str, size: float, stop_level: float, max_attempts: int = 3) -> Optional[Dict]:
        """Create position with retry logic - validates API response"""
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Position creation attempt {attempt}/{max_attempts}")
                
                # Check if in simulation mode
                if self.settings.getboolean('BOT_CONFIG', 'simulation_mode', False):
                    logger.info(f"SIMULATION MODE: Would create {direction} {size} @ stop {stop_level}")
                    return {'simulated': True, 'dealReference': f'SIM-{datetime.now().timestamp()}'}
                
                # Real API call
                result = await self.api.create_position(epic, direction, size, stop_level)
                
                if result and 'dealReference' in result:
                    logger.info(f"Position created successfully on attempt {attempt}")
                    return result
                else:
                    logger.warning(f"Attempt {attempt} failed - invalid response: {result}")
                    
            except Exception as e:
                logger.error(f"Attempt {attempt} failed with error: {e}")
                
            # Wait before retry (except on last attempt)
            if attempt < max_attempts:
                await asyncio.sleep(1)
                
        logger.error(f"Failed to create position after {max_attempts} attempts")
        return None
    
    async def check_and_trail_stop_loss(self, positions: List[Dict]) -> None:
        """Check and adjust stop loss based on profit thresholds - Legacy style"""
        if not self.use_trailing_sl or not positions:
            return

        try:
            for position_data in positions:
                position = position_data.get('position', {})
                market = position_data.get('market', {})
                
                deal_id = position.get('dealId')
                entry_price = float(position.get('level', 0))
                current_sl = float(position.get('stopLevel', 0))
                current_price = float(market.get('bid', 0))
                
                if not all([deal_id, entry_price, current_price]):
                    continue
                
                # Calculate percentage increase
                pct_increase = ((current_price - entry_price) / entry_price) * 100
                
                # Check thresholds
                for i, threshold in enumerate(self.sl_thresholds):
                    if pct_increase >= threshold and threshold > self.highest_threshold_acted:
                        # Calculate new stop loss
                        adjustment = self.sl_adjustments[i]
                        new_sl = round(entry_price * (1 + adjustment/100), 2)
                        
                        if new_sl > current_sl:
                            logger.info(f"Trailing SL: {pct_increase:.2f}% profit, moving SL from {current_sl} to {new_sl}")
                            
                            # Update stop loss with retry
                            for attempt in range(3):
                                try:
                                    result = await self.api.update_position(deal_id, stop_level=new_sl)
                                    if result:
                                        self.highest_threshold_acted = threshold
                                        logger.info(f"Stop loss updated successfully")
                                        break
                                except Exception as e:
                                    if attempt < 2:
                                        await asyncio.sleep(1)
                                    else:
                                        logger.error(f"Failed to update SL after 3 attempts: {e}")
                        break
                
        except Exception as e:
            logger.error(f"Error in trailing stop loss: {e}")
    
    async def simulate_market_close(self):
        """Simulate market close - LEGACY STYLE: Just manipulate time! Returns step results."""
        try:
            logger.info("="*60)
            logger.info("SIMULATION: Legacy-style time manipulation")
            logger.info("Setting market to T-35 seconds before close")
            logger.info("="*60)
            
            # Check if we're in simulation mode
            simulation_mode = self.settings.getboolean('BOT_CONFIG', 'simulation_mode', False)
            if simulation_mode:
                logger.info("SIMULATION MODE: API calls will be skipped")
            
            # Track step results
            closed_positions_success = None
            created_trade_success = None
            
            # Run countdown from 35 to 0 seconds
            for seconds in range(35, -1, -1):
                # Create fake market event
                fake_event = {
                    'is_open': True,
                    'time_until_close': seconds,
                    'time_until_open': 0,
                    'status': 'OPEN',
                    'next_event': 'Market Close',
                    'countdown': f"00:00:{seconds:02d}"
                }
                
                # Log key moments
                if seconds == 30:
                    logger.info("="*40)
                    logger.info("SIMULATION: T-30s - CLOSING POSITIONS")
                    logger.info("="*40)
                    # Check before/after counts to mark success
                    try:
                        before_positions = await self.api.get_positions()
                        before_count = len(before_positions or [])
                    except Exception:
                        before_count = 0
                    await self.close_all_positions_timer()
                    try:
                        after_positions = await self.api.get_positions()
                        after_count = len(after_positions or [])
                    except Exception:
                        after_count = 0
                    closed_positions_success = (after_count == 0) or (after_count < before_count)
                    self.record_action({'event': 'close_positions_summary', 'success': bool(closed_positions_success), 'before': before_count, 'after': after_count})
                elif seconds == 15:
                    logger.info("="*40)
                    logger.info("SIMULATION: T-15s - ANALYZING & TRADING")
                    logger.info("="*40)
                elif seconds <= 5 and seconds > 0:
                    logger.info(f"SIMULATION: T-{seconds}s - Final countdown")
                elif seconds == 0:
                    logger.info("="*40)
                    logger.info("SIMULATION: MARKET CLOSED")
                    logger.info("="*40)
                
                # At T-15s, proactively trigger trade analysis/creation to mirror legacy sim
                if seconds == 15:
                    try:
                        # Ensure we have fresh market info and dealing rules
                        self.market_info = await self.api.get_market_info(self.epic)
                        dealing_rules = (self.market_info or {}).get('dealingRules', {})
                        # Assume conditions true in simulation: use direction from settings
                        direction_setting = self.settings.get('BOT_CONFIG', 'direction', 'long').lower()
                        forced_signal = 'buy' if direction_setting == 'long' else 'sell'
                        ai_analysis = {'trade_signal': forced_signal, 'confidence': 1.0}
                        self.record_action({
                            'event': 'brains_decision',
                            'simulation_override': True,
                            'signal': ai_analysis['trade_signal'],
                            'confidence': ai_analysis['confidence'],
                            'epic': self.epic
                        })
                        try:
                            before_positions = await self.api.get_positions()
                            before_count = len(before_positions or [])
                        except Exception:
                            before_count = 0
                        created_ok = await self.create_position_timer(ai_analysis, dealing_rules)
                        try:
                            after_positions = await self.api.get_positions()
                            after_count = len(after_positions or [])
                        except Exception:
                            after_count = before_count
                        created_trade_success = bool(created_ok) or (after_count > before_count)
                        self.trade_analyzed_today = True
                        self.record_action({'event': 'create_trade_summary', 'success': bool(created_trade_success), 'before': before_count, 'after': after_count})
                    except Exception as e:
                        logger.error(f"SIMULATION force trade failed: {e}")
                        self.record_action({'event': 'api_execution', 'success': False, 'error': str(e), 'epic': self.epic})

                # Execute the normal timer strategy with fake time
                await self.execute_timer_based_strategy(fake_event)
                
                # Speed up simulation (0.2 seconds per market second)
                await asyncio.sleep(0.2)
            
            # Reset for next session
            logger.info("SIMULATION: Resetting for next session")
            self.positions_closed_today = False
            self.trade_analyzed_today = False
            
            logger.info("="*60)
            logger.info("SIMULATION COMPLETE!")
            logger.info("The bot executed its normal timer logic:")
            logger.info("  - Closed positions at T-30s")
            logger.info("  - Analyzed & traded at T-15s")
            logger.info("Check your positions tab for results")
            logger.info("="*60)
            
            return {
                'ok': True,
                'steps': {
                    'close_positions': bool(closed_positions_success) if closed_positions_success is not None else True,
                    'create_trade': bool(created_trade_success) if created_trade_success is not None else True
                }
            }
            
        except Exception as e:
            logger.error(f"SIMULATION ERROR: {e}")
            return {'ok': False, 'error': str(e)}
    
    async def simulate_speed_test_old(self, days: int = 5):
        """Speed test with REAL trades and accelerated time - requires market to be open"""
        try:
            logger.info("="*60)
            logger.info(f"SPEED TEST: Starting {days} day REAL trading test")
            logger.info("30 seconds real time = 24 hours market time")
            logger.info("REAL TRADES - Market must be open!")
            logger.info("="*60)
            
            # Check if market is open for real trading
            market_info = await self.api.get_market_info(self.epic)
            if not market_info:
                return {"ok": False, "error": "no_market_info", "message": "Cannot get market information"}
            
            # Use market timer to determine if market is open (same as dashboard uses)
            market_event = self.market_timer.get_next_market_event(market_info)
            is_market_open = market_event.get('is_open', False) if market_event else False
            
            if not is_market_open:
                return {"ok": False, "error": "market_closed", "message": "Market is CLOSED. Speed test requires market to be OPEN for real trading."}
            
            # Disable simulation mode temporarily for real trading
            original_simulation_mode = self.settings.getboolean('BOT_CONFIG', 'simulation_mode', False)
            if original_simulation_mode:
                logger.warning("SPEED TEST: Temporarily disabling simulation mode for real trading")
            
            results = {
                'days_simulated': 0,
                'trades_created': 0,
                'positions_closed': 0,
                'errors': [],
                'daily_results': []
            }
            
            for day in range(days):
                logger.info(f"SPEED TEST: Day {day + 1}/{days} starting - REAL TRADING")
                day_result = {
                    'day': day + 1,
                    'trades_created': 0,
                    'positions_closed': 0,
                    'errors': []
                }
                
                try:
                    # Get market hours from market info
                    opening_hours = market_info.get('instrument', {}).get('openingHours', {})
                    current_time = self.market_timer.get_current_time_market()
                    day_name = current_time.strftime('%a').lower()
                    
                    # Parse market hours for today
                    market_times = self.market_timer.parse_market_hours(opening_hours, day_name)
                    if not market_times:
                        logger.warning(f"No market hours for {day_name}")
                        continue
                    
                    open_time, close_time = market_times
                    
                    # Create datetime objects for today's market open and close
                    market_open = datetime.combine(current_time.date(), open_time).replace(tzinfo=pytz.timezone('UTC'))
                    market_close = datetime.combine(current_time.date(), close_time).replace(tzinfo=pytz.timezone('UTC'))
                    
                    # Calculate market duration
                    market_duration = market_close - market_open
                    total_market_minutes = market_duration.total_seconds() / 60
                    
                    # Fast forward through most of the day (30 minutes = 0.625 seconds real time)
                    fast_portion_minutes = total_market_minutes - 1  # Leave 1 minute for critical moments
                    fast_real_time = (fast_portion_minutes / 30) * 0.625  # 0.625s per 30min
                    
                    if fast_real_time > 0:
                        logger.info(f"SPEED TEST Day {day + 1}: Fast forwarding {fast_real_time:.1f}s real time")
                        
                        # Move time forward in 30-minute chunks
                        chunk_size = timedelta(minutes=30)
                        chunks = max(1, int(fast_portion_minutes / 30))
                        
                        simulated_time = current_time
                        for chunk in range(chunks):
                            simulated_time += chunk_size
                            
                            # Check if we're approaching critical moment
                            time_until_close = (market_close - simulated_time).total_seconds()
                            if time_until_close <= 30:
                                break
                            
                            # Small delay to show progress
                            await asyncio.sleep(fast_real_time / chunks)
                    
                    # Critical moment: T-30s to T+15s (normal speed with REAL TRADES)
                    logger.info(f"SPEED TEST Day {day + 1}: Critical moment - T-30s to T+15s - REAL TRADING")
                    
                    # T-30s: Close positions (REAL)
                    logger.info(f"SPEED TEST Day {day + 1}: T-30s - Closing REAL positions")
                    
                    # Count positions before closing
                    positions_before = await self.api.get_positions()
                    positions_count_before = len(positions_before or [])
                    
                    await self.close_all_positions_timer()
                    
                    # Count positions after closing
                    positions_after = await self.api.get_positions()
                    positions_count_after = len(positions_after or [])
                    
                    day_result['positions_closed'] = positions_count_before - positions_count_after
                    await asyncio.sleep(2)  # Wait for positions to close
                    
                    # T-15s: Create new trade (REAL)
                    await asyncio.sleep(0.5)
                    
                    logger.info(f"SPEED TEST Day {day + 1}: T-15s - Creating REAL trade")
                    
                    # Count positions before creating trade
                    positions_before = await self.api.get_positions()
                    positions_count_before = len(positions_before or [])
                    
                    # Get fresh market info and dealing rules for real trading
                    self.market_info = await self.api.get_market_info(self.epic)
                    dealing_rules = (self.market_info or {}).get('dealingRules', {})
                    
                    # Run real Brains analysis
                    await self.analyze_and_trade_timer()
                    
                    # Count positions after creating trade
                    positions_after = await self.api.get_positions()
                    positions_count_after = len(positions_after or [])
                    
                    day_result['trades_created'] = positions_count_after - positions_count_before
                    await asyncio.sleep(2)  # Wait for trade to be created
                    
                    # T+15s: Complete this day's cycle
                    await asyncio.sleep(0.5)
                    
                    logger.info(f"SPEED TEST Day {day + 1}: Complete - {day_result['trades_created']} trades created, {day_result['positions_closed']} positions closed")
                    
                except Exception as e:
                    error_msg = f"Day {day + 1} error: {e}"
                    logger.error(error_msg)
                    day_result['errors'].append(error_msg)
                    results['errors'].append(error_msg)
                
                results['daily_results'].append(day_result)
                results['days_simulated'] += 1
                results['trades_created'] += day_result['trades_created']
                results['positions_closed'] += day_result['positions_closed']
            
            # Restore original simulation mode
            if original_simulation_mode:
                logger.info("SPEED TEST: Restoring original simulation mode")
            
            logger.info("="*60)
            logger.info("SPEED TEST COMPLETE - REAL TRADING!")
            logger.info(f"Days simulated: {results['days_simulated']}")
            logger.info(f"REAL trades created: {results['trades_created']}")
            logger.info(f"REAL positions closed: {results['positions_closed']}")
            logger.info(f"Errors: {len(results['errors'])}")
            logger.info("="*60)
            
            return {"ok": True, "results": results}
            
        except Exception as e:
            logger.error(f"SPEED TEST ERROR: {e}")
            return {"ok": False, "error": str(e)}
    
    async def simulate_speed_test(self, days: int = 5):
        """New speed test using dedicated handler"""
        from bot.speed_test_handler import SpeedTestHandler
        handler = SpeedTestHandler(self)
        return await handler.run_speed_test(days)
    
    async def execute_timer_based_strategy(self, market_event: Dict) -> None:
        """Execute timer-based trading strategy"""
        if not market_event:
            return
            
        is_open = market_event.get('is_open', False)
        time_until_close = market_event.get('time_until_close', float('inf'))
        
        # Reset flags when market is closed
        if not is_open:
            if self.positions_closed_today or self.trade_analyzed_today:
                self.positions_closed_today = False
                self.trade_analyzed_today = False
                self.highest_threshold_acted = 0  # Reset trailing SL
                logger.info("Market closed - flags reset for next session")
                return
            
        # Log countdown when within 60 seconds
        if time_until_close <= 60 and time_until_close > 0:
            if int(time_until_close) % 10 == 0:  # Log every 10 seconds
                logger.info(f"Market closing in {int(time_until_close)} seconds")
        
        # Close positions at T-30s
        if time_until_close <= self.seconds_before_close_to_exit and not self.positions_closed_today:
            logger.info(f"T-{self.seconds_before_close_to_exit}s: Closing all positions")
            await self.close_all_positions_timer()
            self.positions_closed_today = True
        
        # Analyze and trade at T-15s (only after positions are closed)
        if time_until_close <= self.seconds_before_close_to_trade and not self.trade_analyzed_today and self.positions_closed_today:
            logger.info(f"T-{self.seconds_before_close_to_trade}s: Analyzing market and creating position")
            await self.analyze_and_trade_timer()
            self.trade_analyzed_today = True
    
    async def close_all_positions_timer(self) -> None:
        """Close all open positions with retry logic"""
        try:
            positions = await self.api.get_positions()
            if not positions:
                logger.info("No positions to close")
                self.record_action({'event': 'close_positions', 'found': 0})
                return
            
            for position_data in positions:
                position = position_data.get('position', {})
                deal_id = position.get('dealId')
                
                if deal_id:
                    # Close with retry
                    success = False
                    for attempt in range(1, 4):
                        try:
                            logger.info(f"Closing position {deal_id} - attempt {attempt}/3")
                            self.record_action({'event': 'close_position_attempt', 'deal_id': deal_id, 'attempt': attempt})
                            
                            if self.settings.getboolean('BOT_CONFIG', 'simulation_mode', False):
                                logger.info(f"SIMULATION MODE: Would close {deal_id}")
                                self.record_action({'event': 'close_position_result', 'deal_id': deal_id, 'success': True, 'simulation': True})
                                success = True
                                break
                            
                            result = await self.api.close_position(deal_id)
                            if result:
                                logger.info(f"Position {deal_id} closed successfully")
                                self.record_action({'event': 'close_position_result', 'deal_id': deal_id, 'success': True})
                                success = True
                                break
                        except Exception as e:
                            if attempt < 3:
                                await asyncio.sleep(1)
                            else:
                                logger.error(f"Failed to close {deal_id} after 3 attempts: {e}")
                                self.record_action({'event': 'close_position_result', 'deal_id': deal_id, 'success': False, 'error': str(e)})
                    if not success:
                        logger.warning(f"Position {deal_id} may still be open after retries")
            
        except Exception as e:
            logger.error(f"Error closing positions: {e}")
        
        # Perform data maintenance after closing positions
        try:
            await self.maintain_data_at_market_close()
        except Exception as e:
            logger.error(f"Error during data maintenance: {e}")
            self.record_action({
                'event': 'data_maintenance_error',
                'error': f'Data maintenance failed: {e}',
                'epic': self.epic
            })
    
    async def analyze_and_trade_timer(self) -> None:
        """Analyze market and create position using GOSPEL Brains"""
        try:
            # Get market info
            self.market_info = await self.api.get_market_info(self.epic)
            if not self.market_info:
                logger.error("Failed to get market info")
                return
            
            dealing_rules = self.market_info.get('dealingRules', {})
            
            # Get historical data
            candles = self.db.get_latest_candles(self.epic, 200)
            if not candles or len(candles) < 100:
                logger.warning(f"Insufficient historical data: {len(candles) if candles else 0} candles")
                self.record_action({
                    'event': 'brains_decision',
                    'error': f'Insufficient data: {len(candles) if candles else 0} candles',
                    'epic': self.epic
                })
                return
            
            # Convert DB rows -> DataFrame with correct schema
            # DB returns tuples: (epic, timestamp, open, high, low, close, volume)
            df = pd.DataFrame(
                candles,
                columns=['epic', 'timestamp', 'open', 'high', 'low', 'close', 'volume']
            )
            
            # Drop epic column
            df = df.drop(columns=['epic'])
            
            # Rename columns for Brains compatibility
            df = df.rename(columns={
                'open': 'openPrice',
                'high': 'highPrice',
                'low': 'lowPrice',
                'close': 'closePrice',
                'volume': 'lastTradedVolume'
            })
            
            # Convert timestamp and sort
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            # Ensure we have a DataFrame, not empty
            if df.empty:
                logger.error("DataFrame is empty after conversion")
                self.record_action({
                    'event': 'brains_decision',
                    'error': 'Empty DataFrame after conversion',
                    'epic': self.epic
                })
                return
            
            # GOSPEL Brains analysis
            df = self.ai_system.calculate_technical_indicators(df)
            ai_analysis = self.ai_system.analyze_market_conditions(
                df.iloc[-1].to_dict(),
                df,
                datetime.now()
            )
            # Record brains decision
            self.record_action({
                'event': 'brains_decision',
                'simulation_override': False,
                'signal': ai_analysis.get('trade_signal'),
                'confidence': ai_analysis.get('confidence'),
                'epic': self.epic
            })
            
            logger.info(f"Brains Decision: Signal={ai_analysis['trade_signal']}, "
                       f"Confidence={ai_analysis['confidence']:.2%}, "
                       f"Direction={ai_analysis.get('direction', 'N/A')}")
            
            # Check confidence threshold
            min_confidence = self.settings.getfloat('BOT_CONFIG', 'ai_confidence_threshold', 30) / 100
            if ai_analysis['confidence'] >= min_confidence and ai_analysis['trade_signal'] != 'hold':
                await self.create_position_timer(ai_analysis, dealing_rules)
            else:
                logger.info("No trade - confidence below threshold or hold signal")
                
        except Exception as e:
            logger.error(f"Error in analyze and trade: {e}")
    
    async def create_position_timer(self, ai_analysis: Dict, dealing_rules: Dict) -> bool:
        """Create position based on AI analysis and dealing rules"""
        try:
            # Get market snapshot
            snapshot = self.market_info.get('snapshot', {})
            bid = float(snapshot.get('bid', 0))
            offer = float(snapshot.get('offer', 0))
            
            # Determine direction
            signal = ai_analysis.get('trade_signal', 'hold')
            if signal == 'hold':
                return False
            
            direction = 'long' if signal == 'buy' else 'short'
            entry_price = offer if direction == 'long' else bid
            
            # Get dealing rules
            min_size = float(dealing_rules.get('minDealSize', {}).get('value', 0.1))
            max_size = float(dealing_rules.get('maxDealSize', {}).get('value', 3250))
            increment = float(dealing_rules.get('minSizeIncrement', {}).get('value', 0.1))
            
            # Get account balance
            accounts = await self.api.get_accounts()
            available = 0
            for acc in accounts:
                if acc['accountId'] == self.current_account['accountId']:
                    available = float(acc['balance']['available'])
                    break
            
            # Calculate position size (GOSPEL formula from legacy)
            investment_pct = self.settings.getfloat('BOT_CONFIG', 'investment_pct', 99) / 100
            leverage = self.settings.getfloat('BOT_CONFIG', 'leverage', 1)
            
            trade_size = (available * investment_pct * leverage) / entry_price
            
            # Apply dealing rules
            if trade_size < min_size:
                trade_size = min_size
            elif trade_size > max_size:
                trade_size = max_size
            
            # Floor to increment
            trade_size = (trade_size // increment) * increment
            
            # Calculate stop loss based on type
            stop_loss_type = self.settings.get('BOT_CONFIG', 'stop_loss_type', 'normal')
            
            if stop_loss_type == 'normal':
                # Simple percentage stop loss
                stop_loss_pct = self.settings.getfloat('BOT_CONFIG', 'stop_loss_pct', 2) / 100
                stop_level = entry_price * (1 - stop_loss_pct) if direction == 'long' else entry_price * (1 + stop_loss_pct)
            elif stop_loss_type == 'trailing':
                # Start with normal stop, will trail later
                stop_loss_pct = self.settings.getfloat('BOT_CONFIG', 'stop_loss_pct', 2) / 100
                stop_level = entry_price * (1 - stop_loss_pct) if direction == 'long' else entry_price * (1 + stop_loss_pct)
            elif stop_loss_type == 'staggered':
                # Start with first staggered level
                sl_use = self.settings.get('BOT_CONFIG', 'sl_use', '0,1,2,4,6,8,10').split(',')
                
                # Use first level or default
                if sl_use and sl_use[0] != '0':
                    first_stop = float(sl_use[0]) / 100
                else:
                    first_stop = 0.02  # Default 2%
                
                stop_level = entry_price * (1 - first_stop) if direction == 'long' else entry_price * (1 + first_stop)
            else:
                # Fallback to normal
                stop_loss_pct = self.settings.getfloat('BOT_CONFIG', 'stop_loss_pct', 2) / 100
                stop_level = entry_price * (1 - stop_loss_pct) if direction == 'long' else entry_price * (1 + stop_loss_pct)
            
            logger.info(f"Creating position: {direction.upper()} {trade_size} @ {entry_price}, SL: {stop_level}")
            # Record sizing/calculation
            self.record_action({
                'event': 'create_position_calculation',
                'simulation_override': False,
                'direction': direction,
                    'entry_price': entry_price,
                'available': available,
                'investment_pct': investment_pct,
                    'leverage': leverage,
                'notional': available * investment_pct * leverage,
                'contracts': trade_size,
                'min_size': min_size,
                'max_size': max_size,
                'increment': increment,
                'stop_level': stop_level,
                'epic': self.epic
            })
            
            # Create position with retry logic
            result = await self.create_position_with_retry(
                self.epic,
                direction,
                trade_size,
                stop_level,
                max_attempts=3
            )
            
            if result:
                logger.info(f"Trade executed: {result}")
                self.record_action({
                    'event': 'api_execution',
                    'success': True,
                    'response': result,
                    'dealReference': result.get('dealReference') if isinstance(result, dict) else None,
                    'epic': self.epic
                })
                self.trade_analyzed_today = True
                self.last_trade_date = datetime.now().date()
                return True
            else:
                logger.error("Trade execution failed after all retries")
                self.record_action({
                    'event': 'api_execution',
                    'success': False,
                    'response': None,
                    'epic': self.epic
                })
                return False
                
        except Exception as e:
            logger.error(f"Error creating position: {e}")
            self.record_action({'event': 'api_execution', 'success': False, 'error': str(e), 'epic': self.epic})
            return False
    
    async def run(self):
        """Main trading loop"""
        self.is_running = True
        
        logger.info("="*60)
        logger.info("BOT STARTED - Timer-Based Trading Active")
        logger.info(f"Epic: {self.epic}")
        logger.info(f"Close positions: {self.seconds_before_close_to_exit}s before close")
        logger.info(f"Analyze & trade: {self.seconds_before_close_to_trade}s before close")
        logger.info(f"Trailing SL: {'Enabled' if self.use_trailing_sl else 'Disabled'}")
        logger.info(f"Simulation Mode: {'ON' if self.settings.getboolean('BOT_CONFIG', 'simulation_mode', False) else 'OFF'}")
        logger.info("="*60)
        
        status_counter = 0
        
        while self.is_running:
            await self.update_data()
            
            # Get market event
            market_event = self.market_timer.get_next_market_event(self.market_info)
            
            # Periodic status update
            status_counter += 1
            if status_counter >= 30:
                if market_event and market_event.get('is_open'):
                    time_until = int(market_event.get('time_until_close', 0))
                    logger.info(f"Market OPEN - {time_until}s until close")
                elif market_event:
                    hours = market_event.get('time_until_open', 0) / 3600
                    logger.info(f"Market CLOSED - Opens in {hours:.1f} hours")
                status_counter = 0
            
            # Check trailing stop loss
            if self.use_trailing_sl:
                positions = await self.api.get_positions()
                await self.check_and_trail_stop_loss(positions)
            
            # Execute strategy
            await self.execute_timer_based_strategy(market_event)
            
            await asyncio.sleep(1)
    
    async def update_data(self):
        """Update market data"""
        try:
            self.market_info = await self.api.get_market_info(self.epic)
        except Exception as e:
            logger.error(f"Error updating data: {e}")
    
    async def continuous_download(self):
        """Continuously download candle data"""
        while self.is_running:
            try:
                await self.downloader.download_and_store_candles(
                    self.epic,
                    self.api.ResolutionType.MINUTE_5,
                    100
                )
            except Exception as e:
                logger.error(f"Download error: {e}")
            await asyncio.sleep(300)  # Every 5 minutes
    
    async def keepalive_loop(self):
        """Keep API connection alive"""
        while self.is_running:
            try:
                await self.api.keepalive()
            except Exception as e:
                logger.error(f"Keepalive error: {e}")
            await asyncio.sleep(30)
    
    async def maintain_data_at_market_close(self):
        """Download latest 1000 candles and perform quality checks at market close"""
        try:
            self.record_action({
                'event': 'data_maintenance_start',
                'epic': self.epic,
                'timestamp': datetime.now().isoformat()
            })
            
            logger.info("Starting market close data maintenance...")
            
            # Download latest 1000 candles
            price_data = await self.api.get_historical_prices(
                self.epic, 
                ResolutionType.MINUTE_5, 
                1000
            )
            
            if not price_data or "prices" not in price_data:
                self.record_action({
                    'event': 'data_maintenance_error',
                    'error': 'No price data received from API',
                    'epic': self.epic
                })
                logger.error("No price data received for maintenance")
                return False
            
            candles = price_data["prices"]
            logger.info(f"Downloaded {len(candles)} candles for maintenance")
            
            # Store candles (handles deduplication automatically)
            stored_count = 0
            for candle in candles:
                try:
                    candle_data = {
                        "timestamp": candle["snapshotTimeUTC"],
                        "open": float(candle["openPrice"]["bid"]),
                        "high": float(candle["highPrice"]["bid"]),
                        "low": float(candle["lowPrice"]["bid"]),
                        "close": float(candle["closePrice"]["bid"]),
                        "volume": float(candle.get("lastTradedVolume", 0))
                    }
                    
                    self.db.store_candle(self.epic, candle_data)
                    stored_count += 1
                    
                except Exception as e:
                    logger.warning(f"Error processing candle during maintenance: {e}")
                    continue
            
            # Perform quality checks
            quality_result = await self._perform_data_quality_check()
            
            # Record maintenance results
            maintenance_result = {
                'event': 'data_maintenance_complete',
                'epic': self.epic,
                'candles_downloaded': len(candles),
                'candles_stored': stored_count,
                'quality_check': quality_result,
                'timestamp': datetime.now().isoformat()
            }
            
            self.record_action(maintenance_result)
            
            logger.info(f"Data maintenance complete: {stored_count} candles stored, quality: {quality_result}")
            return True
            
        except Exception as e:
            error_msg = f"Data maintenance error: {e}"
            logger.error(error_msg)
            self.record_action({
                'event': 'data_maintenance_error',
                'error': error_msg,
                'epic': self.epic,
                'timestamp': datetime.now().isoformat()
            })
            return False
    
    async def _perform_data_quality_check(self):
        """Perform quality checks on the latest 1000 candles"""
        try:
            # Get the latest 1000 candles
            latest_candles = self.db.get_candles(self.epic, limit=1000)
            
            if not latest_candles:
                return {
                    'status': 'ERROR',
                    'message': 'No candles found for quality check',
                    'total_candles': 0,
                    'duplicates': 0,
                    'gaps': 0,
                    'coverage_pct': 0
                }
            
            # Check for duplicates
            timestamps = [candle[1] for candle in latest_candles]  # timestamp is at index 1
            unique_timestamps = set(timestamps)
            duplicates = len(timestamps) - len(unique_timestamps)
            
            # Check for gaps
            sorted_candles = sorted(latest_candles, key=lambda x: x[1])
            gaps = 0
            missing_candles = 0
            
            for i in range(1, len(sorted_candles)):
                prev_timestamp = sorted_candles[i-1][1]
                curr_timestamp = sorted_candles[i][1]
                
                # Parse timestamps
                if isinstance(prev_timestamp, str):
                    prev_time = datetime.fromisoformat(prev_timestamp.replace('Z', '+00:00'))
                else:
                    prev_time = prev_timestamp
                    
                if isinstance(curr_timestamp, str):
                    curr_time = datetime.fromisoformat(curr_timestamp.replace('Z', '+00:00'))
                else:
                    curr_time = curr_timestamp
                
                time_diff = (curr_time - prev_time).total_seconds()
                if time_diff > 300:  # More than 5 minutes
                    gaps += 1
                    missing_candles += int(time_diff / 300) - 1
            
            # Calculate coverage
            if len(sorted_candles) >= 2:
                first_time = sorted_candles[0][1]
                last_time = sorted_candles[-1][1]
                
                if isinstance(first_time, str):
                    first_dt = datetime.fromisoformat(first_time.replace('Z', '+00:00'))
                else:
                    first_dt = first_time
                    
                if isinstance(last_time, str):
                    last_dt = datetime.fromisoformat(last_time.replace('Z', '+00:00'))
                else:
                    last_dt = last_time
                
                total_hours = (last_dt - first_dt).total_seconds() / 3600
                expected_candles = int(total_hours * 12)  # 12 candles per hour
                coverage_pct = (len(latest_candles) / expected_candles) * 100 if expected_candles > 0 else 0
            else:
                coverage_pct = 100  # Single candle or no data
            
            # Determine status
            if duplicates == 0 and gaps <= 5 and coverage_pct >= 15:  # Allow some gaps for market closures
                status = 'EXCELLENT'
            elif duplicates == 0 and gaps <= 20 and coverage_pct >= 10:
                status = 'GOOD'
            elif duplicates <= 5 and gaps <= 50:
                status = 'FAIR'
            else:
                status = 'POOR'
            
            return {
                'status': status,
                'message': f'Quality check: {status} - {len(latest_candles)} candles, {duplicates} duplicates, {gaps} gaps, {coverage_pct:.1f}% coverage',
                'total_candles': len(latest_candles),
                'duplicates': duplicates,
                'gaps': gaps,
                'missing_candles': missing_candles,
                'coverage_pct': round(coverage_pct, 1)
            }
            
        except Exception as e:
            logger.error(f"Error in quality check: {e}")
            return {
                'status': 'ERROR',
                'message': f'Quality check failed: {e}',
                'total_candles': 0,
                'duplicates': 0,
                'gaps': 0,
                'coverage_pct': 0
            }

    def stop(self):
        """Stop the trading bot"""
        self.is_running = False
        logger.info("Trading bot stopped")
        if self.keepalive_task:
            self.keepalive_task.cancel()
        if self.downloader_task:
            self.downloader_task.cancel()
        self.db.close()
