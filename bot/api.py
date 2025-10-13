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
            if not self.client:
                logger.warning("Client not initialized, attempting to authenticate")
                if not await self.authenticate():
                    return []
            
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
            if not self.client:
                logger.warning("Client not initialized, attempting to authenticate")
                if not await self.authenticate():
                    return []
            
            positions_data = await self._run_sync(self.client.all_positions)
            return positions_data.get("positions", [])
        except Exception as e:
            logger.error(f"Error getting positions: {e}")
            return []

    async def get_market_info(self, epic: str) -> Optional[Dict]:
        """Get market information for an epic"""
        try:
            if not self.client:
                logger.warning("Client not initialized, attempting to authenticate")
                if not await self.authenticate():
                    return None
            
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
        """Get complete trade history with entry and exit details"""
        try:
            if not self.client:
                logger.warning("Client not initialized, attempting to authenticate")
                if not await self.authenticate():
                    return []
            
            # Use direct HTTP request to /history/transactions endpoint
            from datetime import datetime, timedelta
            import aiohttp
            
            to_date = datetime.utcnow()
            from_date = to_date - timedelta(days=days)
            
            # Format dates
            from_str = from_date.strftime('%Y-%m-%dT%H:%M:%S')
            to_str = to_date.strftime('%Y-%m-%dT%H:%M:%S')
            
            # Get base URL and build endpoint
            base_url = 'https://api-capital.backend-capital.com/api/v1'
            
            headers = {
                'X-SECURITY-TOKEN': self.client.x_security_token,
                'CST': self.client.cst,
                'Content-Type': 'application/json'
            }
            
            all_transactions = []
            
            async with aiohttp.ClientSession() as session:
                # Get ALL transactions (not just TRADE type) to see full lifecycle
                endpoint = f"/history/transactions?from={from_str}&to={to_str}"
                async with session.get(base_url + endpoint, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        all_transactions = data.get('transactions', [])
                        logger.info(f"Fetched {len(all_transactions)} total transactions")
                        
                        # Log transaction types found
                        transaction_types = set(t.get('transactionType', 'UNKNOWN') for t in all_transactions)
                        logger.info(f"Transaction types found: {transaction_types}")
                        
                # Also try to get activity history for more details
                activity_endpoint = f"/history/activity?fr={from_str}&to={to_str}&detailed=true"
                try:
                    async with session.get(base_url + activity_endpoint, headers=headers) as response:
                        if response.status == 200:
                            data = await response.json()
                            activities = data.get('activities', [])
                            logger.info(f"Fetched {len(activities)} activities")
                        else:
                            logger.warning(f"Activity endpoint returned {response.status}")
                            activities = []
                except:
                    activities = []
                    
            # Process transactions to build complete trade history
            trades = []
            trade_map = {}  # Map dealId to trade info
            
            # First pass - identify all trades
            for trans in all_transactions:
                if trans.get('transactionType') == 'TRADE':
                    deal_id = trans.get('dealId')
                    if deal_id:
                        if deal_id not in trade_map:
                            trade_map[deal_id] = {
                                'dealId': deal_id,
                                'epic': trans.get('instrumentName'),
                                'transactions': []
                            }
                        trade_map[deal_id]['transactions'].append(trans)
            
            # Build complete trade records
            for deal_id, trade_info in trade_map.items():
                transactions = trade_info['transactions']
                
                # For closed trades, we typically only get the closing transaction
                # We need to infer the entry details from the closing info
                for trans in transactions:
                    # The size in transaction is the P&L amount (negative for losses)
                    pnl = float(trans.get('size', 0))
                    
                    trade = {
                        'dealId': deal_id,
                        'epic': trans.get('instrumentName'),
                        'closeDate': trans.get('date'),
                        'closeDateUtc': trans.get('dateUtc'),
                        'pnl': pnl,  # The actual P&L
                        'currency': trans.get('currency', 'USD'),
                        'status': trans.get('status'),
                        'reference': trans.get('reference'),
                        'note': trans.get('note', ''),
                        # Direction based on P&L sign is unreliable
                        # We need to look this up from our records
                        'direction': None,
                        'size': None,
                        'entryDate': None,
                        'entryPrice': None,
                        'closePrice': None,
                        'closeReason': trans.get('note', 'Trade closed'),
                        'strategy': None
                    }
                    trades.append(trade)
                    
            # Sort by close date (newest first)
            trades.sort(key=lambda x: x.get('closeDateUtc', ''), reverse=True)
            
            # Try to enhance with data from our CSV file if it exists
            try:
                import csv
                import os
                
                csv_path = 'trade_history.csv'
                if os.path.exists(csv_path):
                    csv_trades = {}
                    with open(csv_path, 'r') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            deal_ref = row.get('deal_reference')
                            if deal_ref:
                                csv_trades[deal_ref] = row
                    
                    # Enhance trades with CSV data
                    for trade in trades:
                        deal_id = trade.get('dealId')
                        if deal_id and deal_id in csv_trades:
                            csv_data = csv_trades[deal_id]
                            trade['direction'] = csv_data.get('direction', trade.get('direction'))
                            trade['size'] = float(csv_data.get('size', 0)) if csv_data.get('size') else trade.get('size')
                            trade['entryPrice'] = float(csv_data.get('entry_price', 0)) if csv_data.get('entry_price') else None
                            trade['exitPrice'] = float(csv_data.get('exit_price', 0)) if csv_data.get('exit_price') else None
                            trade['strategy'] = csv_data.get('strategy_used', '-')
                            trade['entryDate'] = csv_data.get('timestamp')
                    
                    logger.info(f"Enhanced {len(csv_trades)} trades with CSV data")
            except Exception as e:
                logger.warning(f"Could not load trade history CSV: {e}")
            
            logger.info(f"Processed {len(trades)} complete trades")
            return trades
                        
        except Exception as e:
            logger.error(f"Error fetching trade history: {e}")
            return []
    
    async def get_account_activity(self, from_date: str = None, to_date: str = None, deal_id: str = None, epic: str = None) -> List[Dict]:
        """Get ALL account transactions/activities"""
        try:
            # Use direct HTTP request to get ALL transactions (not just trades)
            from datetime import datetime, timedelta
            import aiohttp
            
            if from_date and to_date:
                # Use provided dates
                from_str = from_date
                to_str = to_date
            else:
                # Default to last 7 days
                to_date = datetime.utcnow()
                from_date = to_date - timedelta(days=7)
                from_str = from_date.strftime('%Y-%m-%dT%H:%M:%S')
                to_str = to_date.strftime('%Y-%m-%dT%H:%M:%S')
            
            # Get base URL and build endpoint
            base_url = 'https://api-capital.backend-capital.com/api/v1'
            # Get ALL transactions, not filtered by type
            endpoint = f"/history/transactions?from={from_str}&to={to_str}"
            
            headers = {
                'X-SECURITY-TOKEN': self.client.x_security_token,
                'CST': self.client.cst,
                'Content-Type': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(base_url + endpoint, headers=headers) as response:
                    if response.status == 200:
                        data = await response.json()
                        transactions = data.get('transactions', [])
                        logger.info(f"Fetched {len(transactions)} total transactions")
                        
                        # Log all transaction types
                        if transactions:
                            types = set(t.get('transactionType', 'UNKNOWN') for t in transactions)
                            logger.info(f"Transaction types: {types}")
                        
                        # Sort by date (newest first)
                        transactions.sort(key=lambda x: x.get('dateUtc', x.get('dateUTC', '')), reverse=True)
                        
                        # If epic filter requested, apply it
                        if epic:
                            transactions = [t for t in transactions if t.get('instrumentName') == epic]
                            logger.info(f"Filtered to {len(transactions)} transactions for {epic}")
                        
                        return transactions
                    else:
                        logger.error(f"API error {response.status}: {await response.text()}")
                        return []
                        
        except Exception as e:
            logger.error(f"Error fetching account activity: {e}")
            return []

    # ===== Account preferences (hedging/leverage) =====
    async def get_account_preferences(self) -> Optional[Dict]:
        """Fetch account preferences including leverages per asset class."""
        try:
            if not hasattr(self.client, 'account_preferences'):
                logger.error("Client does not support account_preferences")
                return None
            prefs = await self._run_sync(self.client.account_preferences)
            return prefs
        except Exception as e:
            logger.error(f"Error getting account preferences: {e}")
            return None

    async def update_account_leverage(self, instrument_category: str, leverage_value: int, hedging_mode: Optional[bool] = None) -> Dict:
        """Update leverage for a specific instrument category.

        instrument_category should be one of: SHARES, CURRENCIES, INDICES, CRYPTOCURRENCIES, COMMODITIES
        """
        try:
            # Get current preferences to preserve other categories
            current = await self.get_account_preferences() or {}
            leverages = (current.get('leverages') or {}).copy()
            # Normalize key
            key = (instrument_category or '').upper()
            if not key:
                return {"ok": False, "error": "missing_instrument_category"}
            # Validate available values if provided by server
            available = []
            if key in leverages and isinstance(leverages[key], dict):
                available = leverages[key].get('available') or []
            # Build leverages payload as expected by API: { CATEGORY: value }
            leverages_payload = {k: (v.get('current') if isinstance(v, dict) else v) for k, v in leverages.items()}
            leverages_payload[key] = leverage_value

            mode = bool(current.get('hedgingMode')) if hedging_mode is None else bool(hedging_mode)

            if not hasattr(self.client, 'update_account_preferences'):
                return {"ok": False, "error": "client_missing_update_account_preferences"}

            result = await self._run_sync(self.client.update_account_preferences, mode, leverages_payload)
            logger.info(f"Update account leverage result: {result}")
            return {"ok": (result or {}).get('status') == 'SUCCESS', **(result or {})}
        except Exception as e:
            logger.error(f"Error updating account leverage: {e}")
            return {"ok": False, "error": str(e)}

