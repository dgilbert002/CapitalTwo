import asyncio
import logging
from datetime import datetime, timedelta

import pandas as pd
from capitalcom.client import ResolutionType

from bot.api import CapitalComAPI
from bot.database import DatabaseManager

logger = logging.getLogger(__name__)

class DataDownloader:
    """Downloads and stores historical candle data."""

    def __init__(self, api: CapitalComAPI, db_manager: DatabaseManager):
        self.api = api
        self.db_manager = db_manager

    async def download_and_store_candles(self, epic: str, resolution: ResolutionType, num_candles: int):
        """Downloads the latest candles and stores them in the database."""
        try:
            logger.info(f"Downloading {num_candles} {resolution.value} candles for {epic}...")
            
            # Skip if API not ready
            if not self.api or not hasattr(self.api, 'client') or not self.api.client:
                logger.warning("API client not ready for historical data download")
                return
                
            price_data = await self.api.get_historical_prices(epic, resolution, num_candles)

            if price_data and "prices" in price_data:
                candles = price_data["prices"]
                for candle in candles:
                    candle_data = {
                        "timestamp": candle["snapshotTimeUTC"],
                        "open": candle["openPrice"]["bid"],
                        "high": candle["highPrice"]["bid"],
                        "low": candle["lowPrice"]["bid"],
                        "close": candle["closePrice"]["bid"],
                        "volume": candle["lastTradedVolume"]
                    }
                    self.db_manager.store_candle(epic, candle_data)
                logger.info(f"Stored {len(candles)} new candles for {epic}.")
            else:
                logger.warning(f"No price data received for {epic}.")

        except Exception as e:
            logger.error(f"Error downloading or storing candle data: {e}")

    async def continuous_download(self, epic: str, resolution: ResolutionType, interval_seconds: int):
        """Continuously downloads data at a specified interval."""
        while True:
            await self.download_and_store_candles(epic, resolution, 100) # Download recent 100 candles
            await asyncio.sleep(interval_seconds)

