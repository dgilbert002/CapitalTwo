import asyncio
import logging
import pandas as pd
from datetime import time, datetime

from bot.api import CapitalComAPI
from bot.database import DatabaseManager
from bot.market_time import MarketTimeManager
from bot.settings import TradingBotSettings
from bot.ai_system import HybridIntelligentSystem
from bot.data_downloader import DataDownloader
from capitalcom.client import ResolutionType

logger = logging.getLogger(__name__)

class TradingBot:
    """Main trading bot class with complete Hybrid Intelligent System"""
    
    def __init__(self):
        self.settings = TradingBotSettings()
        self.api = CapitalComAPI(self.settings)
        self.db_manager = DatabaseManager()
        self.market_timer = MarketTimeManager(self.settings)
        self.ai_system = HybridIntelligentSystem()
        self.downloader = DataDownloader(self.api, self.db_manager)
        self.is_running = False
        self.api_connected = False
        self.current_account = None
        self.market_info = {}
        self.positions = []
        self.balance_info = {}
        self.last_trade_date = None
        self.current_position = None
        self.trade_history = []
        self.winning_trades = 0
        self.losing_trades = 0
        self.total_fees = 0
        self.keepalive_task = None
        self.downloader_task = None
        
    async def initialize(self) -> bool:
        """Initialize the trading bot"""
        try:
            if not await self.api.authenticate():
                return False
            self.api_connected = True
            
            accounts = await self.api.get_accounts()
            if not accounts:
                logger.error("No accounts found")
                return False
            
            env = self.api.environment
            account_id = self.settings.get("ENV_ACCOUNTS", env, "") or self.settings.get("CREDENTIALS", "account_id")
            target_account = None

            if account_id:
                target_account = next((acc for acc in accounts if acc.get("accountId") == account_id), None)
                if not target_account:
                    logger.warning(f"Account {account_id} not found, using first available account.")

            if not target_account:
                target_account = accounts[0]

            self.current_account = target_account
            account_id_to_switch = self.current_account.get("accountId")
            
            if not await self.api.switch_account(account_id_to_switch):
                 return False

            logger.info(f"Using account: {self.current_account.get('accountName', 'Unknown')}")
            
            epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
            self.market_info = await self.api.get_market_info(epic)

            # Start continuous data download (cancel old if exists)
            if self.downloader_task and not self.downloader_task.done():
                self.downloader_task.cancel()
            self.downloader_task = asyncio.create_task(
                self.downloader.continuous_download(epic, ResolutionType.MINUTE_5, 300)
            )
            # Start keepalive pings every 4 minutes
            self.keepalive_task = asyncio.create_task(self._keepalive_loop())
            
            return True
            
        except Exception as e:
            logger.error(f"Initialization error: {e}")
            return False
    
    async def update_data(self):
        """Update all bot data"""
        try:
            self.positions = await self.api.get_positions()
            
            if self.current_account:
                accounts = await self.api.get_accounts()
                current_account_id = self.current_account.get("accountId")
                updated_account = next((acc for acc in accounts if acc.get("accountId") == current_account_id), None)
                if updated_account:
                    self.current_account = updated_account
                    self.balance_info = updated_account.get("balance", {})
            
            epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
            market_data = await self.api.get_market_info(epic)
            if market_data:
                self.market_info = market_data
                # Log minimal market info snapshot for troubleshooting
                logger.debug(f"Market snapshot updated for {epic}")
                
        except Exception as e:
            logger.error(f"Error updating data: {e}")

    async def run(self):
        """Main trading loop with complete Hybrid Intelligent Strategy"""
        self.is_running = True
        logger.info("Trading bot started with Hybrid Intelligent System")
        
        while self.is_running:
            await self.update_data()
            await self.execute_hybrid_intelligent_strategy()
            await asyncio.sleep(5)

    async def _keepalive_loop(self):
        while True:
            try:
                await asyncio.sleep(240)
                await self.api.keepalive()
            except Exception as e:
                logger.warning(f"Keepalive loop error: {e}")

    async def execute_hybrid_intelligent_strategy(self):
        """Execute the complete Hybrid Intelligent Trading Strategy"""
        market_event = self.market_timer.get_next_market_event(self.market_info)
        now = self.market_timer.get_current_time_market()
        current_date = now.date()

        if not market_event.get("is_open"):
            return

        epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
        
        # Get day data (simulated as we don't have intraday data in real-time)
        day_data = pd.DataFrame()  # This would be populated with real intraday data
        
        # Get historical data for AI analysis
        candles = self.db_manager.get_candles(epic, limit=200)
        if len(candles) < 50:
            logger.warning("Not enough historical data for AI analysis")
            return

        df = pd.DataFrame(candles, columns=["epic", "timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df.set_index("timestamp", inplace=True)

        # Calculate technical indicators
        historical_data = self.ai_system.calculate_technical_indicators(df)

        # Market times (matching the uploaded strategy exactly)
        analysis_time = time(15, 30)
        entry_time = time(15, 59, 45)
        exit_time = time(15, 59, 30)

        # Step 1: Close existing position if exists
        if self.current_position is not None:
            await self.close_current_position(day_data, exit_time, current_date)

        # Step 2: AI Analysis for new position (only during analysis time window)
        if now.time() >= analysis_time and now.date() != self.last_trade_date:
            ai_analysis = self.ai_system.analyze_market_conditions(day_data, historical_data, current_date)
            
            logger.info(f"AI Analysis: {ai_analysis}")

            # Step 3: Decision to trade based on AI analysis and confidence threshold
            confidence_threshold = self.settings.getfloat("BOT_CONFIG", "ai_confidence_threshold", 30.0) / 100.0
            
            if (ai_analysis['trade_signal'] in ['buy', 'sell'] and 
                ai_analysis['confidence'] > confidence_threshold and
                now.time() >= entry_time):
                
                await self.create_new_position(ai_analysis, current_date, entry_time)
                self.last_trade_date = current_date

    async def close_current_position(self, day_data, exit_time, current_date):
        """Close existing position with stop-loss monitoring"""
        try:
            stop_loss_pct = self.settings.getfloat("BOT_CONFIG", "stop_loss_pct", 2.0)
            
            # Check if stopped out during the day (in real implementation, this would check intraday data)
            stop_hit, stop_price, stop_time = self.ai_system.check_stop_loss_hit(
                day_data, self.current_position['entry_price'], self.current_position['entry_time'], 
                self.current_position['direction'], stop_loss_pct
            )
            
            if stop_hit:
                exit_price = stop_price
                exit_reason = f'stop_loss_{stop_loss_pct}%'
                logger.info(f"Position stopped out at {stop_price}")
            else:
                # Get current market price for exit
                epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
                market_data = await self.api.get_market_info(epic)
                if market_data and 'snapshot' in market_data:
                    exit_price = market_data['snapshot']['bid']
                else:
                    exit_price = self.current_position['entry_price']
                exit_reason = 'scheduled_exit'
            
            # Calculate P&L
            if self.current_position['direction'] == 'long':
                gross_return = (exit_price - self.current_position['entry_price']) / self.current_position['entry_price']
            else:
                gross_return = (self.current_position['entry_price'] - exit_price) / self.current_position['entry_price']
            
            gross_pnl = self.current_position['position_size'] * gross_return
            trade_costs = self.ai_system.calculate_trading_costs(
                self.current_position['position_size'], 
                self.current_position['direction'], 
                is_overnight=True
            )
            net_pnl = gross_pnl - trade_costs
            
            # Update balance (simulated)
            self.total_fees += trade_costs
            
            if net_pnl > 0:
                self.winning_trades += 1
            else:
                self.losing_trades += 1
            
            # Record trade
            trade_record = {
                'entry_date': self.current_position['entry_date'],
                'exit_date': current_date,
                'direction': self.current_position['direction'],
                'entry_price': self.current_position['entry_price'],
                'exit_price': exit_price,
                'position_size': self.current_position['position_size'],
                'gross_pnl': gross_pnl,
                'net_pnl': net_pnl,
                'trade_costs': trade_costs,
                'exit_reason': exit_reason,
                'ai_confidence': self.current_position.get('ai_confidence', 0)
            }
            self.trade_history.append(trade_record)
            
            logger.info(f"Position closed: {trade_record}")
            
            # Close position via API
            for position in self.positions:
                await self.api.close_position(position["position"]["dealId"])
            
            self.current_position = None
            
        except Exception as e:
            logger.error(f"Error closing position: {e}")

    async def create_new_position(self, ai_analysis, current_date, entry_time):
        """Create new position based on AI analysis"""
        try:
            epic = self.settings.get("BOT_CONFIG", "epic", "TECL")
            
            # Get current market price
            market_data = await self.api.get_market_info(epic)
            if not market_data or 'snapshot' not in market_data:
                logger.warning("Could not get market data for entry")
                return
            
            entry_price = market_data['snapshot']['offer']  # Use offer price for entry
            
            # Calculate position size
            leverage = self.settings.getfloat("BOT_CONFIG", "leverage", 4.0)
            investment_pct = self.settings.getfloat("BOT_CONFIG", "investment_pct", 99.0) / 100.0
            balance = self.balance_info.get("available", 0)
            
            if balance <= 0:
                logger.warning("No available balance for trading")
                return
            
            investment_amount = balance * investment_pct
            position_size = investment_amount * leverage
            
            # Calculate stop loss
            stop_loss_pct = self.settings.getfloat("BOT_CONFIG", "stop_loss_pct", 2.0)
            stop_level = None
            if ai_analysis['direction'] == 'long':
                stop_level = entry_price * (1 - stop_loss_pct / 100)
            else:
                stop_level = entry_price * (1 + stop_loss_pct / 100)
            
            # Create position via API
            position_result = await self.api.create_position(
                epic, 
                ai_analysis['direction'], 
                position_size, 
                stop_level
            )
            
            if position_result:
                # Store current position details
                self.current_position = {
                    'entry_date': current_date,
                    'entry_time': entry_time,
                    'direction': ai_analysis['direction'],
                    'entry_price': entry_price,
                    'position_size': position_size,
                    'leverage': leverage,
                    'ai_confidence': ai_analysis['confidence'],
                    'ai_reasoning': ai_analysis['reasoning'],
                    'stop_level': stop_level
                }
                
                logger.info(f"New position created: {self.current_position}")
            else:
                logger.error("Failed to create position via API")
                
        except Exception as e:
            logger.error(f"Error creating position: {e}")

    def stop(self):
        """Stop the trading bot"""
        self.is_running = False
        logger.info("Trading bot stopped")
        if self.keepalive_task:
            self.keepalive_task.cancel()
        if self.downloader_task:
            self.downloader_task.cancel()
        
        # Log final statistics
        total_trades = self.winning_trades + self.losing_trades
        if total_trades > 0:
            win_rate = self.winning_trades / total_trades * 100
            logger.info(f"Final Stats - Total Trades: {total_trades}, Win Rate: {win_rate:.1f}%, Total Fees: ${self.total_fees:.2f}")
