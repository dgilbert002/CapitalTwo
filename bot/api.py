import asyncio
import logging
from typing import Dict, List, Optional

import capitalcom.client as capital_client
import capitalcom.client_demo as capital_client_demo

from bot.settings import TradingBotSettings

logger = logging.getLogger(__name__)

class CapitalComAPI:
    """Capital.com API client using the capitalcom-python library"""

    def __init__(self, settings: TradingBotSettings, environment: Optional[str] = None):
        self.settings = settings
        self.client: Optional[object] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.environment: str = (environment or self.settings.get("API_CONFIG", "environment", "demo")).lower() or "demo"
        self.ClientClass = capital_client_demo.Client if self.environment == "demo" else capital_client.Client

    @property
    def ResolutionType(self):
        # Use ResolutionType from main client module (same string values in demo)
        return capital_client.ResolutionType

    async def _run_sync(self, func, *args, **kwargs):
        """Runs a synchronous function in a thread pool."""
        if not self.loop:
            self.loop = asyncio.get_running_loop()
        return await self.loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def authenticate(self) -> bool:
        """Authenticate with Capital.com API"""
        try:
            email = self.settings.get("CREDENTIALS", "email")
            password = self.settings.get("CREDENTIALS", "password")
            api_key = self.settings.get("CREDENTIALS", "api_key")

            logging.getLogger(__name__).info(f"CapitalComAPI.authenticate(environment={self.environment})")
            self.client = await self._run_sync(self.ClientClass, email, password, api_key)
            
            if self.client and self.client.cst:
                logger.info("Successfully authenticated with Capital.com")
                return True
            else:
                logger.error("Authentication failed. Check credentials and API key.")
                return False

        except Exception as e:
            logger.error(f"Authentication error: {e}")
            return False

    async def get_accounts(self) -> List[Dict]:
        """Get account information"""
        try:
            accounts_data = await self._run_sync(self.client.all_accounts)
            accounts = accounts_data.get("accounts", [])
            logger.debug(f"Accounts fetched: {len(accounts)}")
            return accounts
        except Exception as e:
            logger.error(f"Error getting accounts: {e}")
            return []

    async def switch_account(self, account_id: str) -> bool:
        """Switch to specific account"""
        try:
            await self._run_sync(self.client.switch_account, account_id)
            logger.info(f"Switched to account: {account_id}")
            return True
        except Exception as e:
            logger.error(f"Error switching account: {e}")
            return False

    async def get_positions(self) -> List[Dict]:
        """Get open positions"""
        try:
            positions_data = await self._run_sync(self.client.all_positions)
            return positions_data.get("positions", [])
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def get_market_info(self, epic: str) -> Optional[Dict]:
        """Get market information for an epic"""
        try:
            market_data = await self._run_sync(self.client.single_market, epic)
            if market_data:
                # Log all top-level keys
                logger.info(f"Market data keys for {epic}: {list(market_data.keys())}")
                
                # Log snapshot data if available
                if market_data.get('snapshot'):
                    snapshot = market_data['snapshot']
                    logger.info(f"Snapshot for {epic}: bid={snapshot.get('bid')}, offer={snapshot.get('offer')}, high={snapshot.get('high')}, low={snapshot.get('low')}, percentageChange={snapshot.get('percentageChange')}")
                
                # Log instrument data if available
                if market_data.get('instrument'):
                    instrument = market_data['instrument']
                    logger.info(f"Instrument for {epic}: name={instrument.get('name')}, type={instrument.get('type')}, marketId={instrument.get('marketId')}, expiry={instrument.get('expiry')}, lotSize={instrument.get('lotSize')}")
                    
                    # Log opening hours if available
                    if instrument.get('openingHours'):
                        hours = instrument['openingHours']
                        logger.info(f"Opening hours for {epic}: {hours}")
                    
                    # Log dealing rules if available (check both locations)
                    if instrument.get('dealingRules'):
                        rules = instrument['dealingRules']
                        logger.info(f"Dealing rules (from instrument): minDealSize={rules.get('minDealSize')}, maxDealSize={rules.get('maxDealSize')}, minSizeIncrement={rules.get('minSizeIncrement')}")
                
                # Check for dealing rules at top level too
                if market_data.get('dealingRules'):
                    rules = market_data['dealingRules']
                    logger.info(f"Dealing rules (top level): minDealSize={rules.get('minDealSize')}, maxDealSize={rules.get('maxDealSize')}, minSizeIncrement={rules.get('minSizeIncrement')}")
                
            return market_data
        except Exception as e:
            logger.error(f"Error getting market info for {epic}: {e}")
            return None
            
    async def get_historical_prices(self, epic: str, resolution, num_candles: int) -> Optional[Dict]:
        """Get historical price data."""
        try:
            if not self.client:
                logger.error(f"Client not initialized for historical prices")
                return None
            return await self._run_sync(self.client.historical_price, epic, resolution, num_candles)
        except Exception as e:
            logger.error(f"Error getting historical prices for {epic}: {e}")
            return None

    async def create_position(self, epic: str, direction: str, size: float, stop_level: Optional[float] = None) -> Optional[Dict]:
        """Create a new position"""
        try:
            # Import DirectionType from the appropriate module
            if self.environment == "demo":
                from capitalcom.client_demo import DirectionType
            else:
                from capitalcom.client import DirectionType
            
            # Convert string direction to DirectionType enum
            trade_direction = DirectionType.BUY if direction.lower() == "long" else DirectionType.SELL
            
            # Create position with proper parameters
            # capitalcom client expects Python kw 'stopLevel' (maps to JSON stopLevel)
            kwargs = {
                'direction': trade_direction,
                'epic': epic,
                'size': size,
            }
            if stop_level:
                # capitalcom-python expects snake_case stop_level
                kwargs['stop_level'] = float(stop_level)

            position = await self._run_sync(self.client.place_the_position, **kwargs)
            logger.info(f"Position creation response: {position}")
            return position
        except Exception as e:
            logger.error(f"Error creating position: {e}")
            return None

    async def close_position(self, deal_id: str) -> bool:
        """Close a position"""
        try:
            await self._run_sync(self.client.close_position, deal_id)
            logger.info(f"Position closed: {deal_id}")
            return True
        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    async def keepalive(self) -> bool:
        """Ping the API to keep the session alive."""
        try:
            await self._run_sync(self.client.check_server_time)
            logger.debug("Keepalive OK")
            return True
        except Exception as e:
            logger.warning(f"Keepalive failed: {e}")
            return False
    
    async def get_trade_history(self, days: int = 7) -> List[Dict]:
        """Get trade history for the last N days using the client's built-in method"""
        try:
            # The capitalcom client has account_transactions_history() method
            # which returns all transactions - we can filter for trades
            history = await self._run_sync(self.client.account_transactions_history)
            
            transactions = []
            if history and 'transactions' in history:
                transactions = history['transactions']
                
            # Fallback: try account_activity_history if transactions empty
            if not transactions:
                try:
                    activity = await self._run_sync(self.client.account_activity_history)
                    if activity and 'activities' in activity:
                        # Normalize activity entries with trade-like fields
                        for a in activity.get('activities', []):
                            if a.get('type') in ('TRADE', 'POSITION'):
                                transactions.append({
                                    'dateUTC': a.get('dateUTC') or a.get('date') or '',
                                    'epic': a.get('epic') or a.get('instrument', {}).get('epic'),
                                    'instrumentName': a.get('instrumentName') or a.get('instrument', {}).get('name'),
                                    'direction': a.get('direction'),
                                    'size': a.get('size') or a.get('dealSize'),
                                    'openLevel': a.get('openLevel') or a.get('level'),
                                    'closeLevel': a.get('closeLevel'),
                                    'profit': a.get('profitAndLoss') or a.get('profit') or a.get('pnl'),
                                    'dealId': a.get('dealId') or a.get('reference')
                                })
                except Exception:
                    pass

            # Filter for TRADE type transactions only
            trades = [t for t in transactions if t.get('type') == 'TRADE' or 'openLevel' in t or 'closeLevel' in t]

            # Sort by date (newest first)
            trades.sort(key=lambda x: x.get('dateUTC', ''), reverse=True)

            # Filter by date if needed
            if days and days > 0:
                from datetime import datetime, timedelta
                cutoff = datetime.utcnow() - timedelta(days=days)
                cutoff_str = cutoff.isoformat()
                trades = [t for t in trades if t.get('dateUTC', '') >= cutoff_str]

            logger.info(f"Fetched {len(trades)} historical trades")
            if trades:
                logger.info(f"Trade history fields: {list(trades[0].keys())}")
                sample = str(trades[0])[:500]
                logger.info(f"First trade sample: {sample}")

            return trades
                
        except Exception as e:
            logger.error(f"Error getting trade history: {e}", exc_info=True)
            return []

