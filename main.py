import asyncio
import json
import logging
import os
import signal
import base64

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response

from bot.trader import TradingBot
from bot.settings import TradingBotSettings

def configure_logging():
    """Configure unified logging for app, API, and server into log.txt."""
    log_file = 'log.txt'
    
    # Truncate log file on startup for fresh logs
    with open(log_file, 'w') as f:
        f.write('')
    
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    root = logging.getLogger()
    root.setLevel(logging.INFO)

    # Avoid duplicate handlers if reloaded
    for h in list(root.handlers):
        root.removeHandler(h)

    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(logging.INFO)
    stream_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(stream_handler)

    # Also attach to uvicorn loggers so access/error go to the same file
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.INFO)
        lg.propagate = True

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

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
        self.is_connected = False
        self.bot = None  # Trading bot (starts stopped)
        self.update_task = None

app_state = AppState()

@app.get("/")
async def get():
    try:
        with open("static/index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(f.read())
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
    try:
        logger.info("WebSocket connected")
        while True:
            await asyncio.sleep(1) # Send updates every second
            
            # Calculate market event fresh each time for accurate countdown
            market_event = {}
            if app_state.market_info:
                from bot.market_time import MarketTimeManager
                mtm = MarketTimeManager(app_state.settings)
                market_event = mtm.get_next_market_event(app_state.market_info)
            
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
                "environment": app_state.api.environment if app_state.api else "demo",
                "is_connected": app_state.is_connected
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
            
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

async def continuous_data_update():
    """Continuously update account and market data for GUI (independent of bot)"""
    logger.info("Starting continuous data updates")
    update_count = 0
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
                
            # Update market info for configured epic
            epic = app_state.settings.get("BOT_CONFIG", "epic", "TECL")
            market_data = await app_state.api.get_market_info(epic)
            if market_data:
                app_state.market_info = market_data
                logger.info(f"Market data updated for {epic}")
                
                # Calculate market timing
                from bot.market_time import MarketTimeManager
                market_timer = MarketTimeManager(app_state.settings)
                app_state.market_event = market_timer.get_next_market_event(market_data)
                
                # Log market status
                if app_state.market_event:
                    status = "OPEN" if app_state.market_event.get("is_open") else "CLOSED"
                    next_event = app_state.market_event.get("next_event", "unknown")
                    time_until = app_state.market_event.get("time_until_seconds", 0)
                    hours_until = time_until / 3600
                    logger.info(f"Market is {status}, next {next_event} in {hours_until:.1f} hours")
                
                # Update trade history
                app_state.historic_trades = await app_state.api.get_trade_history(days=30)
                logger.info(f"Found {len(app_state.historic_trades)} historic trades")
                
                # Keepalive
                await app_state.api.keepalive()
            else:
                logger.warning(f"Not updating - connected: {app_state.is_connected}, api: {app_state.api is not None}")
            
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"Data update error: {e}", exc_info=True)
            await asyncio.sleep(5)

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
    else:
        logger.error("Failed to connect to Capital.com API")

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping app...")
    if app_state.update_task:
        app_state.update_task.cancel()
    if app_state.bot:
        app_state.bot.stop()
        app_state.bot.db_manager.close()

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

@app.get("/config")
async def get_config():
    env = app_state.api.environment if app_state.api else "demo"
    selected = app_state.settings.get("ENV_ACCOUNTS", env, "") or app_state.settings.get("CREDENTIALS", "account_id", "")
    return {
        "environment": env,
        "selected_account_id": selected,
        "is_connected": app_state.is_connected
    }

@app.post("/config/stoploss")
async def save_stoploss_settings(payload: dict = Body(...)):
    """Save stop loss configuration"""
    try:
        # Update settings
        app_state.settings.set_value('BOT_CONFIG', 'stop_loss_type', payload.get('stop_loss_type', 'normal'))
        app_state.settings.set_value('BOT_CONFIG', 'stop_loss_pct', payload.get('stop_loss_pct', '2.0'))
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

    uvicorn.run(app, host="0.0.0.0", port=port)
