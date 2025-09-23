import asyncio
import json
import logging
import os
import signal

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse

from bot.trader import TradingBot
from bot.settings import TradingBotSettings

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('trading_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

bot = TradingBot()

@app.get("/")
async def get():
    with open("static/index.html") as f:
        return HTMLResponse(f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            await asyncio.sleep(1) # Send updates every second
            
            market_event = bot.market_timer.get_next_market_event(bot.market_info)
            
            data = {
                "bot_name": bot.settings.get("BOT_CONFIG", "bot_name", "AI Trading Bot"),
                "epic": bot.settings.get("BOT_CONFIG", "epic", "TECL"),
                "leverage": bot.settings.getint("BOT_CONFIG", "leverage", 1),
                "is_running": bot.is_running,
                "account": bot.current_account,
                "market_event": market_event,
                "positions": bot.positions
            }
            
            # Convert datetime objects to strings for JSON serialization
            def serialize_datetime(obj):
                if hasattr(obj, 'isoformat'):
                    return obj.isoformat()
                return str(obj)
            
            await websocket.send_text(json.dumps(data, default=serialize_datetime))
            
    except WebSocketDisconnect:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")

@app.on_event("startup")
async def startup_event():
    logger.info("Starting trading bot...")
    if await bot.initialize():
        asyncio.create_task(bot.run())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping trading bot...")
    bot.stop()
    bot.db_manager.close()

if __name__ == "__main__":
    settings = TradingBotSettings()
    port = settings.getint("DISPLAY_CONFIG", "port", 8011)

    # Kill any process already using the port
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
