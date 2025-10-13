import asyncio
import json
import logging
import os
import signal
import base64
from datetime import datetime, timedelta

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response

from bot.trader import TradingBot
from bot.settings import TradingBotSettings
from log_manager import log_manager, setup_logging, set_log_level

def configure_logging():
    """Configure unified logging for app, API, and server into log.txt."""
    # Use the session-based log manager - starts in production mode (WARNING)
    logger = setup_logging("WARNING")
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    class ConsoleActionFilter(logging.Filter):
        """Only allow actionable messages to the console.

        Rules:
        - Always allow WARNING and above (failures, exceptions, disconnections)
        - Additionally allow INFO messages that match important trading milestones
          like market open/close, timer triggers, brains analysis, trade exec/close,
          and key P&L summaries.
        """
        KEYWORDS = (
            'MARKET OPEN', 'MARKET CLOSED', 'Market opening', 'Market closing',
            'T-30s', 'T-15s', 'Closing all positions',
            'BRAINS ANALYSIS COMPLETE', 'TRADE EXECUTED SUCCESSFULLY',
            'Trade logged to CSV', 'trade_closed', 'P&L', 'profit', 'loss'
        )

        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            try:
                if record.levelno >= logging.WARNING:
                    return True
                msg = record.getMessage()
                # Whitelist specific actionable INFO lines
                for kw in self.KEYWORDS:
                    if kw in msg:
                        return True
                return False
            except Exception:
                # Fail-open for safety on console
                return True

    # Apply the console filter to existing handlers
    root = logging.getLogger()
    
    # Find and update the stream handler with our filter
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.addFilter(ConsoleActionFilter())

    # Apply sane defaults to framework loggers:
    # - File: keep at INFO via root handler above
    # - Console: reduce access/info noise by raising level to WARNING
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = True

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# Helper: kill any process on the port (POSIX only)
def kill_port_if_posix(port: int) -> None:
    if os.name == 'posix':  # Unix/Linux/Mac
        try:
            pid_str = os.popen(f"lsof -t -i:{port}").read().strip()
            if pid_str:
                for pid in pid_str.split('\n'):
                    if pid:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.info(f"Killed process {pid} on port {port}")
        except Exception as e:
            logger.warning(f"Could not kill process on port {port}: {e}")

# Global state for GUI connection layer (always active)
class AppState:
    def __init__(self):
        self.settings = TradingBotSettings()
        self.api = None
        self.current_account = None
        self.market_info = {}
        self.market_event = {}
        self.positions = []
        self.trade_history = []
        self.historic_trades = []
        self.account_transactions = []
        self.is_connected = False
        self.bot = None  # Trading bot (starts stopped)
        self.update_task = None
        # Market state tracking
        self.last_market_state = None  # Track if market was open/closed
        self.last_market_check = None  # Last time we checked market info
        self.market_info_interval = 30  # Default 30 seconds

app_state = AppState()

@app.get("/")
async def get():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            html = f.read()
        return HTMLResponse(html)
    except Exception as e:
        logger.error(f"Error loading index.html: {e}")
        return HTMLResponse(f"<h1>Error loading page: {e}</h1>", status_code=500)

@app.get("/favicon.ico")
async def favicon():
    # Tiny 16x16 ICO (transparent) to avoid 404s
    ico_b64 = (
        "AAABAAEAEBAAAAEAIABoBAAAFgAAACgAAAAQAAAAIAAAAAEAGAAAAAAAAAAAABMLAAATCwAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
        "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"
    )
    try:
        return Response(base64.b64decode(ico_b64), media_type="image/x-icon")
    except Exception:
        return Response(status_code=204)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Create task for sending updates
    async def send_updates():
        try:
            countdown_timer = 0
            while True:
                # Calculate market event fresh each time for accurate countdown
                market_event = {}
                if app_state.market_info:
                    from bot.market_time import MarketTimeManager
                    mtm = MarketTimeManager(app_state.settings)
                    market_event = mtm.get_next_market_event(app_state.market_info)
                
                # Send full update every 5 seconds, countdown-only update otherwise
                if countdown_timer == 0:
                    # Full data update every 5 seconds
                    data = {
                        "bot_name": app_state.settings.get("BOT_CONFIG", "bot_name", "AI Trading Bot"),
                        "epic": app_state.settings.get("BOT_CONFIG", "epic", "TECL"),
                        "leverage": app_state.settings.getfloat("BOT_CONFIG", "leverage", 1.0),
                        "is_running": app_state.bot.is_running if app_state.bot else False,
                        "account": app_state.current_account,
                        "market_event": market_event,
                        "market_info": app_state.market_info,
                        "positions": app_state.positions,
                        "trade_history": app_state.bot.trade_history if app_state.bot else [],
                        "action_log": getattr(app_state.bot, 'action_log', []) if app_state.bot else [],
                        "historic_trades": app_state.historic_trades,
                        "account_transactions": app_state.account_transactions,
                        "stop_loss_type": app_state.settings.get("BOT_CONFIG", "stop_loss_type", "normal"),
                        "override_strategy_sl": app_state.settings.getboolean("BOT_CONFIG", "override_strategy_sl", False),
                        "environment": app_state.api.environment if app_state.api else "demo",
                        "is_connected": app_state.is_connected,
                        # Add strategy settings for UI to load on page refresh
                        "strategy_mode": app_state.settings.get("STRATEGY", "strategy_mode", "enhanced") if app_state.settings.has_section("STRATEGY") else "enhanced",
                        "enable_crash_protection": app_state.settings.getboolean("STRATEGY", "enable_crash_protection", True) if app_state.settings.has_section("STRATEGY") else True
                    }
                else:
                    # Countdown-only update (lightweight)
                    data = {
                        "countdown_only": True,
                        "market_event": market_event
                    }
                
                # Log what we're sending (first time only for debugging)
                if not hasattr(websocket_endpoint, '_logged'):
                    if app_state.current_account:
                        balance_info = app_state.current_account.get('balance', {})
                        logger.info(f"Account structure: accountName={app_state.current_account.get('accountName')}, balance_keys={list(balance_info.keys()) if balance_info else 'No balance'}")
                        if balance_info:
                            logger.info(f"Balance values: balance={balance_info.get('balance')}, available={balance_info.get('available')}, profitLoss={balance_info.get('profitLoss')}")
                    websocket_endpoint._logged = True
                
                # Convert datetime objects to strings for JSON serialization
                def serialize_datetime(obj):
                    if hasattr(obj, 'isoformat'):
                        return obj.isoformat()
                    return str(obj)
                
                await websocket.send_text(json.dumps(data, default=serialize_datetime))
                
                # Increment countdown timer and reset at 5
                countdown_timer = (countdown_timer + 1) % 5
                await asyncio.sleep(1)  # Send updates every 1 second for smooth countdown
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected in send_updates")
            return
        except ConnectionError:
            logger.info("Connection closed in send_updates")
            return
        except Exception as e:
            # Only log actual errors, not connection closures
            if "websocket.send" not in str(e) and "websocket.close" not in str(e):
                logger.error(f"Error in send_updates: {e}")
            return
    
    # Create task for receiving messages
    async def receive_messages():
        try:
            while True:
                message = await websocket.receive_json()
                command = message.get("command")
                
                if command == "fetch_trade_history":
                    # Fetch trade history on demand
                    if app_state.api:
                        try:
                            app_state.historic_trades = await app_state.api.get_trade_history(days=30)
                            logger.info(f"On-demand: Fetched {len(app_state.historic_trades)} historic trades")
                            await websocket.send_json({"type": "trade_history_updated", "count": len(app_state.historic_trades)})
                        except Exception as e:
                            logger.error(f"Error fetching trade history: {e}")
                            await websocket.send_json({"type": "error", "message": str(e)})
                
                elif command == "fetch_account_transactions":
                    # Fetch account transactions on demand
                    if app_state.api:
                        try:
                            from datetime import datetime, timedelta
                            to_date = datetime.utcnow()
                            from_date = to_date - timedelta(days=30)
                            
                            activities = await app_state.api.get_account_activity(
                                from_date=from_date.strftime('%Y-%m-%dT%H:%M:%S'),
                                to_date=to_date.strftime('%Y-%m-%dT%H:%M:%S')
                            )
                            app_state.account_transactions = activities
                            logger.info(f"On-demand: Fetched {len(activities)} account transactions")
                            await websocket.send_json({"type": "account_transactions_updated", "count": len(activities)})
                        except Exception as e:
                            logger.error(f"Error fetching account transactions: {e}")
                            await websocket.send_json({"type": "error", "message": str(e)})
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected in receive_messages")
            return
        except ConnectionError:
            logger.info("Connection closed in receive_messages")
            return
        except Exception as e:
            # Only log actual errors, not connection closures
            if "websocket" not in str(e).lower():
                logger.error(f"Error in receive_messages: {e}")
            return
    
    # Run both tasks concurrently
    send_task = None
    receive_task = None
    try:
        send_task = asyncio.create_task(send_updates())
        receive_task = asyncio.create_task(receive_messages())
        await asyncio.gather(send_task, receive_task, return_exceptions=True)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        if "websocket" not in str(e).lower():
            logger.error(f"WebSocket error: {e}")
    finally:
        # Clean up tasks
        if send_task and not send_task.done():
            send_task.cancel()
        if receive_task and not receive_task.done():
            receive_task.cancel()
        logger.debug("WebSocket connection closed")

async def keepalive_task():
    """Separate keepalive task that runs every 8 minutes"""
    keepalive_interval = app_state.settings.getint("TIMERS", "keepalive_minutes", fallback=8) * 60
    logger.info(f"Starting keepalive task (every {keepalive_interval}s)")
    
    last_auth_time = datetime.utcnow()
    auth_backoff = 1  # Start with 1 second backoff
    
    while True:
        try:
            await asyncio.sleep(keepalive_interval)
            
            if app_state.api and app_state.is_connected:
                try:
                    # Try keepalive
                    success = await app_state.api.keepalive()
                    if success:
                        logger.info("Keepalive successful")
                        auth_backoff = 1  # Reset backoff on success
                    else:
                        logger.warning("Keepalive failed, attempting re-authentication")
                        raise Exception("Keepalive failed")
                        
                except Exception as e:
                    # Check if it's a 401 error
                    if "401" in str(e) or "invalid.session" in str(e) or not success:
                        logger.warning(f"Session expired, re-authenticating (backoff: {auth_backoff}s)")
                        
                        # Wait with exponential backoff
                        await asyncio.sleep(auth_backoff)
                        auth_backoff = min(auth_backoff * 2, 60)  # Max 60 second backoff
                        
                        # Re-authenticate
                        try:
                            await app_state.api.authenticate()
                            app_state.is_connected = True
                            last_auth_time = datetime.utcnow()
                            logger.info("Re-authentication successful")
                            auth_backoff = 1  # Reset backoff
                            
                            # Fetch current account after re-auth
                            if app_state.api.current_account_id:
                                accounts = await app_state.api.get_accounts()
                                app_state.current_account = next(
                                    (a for a in accounts if a.get("accountId") == app_state.api.current_account_id),
                                    None
                                )
                        except Exception as auth_error:
                            logger.error(f"Re-authentication failed: {auth_error}")
                            app_state.is_connected = False
                    else:
                        logger.error(f"Keepalive error: {e}")
                        
        except Exception as e:
            logger.error(f"Error in keepalive task: {e}")
            await asyncio.sleep(30)  # Wait 30s before retrying on error

async def continuous_data_update():
    """Continuously update account and market data for GUI (independent of bot)"""
    logger.info("Starting continuous data updates")
    update_count = 0
    
    # Get timer settings
    market_open_interval = app_state.settings.getint("TIMERS", "positions_update_market_open_sec", fallback=5)
    market_closed_interval = app_state.settings.getint("TIMERS", "positions_update_market_closed_sec", fallback=10)
    
    while True:
        try:
            if app_state.api and app_state.is_connected:
                update_count += 1
                logger.info(f"Running data update #{update_count}")
                
                # Update account balances
                if app_state.current_account:
                    accounts = await app_state.api.get_accounts()
                    current_id = app_state.current_account.get("accountId")
                    updated = next((a for a in accounts if a.get("accountId") == current_id), None)
                    if updated:
                        app_state.current_account = updated
                        balance = updated.get('balance', {}).get('balance', 0)
                        logger.info(f"Account balance: ${balance}")
                
                # Update positions
                app_state.positions = await app_state.api.get_positions()
                logger.info(f"Found {len(app_state.positions)} open positions")
                if app_state.positions:
                    # Log first position to see structure
                    logger.info(f"Position fields: {list(app_state.positions[0].keys())}")
                    logger.info(f"First position: {app_state.positions[0]}")
                
                # Smart market info update - only when needed
                epic = app_state.settings.get("BOT_CONFIG", "epic", "TECL")
                market_info_interval = app_state.settings.getint("TIMERS", "market_info_update_sec", fallback=30)
                current_time = datetime.utcnow()
                
                should_update_market = False
                reason = ""
            
                # Check if it's time for regular update
                if app_state.last_market_check is None:
                    should_update_market = True
                    reason = "Initial market check"
                elif (current_time - app_state.last_market_check).total_seconds() >= market_info_interval:
                    should_update_market = True
                    reason = f"Regular update (every {market_info_interval}s)"
            
                # Always update if market state might have changed (near open/close times)
                if app_state.market_event:
                    time_until = app_state.market_event.get("time_until_seconds", float('inf'))
                    if 0 < time_until < 300:  # Within 5 minutes of market open/close
                        should_update_market = True
                        reason = "Near market state change"
                
                    # Also check for critical trading times (T-120s, T-30s, T-15s)
                    # These are used by the bot for trading decisions
                    next_event = app_state.market_event.get("next_event", "")
                    if next_event == "close" and app_state.market_event.get("is_open"):
                        # Market is open and will close soon
                        seconds_to_close = time_until
                        
                        # Check if we're at critical times (with 5s buffer for timing)
                        if 115 <= seconds_to_close <= 125:  # T-120s
                            should_update_market = True
                            reason = "T-120s: Market data refresh for analysis"
                        elif 25 <= seconds_to_close <= 35:  # T-30s
                            should_update_market = True
                            reason = "T-30s: Exit position timing"
                        elif 10 <= seconds_to_close <= 20:  # T-15s
                            should_update_market = True
                            reason = "T-15s: Entry position timing"
            
                if should_update_market:
                    market_data = await app_state.api.get_market_info(epic)
                    if market_data:
                        app_state.market_info = market_data
                        app_state.last_market_check = current_time
                        logger.info(f"Market data updated for {epic} - Reason: {reason}")
                
                    # Calculate market timing
                    from bot.market_time import MarketTimeManager
                    market_timer = MarketTimeManager(app_state.settings)
                    new_market_event = market_timer.get_next_market_event(market_data)
                
                    if new_market_event:
                        # Check if market state changed
                        current_state = new_market_event.get("is_open")
                        if app_state.last_market_state is not None and current_state != app_state.last_market_state:
                            # Market state changed!
                            if current_state:
                                logger.warning("MARKET OPENED - Switching to higher frequency updates")
                                # Could trigger additional actions here (e.g., refresh positions, check auth)
                                if app_state.api:
                                    # Ensure we're authenticated for market open
                                    try:
                                        await app_state.api.keepalive()
                                        logger.info("Verified authentication at market open")
                                    except:
                                        logger.warning("Keepalive failed at market open, will retry on next cycle")
                            else:
                                logger.warning("MARKET CLOSED - Switching to lower frequency updates")
                        
                        # Update state tracking
                        app_state.last_market_state = current_state
                        app_state.market_event = new_market_event
                        
                        # Log market status
                        status = "OPEN" if current_state else "CLOSED"
                        next_event = new_market_event.get("next_event", "unknown")
                        time_until = new_market_event.get("time_until_seconds", 0)
                        hours_until = time_until / 3600
                        logger.info(f"Market is {status}, next {next_event} in {hours_until:.1f} hours")
                    
                    # Trade history moved to on-demand (when tab clicked)
                    # app_state.historic_trades = await app_state.api.get_trade_history(days=30)
                    # logger.info(f"Found {len(app_state.historic_trades)} historic trades")
                    
                    # Account transactions moved to on-demand (when tab clicked)
                    # Will be fetched via WebSocket command when Account Transactions tab is activated
                    
                    # Keepalive moved to separate timer (every 8 minutes)
            else:
                logger.warning(f"Not updating - connected: {app_state.is_connected}, api: {app_state.api is not None}")
            
            # Determine update interval based on market state
            if app_state.market_event and app_state.market_event.get("is_open"):
                update_interval = market_open_interval
            else:
                update_interval = market_closed_interval
            
            await asyncio.sleep(update_interval)
        except Exception as e:
            logger.error(f"Data update error: {e}", exc_info=True)
            await asyncio.sleep(10)  # Wait 10s on error

@app.on_event("startup")
async def startup_event():
    logger.info("Starting app connection layer...")
    
    # Initialize API connection
    from bot.api import CapitalComAPI
    env = app_state.settings.get("API_CONFIG", "environment", "demo").lower()
    app_state.api = CapitalComAPI(app_state.settings, environment=env)
    
    if await app_state.api.authenticate():
        app_state.is_connected = True
        
        # Get accounts and select default
        accounts = await app_state.api.get_accounts()
        if accounts:
            # Try to restore last selected account for this environment
            saved_id = app_state.settings.get("ENV_ACCOUNTS", env, "") or app_state.settings.get("CREDENTIALS", "account_id", "")
            target = next((a for a in accounts if a.get("accountId") == saved_id), None) or accounts[0]
            
            if await app_state.api.switch_account(target.get("accountId")):
                app_state.current_account = target
                logger.info(f"Connected to {env} account: {target.get('accountName')}")
        
        # Start continuous data updates
        app_state.update_task = asyncio.create_task(continuous_data_update())
        
        # Start keepalive task
        app_state.keepalive_task = asyncio.create_task(keepalive_task())
    else:
        logger.error("Failed to connect to Capital.com API")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping app...")
    if app_state.update_task:
        app_state.update_task.cancel()
    if hasattr(app_state, 'keepalive_task') and app_state.keepalive_task:
        app_state.keepalive_task.cancel()
    if app_state.bot:
        app_state.bot.stop()
        app_state.bot.db_manager.close()

@app.get("/market/refresh/{epic}")
async def refresh_market_info(epic: str):
    """On-demand market info refresh for bid/ask prices"""
    if not app_state.api:
        return {"ok": False, "error": "Not connected"}
    
    try:
        market_data = await app_state.api.get_market_info(epic)
        if market_data:
            app_state.market_info = market_data
            app_state.last_market_check = datetime.utcnow()
            
            # Extract bid/ask for immediate use
            bid = market_data.get("snapshot", {}).get("bid")
            ask = market_data.get("snapshot", {}).get("offer")
            
            logger.info(f"On-demand market refresh for {epic} - Bid: {bid}, Ask: {ask}")
            return {
                "ok": True,
                "bid": bid,
                "ask": ask,
                "spread": ask - bid if bid and ask else None
            }
        else:
            return {"ok": False, "error": "No market data"}
    except Exception as e:
        logger.error(f"Error refreshing market info: {e}")
        return {"ok": False, "error": str(e)}

@app.post("/bot/start")
async def bot_start():
    if not app_state.bot:
        # Create bot instance
        from bot.trader import TradingBot
        app_state.bot = TradingBot(app_state.settings)
        # Share the existing API connection completely
        app_state.bot.api = app_state.api
        app_state.bot.api_connected = True  # Mark as already connected
        app_state.bot.current_account = app_state.current_account
    
    if not app_state.bot.is_running:
        logger.info("Bot start requested")
        if await app_state.bot.initialize():
            asyncio.create_task(app_state.bot.run())
            return {"ok": True, "status": "running"}
        return {"ok": False, "error": "init_failed"}
    return {"ok": True, "status": "running"}

@app.post("/bot/stop")
async def bot_stop():
    if app_state.bot and app_state.bot.is_running:
        logger.info("Bot stop requested")
        app_state.bot.stop()
        return {"ok": True, "status": "stopped"}
    return {"ok": True, "status": "stopped"}

@app.post("/bot/simulate")
async def bot_simulate():
    """Simulate market close for testing - works with or without bot running"""
    logger.info("Simulate market close requested")
    
    # If bot not initialized, create temporary instance for simulation
    if not app_state.bot:
        logger.info("Creating temporary bot instance for simulation")
        from bot.trader import TradingBot
        temp_bot = TradingBot(app_state.settings)
        
        # Initialize with existing API connection
        if app_state.api:
            temp_bot.api = app_state.api
            temp_bot.api_connected = True
            temp_bot.current_account = app_state.current_account
            
            # Fetch market info for the bot
            try:
                temp_bot.market_info = await temp_bot.api.get_market_info(temp_bot.epic)
            except Exception as e:
                logger.error(f"Failed to get market info for simulation: {e}")
                temp_bot.market_info = None
            
            # Run simulation
            result = await temp_bot.simulate_market_close()
            if isinstance(result, dict):
                return result
            return {"ok": bool(result), "error": None if result else "simulation_failed"}
        else:
            return {"ok": False, "error": "no_api_connection", "message": "No API connection available"}
    
    # Use existing bot
    if not app_state.bot.is_running:
        logger.info("Bot exists but not running - starting temporarily for simulation")
        
        # Ensure market info is fetched
        if not app_state.bot.market_info and app_state.bot.api:
            try:
                app_state.bot.market_info = await app_state.bot.api.get_market_info(app_state.bot.epic)
            except Exception as e:
                logger.error(f"Failed to get market info for simulation: {e}")
        
        # Temporarily mark as running for simulation
        app_state.bot.is_running = True
        result = await app_state.bot.simulate_market_close()
        app_state.bot.is_running = False
    else:
        # Bot is running normally
        result = await app_state.bot.simulate_market_close()
    
    if isinstance(result, dict):
        return result
    return {"ok": bool(result), "message": "Simulation complete" if result else None, "error": None if result else "simulation_failed"}

@app.post("/bot/speedtest")
async def bot_speed_test(days: int = 5):
    """Run speed test simulation with accelerated time for multiple days"""
    logger.info(f"Speed test requested for {days} days")
    
    # If bot not initialized, create temporary instance for speed test
    if not app_state.bot:
        logger.info("Creating temporary bot instance for speed test")
        from bot.trader import TradingBot
        temp_bot = TradingBot(app_state.settings)
        
        # Initialize with existing API connection
        if app_state.api:
            temp_bot.api = app_state.api
            temp_bot.api_connected = True
            temp_bot.current_account = app_state.current_account
            
            # Run speed test
            result = await temp_bot.simulate_speed_test(days)
            return result
        else:
            return {"ok": False, "error": "no_api_connection", "message": "No API connection available"}
    
    # Use existing bot
    if not app_state.bot.is_running:
        logger.info("Bot exists but not running - starting temporarily for speed test")
        # Temporarily mark as running for speed test
        app_state.bot.is_running = True
        result = await app_state.bot.simulate_speed_test(days)
        app_state.bot.is_running = False
    else:
        # Bot is running normally
        result = await app_state.bot.simulate_speed_test(days)
    
    return result

@app.post("/brains/preview")
async def brains_preview():
    """Run Brains analysis without trading and return the decision details."""
    try:
        # Ensure API and market info
        if not app_state.api:
            return {"ok": False, "error": "no_api_connection"}
        epic = app_state.settings.get("BOT_CONFIG", "epic", "TECL")
        market_info = await app_state.api.get_market_info(epic)
        if not market_info:
            return {"ok": False, "error": "no_market_info"}

        # Build candles DataFrame similar to bot path; ensure latest candles
        from bot.database import DatabaseManager
        from bot.data_downloader import DataDownloader
        from Brains.ai_system import HybridIntelligentSystem
        import pandas as pd
        db = DatabaseManager(app_state.settings.get('DATABASE', 'path', 'database.db'))
        # Attempt to top-up recent candles to ensure we have the previous closed 5m bar
        try:
            downloader = DataDownloader(app_state.api, db)
            await downloader.download_and_store_candles(epic, app_state.api.ResolutionType.MINUTE_5, 50)
        except Exception:
            pass
        candles = db.get_candles(epic, limit=200)
        if not candles or len(candles) < 50:
            return {"ok": False, "error": "insufficient_history"}

        df = pd.DataFrame(candles, columns=['epic', 'timestamp', 'open', 'high', 'low', 'close', 'volume'])
        if 'epic' in df.columns:
            df = df.drop(columns=['epic'])
        df = df.rename(columns={
            'open': 'openPrice',
            'high': 'highPrice',
            'low': 'lowPrice',
            'close': 'closePrice',
            'volume': 'lastTradedVolume'
        })
        df['timestamp'] = pd.to_datetime(df['timestamp'], utc=True)
        df = df.sort_values('timestamp').reset_index(drop=True)

        ai = HybridIntelligentSystem()
        
        # Load current strategy settings
        if app_state.settings.has_section('STRATEGY'):
            strategy_mode = app_state.settings.get('STRATEGY', 'strategy_mode', 'enhanced')
            
            # Handle Test6 modes
            if strategy_mode == 'test6_no_protection':
                ai.strategy_mode = 'test6'
                ai.enable_crash_protection = False
            elif strategy_mode == 'test6_with_protection':
                ai.strategy_mode = 'test6'
                ai.enable_crash_protection = True
            else:
                ai.strategy_mode = strategy_mode
                ai.enable_crash_protection = app_state.settings.getboolean('STRATEGY', 'enable_crash_protection', True)
            
            logger.info(f"Brain Preview using strategy: {strategy_mode}, Crash protection: {ai.enable_crash_protection}")
        
        df_for_ai = ai.calculate_technical_indicators(df.copy())
        latest_row = df_for_ai.iloc[-1]
        decision = ai.analyze_market_conditions(latest_row, df_for_ai, __import__('datetime').datetime.now())
        
        # Log the decision details
        logger.info(f"Brain Preview Result - Signal: {decision.get('signal', 'None')}, Confidence: {decision.get('confidence', 0):.1f}%, Trade: {decision.get('trade_signal', 'hold')}")

        # Prepare last candle (5m) summary
        # Display time in local timezone for UI consistency
        import pytz
        local_ts = latest_row['timestamp']
        try:
            local_ts = local_ts.tz_convert(pytz.timezone('UTC')).astimezone()
        except Exception:
            try:
                local_ts = local_ts.tz_localize('UTC').astimezone()
            except Exception:
                pass
        last_candle = {
            'timestamp': local_ts.isoformat() if hasattr(local_ts, 'isoformat') else str(local_ts),
            'open': float(latest_row.get('openPrice', latest_row.get('open', 0)) or 0),
            'high': float(latest_row.get('highPrice', latest_row.get('high', 0)) or 0),
            'low': float(latest_row.get('lowPrice', latest_row.get('low', 0)) or 0),
            'close': float(latest_row.get('closePrice', latest_row.get('close', 0)) or 0),
            'volume': float(latest_row.get('lastTradedVolume', latest_row.get('volume', 0)) or 0)
        }

        # Also compute sizing preview with dealing rules
        rules = market_info.get('dealingRules', {})
        snapshot = market_info.get('snapshot', {})
        bid = float(snapshot.get('bid', 0) or 0)
        offer = float(snapshot.get('offer', 0) or 0)
        direction = 'long' if decision.get('trade_signal') == 'buy' else ('short' if decision.get('trade_signal') == 'sell' else 'hold')
        entry_price = offer if direction == 'long' else (bid if direction == 'short' else 0)
        min_size = float(rules.get('minDealSize', {}).get('value', 0.1))
        max_size = float(rules.get('maxDealSize', {}).get('value', 3250))
        increment = float(rules.get('minSizeIncrement', {}).get('value', 0.1))

        # Get leverage from strategy if available
        strategy_leverage = decision.get('strategy_leverage', None)
        if strategy_leverage is not None:
            leverage = float(strategy_leverage)
            logger.info(f"Brain Preview: Using leverage {leverage} from strategy '{decision.get('strategy_used', 'N/A')}'")
        
        sizing = None
        if direction in ('long', 'short') and entry_price:
            # Use account available for preview if available
            available = 0.0
            if app_state.current_account and app_state.current_account.get('balance'):
                available = float(app_state.current_account['balance'].get('available', 0) or 0)
            invest_pct = app_state.settings.getfloat('BOT_CONFIG', 'investment_pct', 99) / 100
            leverage = app_state.settings.getfloat('BOT_CONFIG', 'leverage', 1)
            raw_contracts = (available * invest_pct * leverage) / entry_price
            # Clamp and floor to increment
            tsz = raw_contracts
            if tsz < min_size:
                tsz = min_size
            elif tsz > max_size:
                tsz = max_size
            tsz = (tsz // increment) * increment

            # Stop level preview using configured SL type
            sl_type = app_state.settings.get('BOT_CONFIG', 'stop_loss_type', 'normal')
            sl_pct = app_state.settings.getfloat('BOT_CONFIG', 'stop_loss_pct', 2) / 100
            if sl_type in ('normal', 'trailing'):
                stop_level = entry_price * (1 - sl_pct) if direction == 'long' else entry_price * (1 + sl_pct)
            else:
                # staggered: use first value if provided
                first_use = app_state.settings.get('BOT_CONFIG', 'sl_use', '0,1,2,4,6,8,10').split(',')[0]
                first_pct = float(first_use) / 100 if first_use and first_use != '0' else sl_pct
                stop_level = entry_price * (1 - first_pct) if direction == 'long' else entry_price * (1 + first_pct)

            sizing = {
                'available': available,
                'investment_pct': invest_pct,
                'leverage': leverage,
                'strategy_leverage': strategy_leverage,
                'leverage_source': 'strategy' if strategy_leverage is not None else 'settings',
                'entry_price': entry_price,
                'contracts': tsz,
                'min_size': min_size,
                'max_size': max_size,
                'increment': increment,
                'stop_level': stop_level,
                'sl_type': sl_type
            }

        # Convert numpy values to regular Python types
        import numpy as np
        
        def convert_numpy(obj):
            """Convert numpy types to Python native types"""
            if isinstance(obj, np.bool_):
                return bool(obj)
            elif isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            elif isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            return obj
        
        # Clean up the decision dictionary
        decision = convert_numpy(decision)
        fired_signals = decision.get('fired_signals', {})
        
        return {
            "ok": True, 
            "strategy_mode": strategy_mode if 'strategy_mode' in locals() else "enhanced",
            "crash_protection": bool(ai.enable_crash_protection),
            "decision": decision, 
            "sizing": sizing, 
            "market_info": market_info, 
            "last_candle": last_candle,
            "selected_strategy": decision.get('selected_strategy', 'N/A'),
            "fired_signals": fired_signals,
            "strategy_config": decision.get('strategy_config', None)
        }
    except Exception as e:
        logger.error(f"Brains preview error: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/account/preferences")
async def get_account_preferences():
    try:
        if not app_state.api:
            return {"ok": False, "error": "no_api_connection"}
        prefs = await app_state.api.get_account_preferences()
        return {"ok": prefs is not None, "preferences": prefs}
    except Exception as e:
        logger.error(f"Error fetching account preferences: {e}")
        return {"ok": False, "error": str(e)}

@app.post("/account/leverage")
async def set_account_leverage(payload: dict = Body(...)):
    try:
        if not app_state.api:
            return {"ok": False, "error": "no_api_connection"}
        category = (payload or {}).get("category", "")
        leverage_val = int((payload or {}).get("leverage", 0))
        hedging = (payload or {}).get("hedgingMode", None)
        if not category or leverage_val <= 0:
            return {"ok": False, "error": "invalid_params"}
        result = await app_state.api.update_account_leverage(category, leverage_val, hedging)
        return result
    except Exception as e:
        logger.error(f"Error updating account leverage: {e}")
        return {"ok": False, "error": str(e)}

@app.get("/config")
async def get_config():
    env = app_state.api.environment if app_state.api else "demo"
    selected = app_state.settings.get("ENV_ACCOUNTS", env, "") or app_state.settings.get("CREDENTIALS", "account_id", "")
    return {
        "environment": env,
        "selected_account_id": selected,
        "is_connected": app_state.is_connected
    }

@app.post("/api/log/level")
async def set_log_level_endpoint(payload: dict = Body(...)):
    """Toggle between debug (all logs) and production (errors/warnings only) mode"""
    try:
        debug_mode = payload.get('debug_mode', False)
        set_log_level(debug_mode)
        
        level = "DEBUG/INFO" if debug_mode else "ERROR/WARNING"
        logger.info(f"Log level changed to: {level}")
        
        return {"success": True, "message": f"Log level set to {level}"}
    except Exception as e:
        logger.error(f"Error setting log level: {e}")
        return {"success": False, "error": str(e)}

@app.get("/api/log/sessions")
async def get_log_sessions():
    """Get list of available log sessions"""
    try:
        sessions = log_manager.get_session_logs()
        return {"success": True, "sessions": sessions}
    except Exception as e:
        logger.error(f"Error getting log sessions: {e}")
        return {"success": False, "error": str(e)}

@app.post("/api/strategy/settings")
async def save_strategy_settings(payload: dict = Body(...)):
    """Save strategy mode settings - PROVEN $699K SYSTEM"""
    try:
        strategy_mode = payload.get('strategy_mode', 'enhanced')
        enable_crash_protection = payload.get('enable_crash_protection', True)
        
        # Update settings file
        app_state.settings.set_value('STRATEGY', 'strategy_mode', strategy_mode)
        app_state.settings.set_value('STRATEGY', 'enable_crash_protection', str(enable_crash_protection))
        app_state.settings.save()
        
        # Update bot's AI system
        if app_state.bot and app_state.bot.ai_system:
            app_state.bot.ai_system.strategy_mode = strategy_mode
            app_state.bot.ai_system.enable_crash_protection = enable_crash_protection
            logger.info(f"Strategy updated: {strategy_mode}, Crash protection: {enable_crash_protection}")
            
            # Log expected performance based on ACTUAL tested results
            if strategy_mode == 'all_signals' and enable_crash_protection:
                logger.info("Expected: $699,074 (57.2% WR, -96.9% DD) - PROVEN RESULT")
            elif strategy_mode == 'all_signals' and not enable_crash_protection:
                logger.info("WARNING: Expected: $376,004 (56.1% WR, -98.7% DD) - NO PROTECTION")
            elif strategy_mode == 'two_rsi_only' and enable_crash_protection:
                logger.info("Expected: $485,948 (59.6% WR, -33.9% DD) - LOWEST RISK")
            elif strategy_mode == 'two_rsi_only' and not enable_crash_protection:
                logger.info("WARNING: Expected: $348,803 (58.1% WR, -68.5% DD) - NO PROTECTION")
        
        return {"success": True, "message": "Strategy settings saved"}
    except Exception as e:
        logger.error(f"Error saving strategy settings: {e}")
        return {"success": False, "error": str(e)}

@app.post("/config/stoploss")
async def save_stoploss_settings(payload: dict = Body(...)):
    """Save stop loss configuration"""
    try:
        # Update settings
        app_state.settings.set_value('BOT_CONFIG', 'stop_loss_type', payload.get('stop_loss_type', 'normal'))
        app_state.settings.set_value('BOT_CONFIG', 'stop_loss_pct', payload.get('stop_loss_pct', '2.0'))
        app_state.settings.set_value('BOT_CONFIG', 'override_strategy_sl', str(payload.get('override_strategy_sl', False)))
        app_state.settings.set_value('BOT_CONFIG', 'sl_thresholds', payload.get('sl_thresholds', '5,10,15'))
        app_state.settings.set_value('BOT_CONFIG', 'sl_adjustments', payload.get('sl_adjustments', '2,5,8'))
        app_state.settings.set_value('BOT_CONFIG', 'sl_when_at', payload.get('sl_when_at', '2,4,5,7,10,12,15'))
        app_state.settings.set_value('BOT_CONFIG', 'sl_use', payload.get('sl_use', '0,1,2,4,6,8,10'))
        
        # Set use_trailing_sl based on type
        app_state.settings.set_value('BOT_CONFIG', 'use_trailing_sl', 
                                    str(payload.get('stop_loss_type') in ['trailing', 'staggered']))
        
        logger.info(f"Stop loss settings updated: {payload.get('stop_loss_type')}")
        return {"ok": True}
        
    except Exception as e:
        logger.error(f"Error saving stop loss settings: {e}")
        return {"ok": False, "error": str(e)}

@app.post("/config/environment")
async def set_environment(payload: dict = Body(...)):
    env = (payload or {}).get("environment", "demo").lower()
    if env not in ["demo", "live"]:
        return {"ok": False, "error": "invalid_environment"}
    
    app_state.settings.set_value("API_CONFIG", "environment", env)
    
    # Recreate API with new environment
    from bot.api import CapitalComAPI
    app_state.api = CapitalComAPI(app_state.settings, environment=env)
    
    logger.info(f"Environment changed to {env}; re-authenticating")
    
    if await app_state.api.authenticate():
        app_state.is_connected = True
        
        # Get accounts for new environment
        accounts = await app_state.api.get_accounts()
        
        # Try to restore saved account for this environment
        saved_id = app_state.settings.get("ENV_ACCOUNTS", env, "")
        target = next((a for a in accounts if a.get("accountId") == saved_id), None) or (accounts[0] if accounts else None)
        
        if target:
            await app_state.api.switch_account(target.get("accountId"))
            app_state.current_account = target
        
        return {"ok": True, "environment": env}
    else:
        app_state.is_connected = False
        return {"ok": False, "error": "auth_failed"}

@app.get("/accounts")
async def list_accounts():
    if not app_state.api:
        return {"accounts": []}
    accounts = await app_state.api.get_accounts()
    return {"accounts": [{"accountId": a.get("accountId"), "accountName": a.get("accountName")} for a in accounts]}

@app.post("/accounts/select")
async def select_account(payload: dict = Body(...)):
    account_id = (payload or {}).get("account_id")
    if not account_id:
        return {"ok": False, "error": "missing_account_id"}
    
    logger.info(f"Selecting account {account_id}")
    ok = await app_state.api.switch_account(account_id)
    
    if ok:
        # Save per-environment mapping
        app_state.settings.set_env_account(app_state.api.environment, account_id)
        
        # Update current account with full details
        accounts = await app_state.api.get_accounts()
        app_state.current_account = next((a for a in accounts if a.get("accountId") == account_id), {"accountId": account_id})
        
    return {"ok": ok}

if __name__ == "__main__":
    settings = TradingBotSettings()
    port = settings.getint("DISPLAY_CONFIG", "port", 8011)
    # Note: On Windows, we can't easily kill processes on a port
    # If port is in use, uvicorn will fail and user needs to restart manually
    kill_port_if_posix(port)

    uvicorn.run(app, host="0.0.0.0", port=port)
