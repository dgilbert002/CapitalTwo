import asyncio
import logging
from typing import Dict, List, Optional

from capitalcom.client import Client, ResolutionType

from bot.settings import TradingBotSettings

logger = logging.getLogger(__name__)

class CapitalComAPI:
    """Capital.com API client using the capitalcom-python library"""

    def __init__(self, settings: TradingBotSettings):
        self.settings = settings
        self.client: Optional[Client] = None
        self.loop: Optional[asyncio.AbstractEventLoop] = None

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

            self.client = await self._run_sync(Client, email, password, api_key)
            
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
            logger.info(f"Found {len(accounts)} accounts.")
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
            return await self._run_sync(self.client.single_market, epic)
        except Exception as e:
            logger.error(f"Error getting market info for {epic}: {e}")
            return None
            
    async def get_historical_prices(self, epic: str, resolution: ResolutionType, num_candles: int) -> Optional[Dict]:
        """Get historical price data."""
        try:
            return await self._run_sync(self.client.historical_price, epic, resolution, num_candles)
        except Exception as e:
            logger.error(f"Error getting historical prices for {epic}: {e}")
            return None

    async def create_position(self, epic: str, direction: str, size: float, stop_level: Optional[float] = None) -> Optional[Dict]:
        """Create a new position"""
        try:
            trade_direction = "BUY" if direction.lower() == "long" else "SELL"
            position = await self._run_sync(self.client.place_the_position, epic=epic, direction=trade_direction, size=size, stop_level=stop_level)
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

