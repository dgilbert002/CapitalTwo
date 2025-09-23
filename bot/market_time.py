import logging
from datetime import datetime, timedelta, time
from typing import Dict, Optional, Tuple

import pytz

from bot.settings import TradingBotSettings

logger = logging.getLogger(__name__)

class MarketTimeManager:
    """Manages market timing and timezone conversions - handles DST and date boundaries correctly"""
    
    def __init__(self, settings: TradingBotSettings):
        self.settings = settings
        # Dubai doesn't observe DST, always UTC+4
        self.uae_tz = pytz.timezone("Asia/Dubai")
        # Market times from API are in UTC
        self.utc_tz = pytz.UTC
        # Local system timezone
        self.local_tz = datetime.now().astimezone().tzinfo
    
    def get_current_time_uae(self) -> datetime:
        """Get current time in UAE timezone"""
        return datetime.now(self.uae_tz)
    
    def get_current_time_market(self) -> datetime:
        """Get current time in UTC (market times from API are in UTC)"""
        return datetime.now(self.utc_tz)
    
    def parse_market_hours(self, opening_hours: Dict, day_key: str) -> Optional[Tuple[time, time]]:
        """Parse market hours for a specific day"""
        times = opening_hours.get(day_key, [])
        if not times:
            return None
            
        # Handle different formats from API
        if isinstance(times, list) and len(times) > 0:
            time_range = times[0] if isinstance(times[0], str) else None
        elif isinstance(times, str):
            time_range = times
        else:
            return None
            
        if time_range and " - " in time_range:
            try:
                parts = time_range.split(" - ")
                open_time = datetime.strptime(parts[0].strip(), "%H:%M").time()
                close_time = datetime.strptime(parts[1].strip(), "%H:%M").time()
                return (open_time, close_time)
            except:
                logger.warning(f"Failed to parse time range: {time_range}")
                return None
        return None

    def get_next_market_event(self, market_info: dict) -> dict:
        """Get next market open/close event with proper timezone and DST handling"""
        try:
            # Current time in UTC (market hours from API are in UTC)
            now_utc = datetime.now(self.utc_tz)
            now_local = datetime.now(self.local_tz) if self.local_tz else datetime.now()
            now_dubai = now_utc.astimezone(self.uae_tz)
            
            # Get market status directly from API
            market_status = market_info.get("marketStatus", "")
            
            # Get opening hours from instrument data
            instrument = market_info.get("instrument", {})
            opening_hours = instrument.get("openingHours", {})
            
            if not opening_hours:
                logger.warning("No opening hours found in market info")
                # If market status says TRADEABLE, assume it's open
                is_open = market_status == "TRADEABLE"
                return {
                    "is_open": is_open,
                    "market_status": market_status,
                    "next_event": "close" if is_open else "open",
                    "time_until_seconds": 0,
                    "current_utc_time": now_utc,
                    "current_uae_time": now_dubai,
                    "current_local_time": now_local
                }
            
            # Map weekday to API format (3-letter lowercase)
            weekday_map = {
                0: "mon", 1: "tue", 2: "wed", 3: "thu", 
                4: "fri", 5: "sat", 6: "sun"
            }
            
            current_weekday = now_utc.weekday()
            current_session = None
            next_session = None
            
            # Check if we're currently in a trading session
            today_key = weekday_map[current_weekday]
            today_hours = self.parse_market_hours(opening_hours, today_key)
            
            if today_hours:
                open_time, close_time = today_hours
                
                # Create datetime objects for today's session in UTC
                today_open = now_utc.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0)
                today_close = now_utc.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)
                
                # Handle overnight sessions (close time < open time means it closes next day)
                if close_time <= open_time:
                    today_close = today_close + timedelta(days=1)
                
                # Check if we're in the current session
                if today_open <= now_utc < today_close:
                    current_session = {
                        "open": today_open,
                        "close": today_close,
                        "is_current": True
                    }
                elif now_utc < today_open:
                    # Session hasn't started yet today
                    next_session = {
                        "open": today_open,
                        "close": today_close,
                        "is_current": False
                    }
            
            # If no current session and no next session found yet, look for next trading day
            if not current_session and not next_session:
                for days_ahead in range(1, 8):  # Check next 7 days
                    future_date = now_utc + timedelta(days=days_ahead)
                    future_weekday = future_date.weekday()
                    future_key = weekday_map[future_weekday]
                    
                    future_hours = self.parse_market_hours(opening_hours, future_key)
                    if future_hours:
                        open_time, close_time = future_hours
                        
                        # Create datetime for future session
                        future_open = future_date.replace(hour=open_time.hour, minute=open_time.minute, second=0, microsecond=0)
                        future_close = future_date.replace(hour=close_time.hour, minute=close_time.minute, second=0, microsecond=0)
                        
                        # Handle overnight sessions
                        if close_time <= open_time:
                            future_close = future_close + timedelta(days=1)
                        
                        next_session = {
                            "open": future_open,
                            "close": future_close,
                            "is_current": False
                        }
                        break
            
            # Build response based on current/next session
            if current_session:
                # Market is currently open
                time_until_close = (current_session["close"] - now_utc).total_seconds()
                
                return {
                    "is_open": True,
                    "market_status": market_status or "OPEN",
                    "next_event": "close",
                    "next_event_time_utc": current_session["close"],
                    "next_event_time_dubai": current_session["close"].astimezone(self.uae_tz),
                    "next_event_time_local": current_session["close"].astimezone(self.local_tz) if self.local_tz else current_session["close"],
                    "time_until_seconds": max(0, time_until_close),
                    "current_utc_time": now_utc,
                    "current_uae_time": now_dubai,
                    "current_local_time": now_local,
                    "session_open_time": current_session["open"],
                    "session_close_time": current_session["close"]
                }
            elif next_session:
                # Market is closed, next session found
                time_until_open = (next_session["open"] - now_utc).total_seconds()
                
                return {
                    "is_open": False,
                    "market_status": market_status or "CLOSED",
                    "next_event": "open",
                    "next_event_time_utc": next_session["open"],
                    "next_event_time_dubai": next_session["open"].astimezone(self.uae_tz),
                    "next_event_time_local": next_session["open"].astimezone(self.local_tz) if self.local_tz else next_session["open"],
                    "time_until_seconds": max(0, time_until_open),
                    "current_utc_time": now_utc,
                    "current_uae_time": now_dubai,
                    "current_local_time": now_local,
                    "next_session_open": next_session["open"],
                    "next_session_close": next_session["close"]
                }
            else:
                # No sessions found (market might be on holiday)
                return {
                    "is_open": False,
                    "market_status": market_status or "CLOSED",
                    "next_event": "unknown",
                    "time_until_seconds": 0,
                    "current_utc_time": now_utc,
                    "current_uae_time": now_dubai,
                    "current_local_time": now_local,
                    "error": "No trading sessions found"
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

