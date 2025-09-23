import logging
from datetime import datetime, timedelta, time

import pytz

from bot.settings import TradingBotSettings

logger = logging.getLogger(__name__)

class MarketTimeManager:
    """Manages market timing and timezone conversions"""
    
    def __init__(self, settings: TradingBotSettings):
        self.settings = settings
        self.uae_tz = pytz.timezone(self.settings.get("TRADING_HOURS", "timezone", "Asia/Dubai"))
        self.market_tz = pytz.timezone(self.settings.get("TRADING_HOURS", "market_timezone", "US/Eastern"))
    
    def get_current_time_uae(self) -> datetime:
        """Get current time in UAE timezone"""
        return datetime.now(self.uae_tz)
    
    def get_current_time_market(self) -> datetime:
        """Get current time in market timezone"""
        return datetime.now(self.market_tz)
    
    def get_next_market_event(self, market_info: dict) -> dict:
        """Get next market open/close event using dynamic market hours from API"""
        try:
            current_market_time = self.get_current_time_market()
            today_weekday = current_market_time.strftime("%A").upper()

            market_times = market_info.get("instrument", {}).get("marketTimes", [])
            today_market_times = None
            for mt in market_times:
                if mt.get("day") == today_weekday:
                    today_market_times = mt
                    break

            if not today_market_times:
                # Fallback to assuming next weekday if today is not a trading day
                return self._get_next_open_event(current_market_time, market_times)

            open_time_str = today_market_times.get("openTime")
            close_time_str = today_market_times.get("closeTime")

            if not open_time_str or not close_time_str:
                return self._get_next_open_event(current_market_time, market_times)

            market_open = self.market_tz.localize(datetime.combine(current_market_time.date(), time.fromisoformat(open_time_str)))
            market_close = self.market_tz.localize(datetime.combine(current_market_time.date(), time.fromisoformat(close_time_str)))

            is_open = market_open <= current_market_time <= market_close

            if is_open:
                next_event = "close"
                next_time = market_close
            else:
                if current_market_time > market_close:
                    return self._get_next_open_event(current_market_time, market_times, days_to_add=1)
                else:
                    next_event = "open"
                    next_time = market_open

            time_until = (next_time - current_market_time).total_seconds()

            return {
                "is_open": is_open,
                "next_event": next_event,
                "next_time_market": next_time,
                "next_time_uae": next_time.astimezone(self.uae_tz),
                "time_until_seconds": max(0, time_until),
                "current_market_time": current_market_time,
                "current_uae_time": self.get_current_time_uae()
            }

        except Exception as e:
            logger.error(f"Error calculating market timing: {e}")
            return self._default_market_event()

    def _get_next_open_event(self, current_time, market_times, days_to_add=0):
        """Helper to find the next market opening time."""
        for i in range(days_to_add, 8):
            next_date = current_time.date() + timedelta(days=i)
            next_weekday = next_date.strftime("%A").upper()
            
            for mt in market_times:
                if mt.get("day") == next_weekday:
                    open_time_str = mt.get("openTime")
                    if open_time_str:
                        next_open_time = self.market_tz.localize(datetime.combine(next_date, time.fromisoformat(open_time_str)))
                        if next_open_time > current_time:
                            time_until = (next_open_time - current_time).total_seconds()
                            return {
                                "is_open": False,
                                "next_event": "open",
                                "next_time_market": next_open_time,
                                "next_time_uae": next_open_time.astimezone(self.uae_tz),
                                "time_until_seconds": max(0, time_until),
                                "current_market_time": current_time,
                                "current_uae_time": self.get_current_time_uae()
                            }
        return self._default_market_event()

    def _default_market_event(self):
        """Returns a default market event structure when data is unavailable."""
        return {
            "is_open": False,
            "next_event": "unknown",
            "time_until_seconds": 0,
            "current_market_time": self.get_current_time_market(),
            "current_uae_time": self.get_current_time_uae()
        }

