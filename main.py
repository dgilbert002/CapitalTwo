import asyncio
import json
import logging
import os
import signal
import sqlite3
import base64
from datetime import datetime, timedelta

import uvicorn
import pandas as pd
import pytz
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response

from bot.trader import TradingBot
from bot.settings import TradingBotSettings
from log_manager import log_manager, setup_logging, set_log_level


def configure_logging():
    """Configure unified logging for app, API, and server into log.txt."""
    # Use the session-based log manager - starts in production mode (WARNING)
    setup_logging("WARNING")

    class ConsoleActionFilter(logging.Filter):
        """Only allow actionable messages to the console.

        Rules:
        - Always allow WARNING and above (failures, exceptions, disconnections)
        - Additionally allow INFO messages that match important trading milestones
          like market open/close, timer triggers, brains analysis, trade exec/close,
          and key P&L summaries.
        """

        KEYWORDS = (
            "MARKET OPEN",
            "MARKET CLOSED",
            "Market opening",
            "Market closing",
            "T-30s",
            "T-15s",
            "Closing all positions",
            "BRAINS ANALYSIS COMPLETE",
            "TRADE EXECUTED SUCCESSFULLY",
            "Trade logged to CSV",
            "trade_closed",
            "P&L",
            "profit",
            "loss",
        )

        def filter(self, record: logging.LogRecord) -> bool:  # type: ignore[override]
            try:
                if record.levelno >= logging.WARNING:
                    return True
                msg = record.getMessage()
                for kw in self.KEYWORDS:
                    if kw in msg:
                        return True
                return False
            except Exception:
                return True

    root = logging.getLogger()
    for handler in root.handlers:
        if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
            handler.addFilter(ConsoleActionFilter())

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access", "fastapi"):
        lg = logging.getLogger(name)
        lg.setLevel(logging.WARNING)
        lg.propagate = True


configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")


def kill_port_if_posix(port: int) -> None:
    if os.name == "posix":
        try:
            pid_str = os.popen(f"lsof -t -i:{port}").read().strip()
            if pid_str:
                for pid in pid_str.split("\n"):
                    if pid:
                        os.kill(int(pid), signal.SIGKILL)
                        logger.info(f"Killed process {pid} on port {port}")
        except Exception as exc:
            logger.warning(f"Could not kill process on port {port}: {exc}")


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
        self.bot: TradingBot | None = None
        self.update_task: asyncio.Task | None = None
        self.keepalive_task: asyncio.Task | None = None
        self.last_market_state = None
        self.last_market_check = None
        self.market_info_interval = 30
        self.data_source = ""
        self.action_log = []


app_state = AppState()


@app.get("/")
async def get():
    try:
        with open("static/index.html", "r", encoding="utf-8") as fh:
            return HTMLResponse(fh.read())
    except Exception as exc:
        logger.error(f"Error loading index.html: {exc}")
        return HTMLResponse(f"<h1>Error loading page: {exc}</h1>", status_code=500)


@app.get("/favicon.ico")
async def favicon():
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

    async def send_updates():
        try:
            countdown_timer = 0
            while True:
                full_update_interval = app_state.settings.getint(
                    "TIMERS", "websocket_update_sec", 5
                )
                if full_update_interval <= 0:
                    full_update_interval = 1

                market_event = {}
                if app_state.market_info:
                    from bot.market_time import MarketTimeManager

                    mtm = MarketTimeManager(app_state.settings)
                    market_event = mtm.get_next_market_event(app_state.market_info)

                if countdown_timer == 0:
                    bot_instance = app_state.bot
                    epic_value = (
                        getattr(bot_instance, "epic", None)
                        if bot_instance and getattr(bot_instance, "epic", None)
                        else app_state.settings.get("BOT_CONFIG", "epic", "TECL")
                    )
                    leverage_value = (
                        getattr(bot_instance.ai_system, "strategy_leverage", None)
                        if bot_instance and getattr(bot_instance, "ai_system", None)
                        else None
                    )
                    if leverage_value is None:
                        leverage_value = app_state.settings.getfloat("BOT_CONFIG", "leverage", 1.0)

                    override_flag = app_state.settings.getboolean("MARKET_HOURS", "use_override", False)
                    override_epic = app_state.settings.get("MARKET_HOURS", "override_epic", "")

                    data = {
                        "bot_name": app_state.settings.get("BOT_CONFIG", "bot_name", "AI Trading Bot"),
                        "epic": epic_value,
                        "leverage": leverage_value,
                        "is_running": bot_instance.is_running if bot_instance else False,
                        "account": app_state.current_account,
                        "market_event": market_event,
                        "market_info": app_state.market_info,
                        "strategy_metadata": getattr(bot_instance.ai_system, "last_strategy_metadata", None)
                        if bot_instance and getattr(bot_instance, "ai_system", None)
                        else None,
                        "positions": app_state.positions,
                        "trade_history": bot_instance.trade_history if bot_instance else [],
                        "action_log": getattr(bot_instance, "action_log", []) if bot_instance else [],
                        "historic_trades": app_state.historic_trades,
                        "account_transactions": app_state.account_transactions,
                        "stop_loss_type": app_state.settings.get("BOT_CONFIG", "stop_loss_type", "normal"),
                        "override_strategy_sl": app_state.settings.getboolean("BOT_CONFIG", "override_strategy_sl", False),
                        "environment": app_state.api.environment if app_state.api else "demo",
                        "is_connected": app_state.is_connected,
                        "strategy_mode": app_state.settings.get("STRATEGY", "strategy_mode", "enhanced")
                        if app_state.settings.has_section("STRATEGY")
                        else "enhanced",
                        "enable_crash_protection": app_state.settings.getboolean(
                            "STRATEGY", "enable_crash_protection", True
                        )
                        if app_state.settings.has_section("STRATEGY")
                        else True,
                        "data_source": app_state.data_source,
                        "market_hours_override": {
                            "enabled": override_flag,
                            "epic": override_epic,
                        },
                    }
                else:
                    data = {"countdown_only": True, "market_event": market_event}

                if not hasattr(websocket_endpoint, "_logged") and data.get("account"):
                    balance_info = data["account"].get("balance", {})
                    logger.info(
                        "Account structure: accountName=%s, balance_keys=%s",
                        data["account"].get("accountName"),
                        list(balance_info.keys()) if balance_info else "No balance",
                    )
                    if balance_info:
                        logger.info(
                            "Balance values: balance=%s, available=%s, profitLoss=%s",
                            balance_info.get("balance"),
                            balance_info.get("available"),
                            balance_info.get("profitLoss"),
                        )
                    websocket_endpoint._logged = True

                def serialize_datetime(obj):
                    if hasattr(obj, "isoformat"):
                        return obj.isoformat()
                    return str(obj)

                await websocket.send_text(json.dumps(data, default=serialize_datetime))
                countdown_timer = (countdown_timer + 1) % full_update_interval
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected in send_updates")
        except ConnectionError:
            logger.info("Connection closed in send_updates")
        except Exception as exc:
            if "websocket" not in str(exc).lower():
                logger.error(f"Error in send_updates: {exc}")

    async def receive_messages():
        try:
            while True:
                message = await websocket.receive_json()
                command = message.get("command")

                if command == "fetch_trade_history" and app_state.api:
                    try:
                        app_state.historic_trades = await app_state.api.get_trade_history(days=30)
                        logger.info(
                            "On-demand: Fetched %s historic trades",
                            len(app_state.historic_trades),
                        )
                        await websocket.send_json(
                            {"type": "trade_history_updated", "count": len(app_state.historic_trades)}
                        )
                    except Exception as exc:
                        logger.error(f"Error fetching trade history: {exc}")
                        await websocket.send_json({"type": "error", "message": str(exc)})

                elif command == "fetch_account_transactions" and app_state.api:
                    try:
                        to_date = datetime.utcnow()
                        from_date = to_date - timedelta(days=30)
                        activities = await app_state.api.get_account_activity(
                            from_date=from_date.strftime("%Y-%m-%dT%H:%M:%S"),
                            to_date=to_date.strftime("%Y-%m-%dT%H:%M:%S"),
                        )
                        app_state.account_transactions = activities
                        logger.info(
                            "On-demand: Fetched %s account transactions", len(activities)
                        )
                        await websocket.send_json(
                            {"type": "account_transactions_updated", "count": len(activities)}
                        )
                    except Exception as exc:
                        logger.error(f"Error fetching account transactions: {exc}")
                        await websocket.send_json({"type": "error", "message": str(exc)})
        except WebSocketDisconnect:
            logger.info("WebSocket disconnected in receive_messages")
        except ConnectionError:
            logger.info("Connection closed in receive_messages")
        except Exception as exc:
            if "websocket" not in str(exc).lower():
                logger.error(f"Error in receive_messages: {exc}")

    send_task = receive_task = None
    try:
        send_task = asyncio.create_task(send_updates())
        receive_task = asyncio.create_task(receive_messages())
        await asyncio.gather(send_task, receive_task, return_exceptions=True)
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as exc:
        if "websocket" not in str(exc).lower():
            logger.error(f"WebSocket error: {exc}")
    finally:
        if send_task and not send_task.done():
            send_task.cancel()
        if receive_task and not receive_task.done():
            receive_task.cancel()
        logger.debug("WebSocket connection closed")


async def keepalive_task():
    keepalive_interval = app_state.settings.getint("TIMERS", "keepalive_minutes", fallback=8) * 60
    logger.info("Starting keepalive task (every %ss)", keepalive_interval)

    auth_backoff = 1
    while True:
        try:
            await asyncio.sleep(keepalive_interval)
            if app_state.api and app_state.is_connected:
                try:
                    success = await app_state.api.keepalive()
                    if success:
                        logger.info("Keepalive successful")
                        auth_backoff = 1
                    else:
                        logger.warning("Keepalive failed, attempting re-authentication")
                        raise Exception("Keepalive failed")
                except Exception as exc:
                    if "401" in str(exc) or "invalid.session" in str(exc):
                        logger.warning("Session expired, re-authenticating (backoff: %ss)", auth_backoff)
                        await asyncio.sleep(auth_backoff)
                        auth_backoff = min(auth_backoff * 2, 60)
                        try:
                            await app_state.api.authenticate()
                            app_state.is_connected = True
                            auth_backoff = 1
                            if app_state.api.current_account_id:
                                accounts = await app_state.api.get_accounts()
                                app_state.current_account = next(
                                    (
                                        acc
                                        for acc in accounts
                                        if acc.get("accountId") == app_state.api.current_account_id
                                    ),
                                    None,
                                )
                        except Exception as auth_error:
                            logger.error(f"Re-authentication failed: {auth_error}")
                            app_state.is_connected = False
                    else:
                        logger.error(f"Keepalive error: {exc}")
        except Exception as exc:
            logger.error(f"Error in keepalive task: {exc}")
            await asyncio.sleep(30)


async def continuous_data_update():
    logger.info("Starting continuous data updates")
    update_count = 0
    market_open_interval = app_state.settings.getint(
        "TIMERS", "positions_update_market_open_sec", fallback=5
    )
    market_closed_interval = app_state.settings.getint(
        "TIMERS", "positions_update_market_closed_sec", fallback=10
    )

    while True:
        try:
            if app_state.api and app_state.is_connected:
                update_count += 1
                logger.info("Running data update #%s", update_count)

                if app_state.current_account:
                    market_event = app_state.market_event or {}
                    is_market_open = market_event.get("is_open", False)
                    account_interval = (
                        app_state.settings.getint("TIMERS", "accounts_update_market_open_sec", 5)
                        if is_market_open
                        else app_state.settings.getint("TIMERS", "accounts_update_market_closed_sec", 10)
                    )
                    if not hasattr(app_state, "_last_account_update") or (
                        datetime.utcnow() - app_state._last_account_update
                    ).total_seconds() > account_interval:
                        accounts = await app_state.api.get_accounts()
                        current_id = app_state.current_account.get("accountId")
                        updated = next(
                            (acc for acc in accounts if acc.get("accountId") == current_id),
                            None,
                        )
                        if updated:
                            app_state.current_account = updated
                            app_state._last_account_update = datetime.utcnow()
                        else:
                            logger.warning("Could not find account %s in accounts list", current_id)

                app_state.positions = await app_state.api.get_positions()
                logger.debug(
                    "Found %s open positions",
                    len(app_state.positions) if app_state.positions else 0,
                )

                epic = app_state.settings.get("BOT_CONFIG", "epic", "TECL")
                market_info_interval = app_state.settings.getint(
                    "TIMERS", "market_info_update_sec", fallback=30
                )
                current_time = datetime.utcnow()
                should_update_market = False
                reason = ""

                if app_state.last_market_check is None:
                    should_update_market = True
                    reason = "Initial market check"
                elif (
                    current_time - app_state.last_market_check
                ).total_seconds() >= market_info_interval:
                    should_update_market = True
                    reason = f"Regular update (every {market_info_interval}s)"

                market_event = app_state.market_event or {}
                if market_event:
                    time_until = market_event.get("time_until_seconds", float("inf"))
                    if 0 < time_until < 300:
                        should_update_market = True
                        reason = "Near market state change"

                    next_event = market_event.get("next_event", "")
                    if next_event == "close" and market_event.get("is_open"):
                        if 115 <= time_until <= 125:
                            should_update_market = True
                            reason = "T-120s: Market data refresh for analysis"
                        elif 25 <= time_until <= 35:
                            should_update_market = True
                            reason = "T-30s: Exit position timing"
                        elif 10 <= time_until <= 20:
                            should_update_market = True
                            reason = "T-15s: Entry position timing"

                if should_update_market:
                    override_enabled = app_state.settings.getboolean("MARKET_HOURS", "use_override", False)
                    override_epic = app_state.settings.get("MARKET_HOURS", "override_epic", "")
                    override_hours = None

                    if override_enabled and override_epic:
                        try:
                            override_market_data = await app_state.api.get_market_info(override_epic)
                            instrument = (override_market_data or {}).get("instrument", {})
                            override_hours = instrument.get("openingHours")
                            if override_hours:
                                logger.info(
                                    "Using override market hours from %s for countdowns",
                                    override_epic,
                                )
                        except Exception as exc:
                            logger.warning(
                                "Failed to fetch override market hours for %s: %s",
                                override_epic,
                                exc,
                            )
                            override_hours = None

                    market_data = await app_state.api.get_market_info(epic)
                    if market_data:
                        if override_hours:
                            market_data = dict(market_data)
                            instrument = dict(market_data.get("instrument", {}))
                            instrument["openingHours"] = override_hours
                            market_data["instrument"] = instrument

                        app_state.market_info = market_data
                        app_state.last_market_check = current_time
                        logger.info("Market data updated for %s - Reason: %s", epic, reason)

                    from bot.market_time import MarketTimeManager

                    market_timer = MarketTimeManager(app_state.settings)
                    new_market_event = market_timer.get_next_market_event(market_data)
                    if new_market_event:
                        current_state = new_market_event.get("is_open")
                        if (
                            app_state.last_market_state is not None
                            and current_state != app_state.last_market_state
                        ):
                            if current_state:
                                logger.warning("MARKET OPENED - Switching to higher frequency updates")
                                if app_state.api:
                                    try:
                                        await app_state.api.keepalive()
                                        logger.warning("MARKET OPENED - Verified authentication")
                                    except Exception:
                                        logger.warning(
                                            "Keepalive failed at market open, will retry on next cycle"
                                        )
                            else:
                                logger.warning("MARKET CLOSED - Switching to lower frequency updates")

                        app_state.last_market_state = current_state
                        app_state.market_event = new_market_event
                        status = "OPEN" if current_state else "CLOSED"
                        next_event = new_market_event.get("next_event", "unknown")
                        time_until = new_market_event.get("time_until_seconds", 0)
                        hours_until = time_until / 3600
                        logger.info(
                            "Market is %s, next %s in %.1f hours", status, next_event, hours_until
                        )
            else:
                logger.warning(
                    "Not updating - connected: %s, api: %s",
                    app_state.is_connected,
                    app_state.api is not None,
                )

            update_interval = (
                market_open_interval
                if app_state.market_event and app_state.market_event.get("is_open")
                else market_closed_interval
            )
            await asyncio.sleep(update_interval)
        except Exception as exc:
            logger.error("Data update error: %s", exc, exc_info=True)
            await asyncio.sleep(10)


@app.on_event("startup")
async def startup_event():
    logger.info("Starting app connection layer...")
    from bot.api import CapitalComAPI

    env = app_state.settings.get("API_CONFIG", "environment", "demo").lower()
    app_state.api = CapitalComAPI(app_state.settings, environment=env)

    if await app_state.api.authenticate():
        app_state.is_connected = True
        accounts = await app_state.api.get_accounts()
        if accounts:
            saved_id = app_state.settings.get("ENV_ACCOUNTS", env, "") or app_state.settings.get(
                "CREDENTIALS", "account_id", ""
            )
            target = next((acc for acc in accounts if acc.get("accountId") == saved_id), None) or accounts[0]
            if await app_state.api.switch_account(target.get("accountId")):
                app_state.current_account = target
                logger.info("Connected to %s account: %s", env, target.get("accountName"))

        app_state.update_task = asyncio.create_task(continuous_data_update())
        app_state.keepalive_task = asyncio.create_task(keepalive_task())
    else:
        logger.error("Failed to connect to Capital.com API")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Stopping app...")
    if app_state.update_task:
        app_state.update_task.cancel()
    if app_state.keepalive_task:
        app_state.keepalive_task.cancel()
    if app_state.bot:
        app_state.bot.stop()
        app_state.bot.db_manager.close()


@app.get("/market/refresh/{epic}")
async def refresh_market_info(epic: str):
    if not app_state.api:
        return {"ok": False, "error": "Not connected"}
    try:
        market_data = await app_state.api.get_market_info(epic)
        if market_data:
            app_state.market_info = market_data
            app_state.last_market_check = datetime.utcnow()
            bid = market_data.get("snapshot", {}).get("bid")
            ask = market_data.get("snapshot", {}).get("offer")
            logger.info("On-demand market refresh for %s - Bid: %s, Ask: %s", epic, bid, ask)
            return {
                "ok": True,
                "bid": bid,
                "ask": ask,
                "spread": ask - bid if bid and ask else None,
            }
        return {"ok": False, "error": "No market data"}
    except Exception as exc:
        logger.error(f"Error refreshing market info: {exc}")
        return {"ok": False, "error": str(exc)}


@app.post("/bot/start")
async def bot_start():
    if not app_state.bot:
        app_state.bot = TradingBot(app_state.settings)
        app_state.bot.api = app_state.api
        app_state.bot.api_connected = True
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
    logger.info("Simulate market close requested")
    if not app_state.bot:
        logger.info("Creating temporary bot instance for simulation")
        temp_bot = TradingBot(app_state.settings)
        if app_state.api:
            temp_bot.api = app_state.api
            temp_bot.api_connected = True
            temp_bot.current_account = app_state.current_account
            try:
                temp_bot.market_info = await temp_bot.api.get_market_info(temp_bot.epic)
            except Exception as exc:
                logger.error(f"Failed to get market info for simulation: {exc}")
                temp_bot.market_info = None
            result = await temp_bot.simulate_market_close()
            if isinstance(result, dict):
                return result
            return {"ok": bool(result), "error": None if result else "simulation_failed"}
        return {"ok": False, "error": "no_api_connection", "message": "No API connection available"}

    if not app_state.bot.is_running:
        logger.info("Bot exists but not running - starting temporarily for simulation")
        if not app_state.bot.market_info and app_state.bot.api:
            try:
                app_state.bot.market_info = await app_state.bot.api.get_market_info(app_state.bot.epic)
            except Exception as exc:
                logger.error(f"Failed to get market info for simulation: {exc}")
        app_state.bot.is_running = True
        result = await app_state.bot.simulate_market_close()
        app_state.bot.is_running = False
    else:
        result = await app_state.bot.simulate_market_close()

    if isinstance(result, dict):
        return result
    return {
        "ok": bool(result),
        "message": "Simulation complete" if result else None,
        "error": None if result else "simulation_failed",
    }


@app.post("/bot/speedtest")
async def bot_speed_test(days: int = 5):
    logger.info("Speed test requested for %s days", days)
    if not app_state.bot:
        logger.info("Creating temporary bot instance for speed test")
        temp_bot = TradingBot(app_state.settings)
        if app_state.api:
            temp_bot.api = app_state.api
            temp_bot.api_connected = True
            temp_bot.current_account = app_state.current_account
            result = await temp_bot.simulate_speed_test(days)
            return result
        return {"ok": False, "error": "no_api_connection", "message": "No API connection available"}

    if not app_state.bot.is_running:
        logger.info("Bot exists but not running - starting temporarily for speed test")
        app_state.bot.is_running = True
        result = await app_state.bot.simulate_speed_test(days)
        app_state.bot.is_running = False
    else:
        result = await app_state.bot.simulate_speed_test(days)
    return result


@app.post("/brains/preview")
async def brains_preview():
    try:
        if not app_state.api:
            return {"ok": False, "error": "no_api_connection"}
        epic = app_state.settings.get("BOT_CONFIG", "epic", "TECL")
        market_info = await app_state.api.get_market_info(epic)
        if not market_info:
            return {"ok": False, "error": "no_market_info"}

        bot_instance = app_state.bot
        if bot_instance:
            await bot_instance.refresh_alpha_vantage_data()
            df = bot_instance._load_alpha_vantage_dataframe(limit=500, include_gap_fill=True)
        else:
            temp_bot = TradingBot(app_state.settings)
            temp_bot.api = app_state.api
            temp_bot.api_connected = True
            await temp_bot.refresh_alpha_vantage_data(force_refresh=True)
            df = temp_bot._load_alpha_vantage_dataframe(limit=500, include_gap_fill=True)
            bot_instance = temp_bot

        if df is None or len(df) < 50:
            return {"ok": False, "error": "insufficient_history"}

        from Brains.ai_system import HybridIntelligentSystem

        ai = HybridIntelligentSystem()
        if app_state.settings.has_section("STRATEGY"):
            strategy_mode = app_state.settings.get("STRATEGY", "strategy_mode", "enhanced")
            if strategy_mode == "test6_no_protection":
                ai.strategy_mode = "test6"
                ai.enable_crash_protection = False
            elif strategy_mode == "test6_with_protection":
                ai.strategy_mode = "test6"
                ai.enable_crash_protection = True
            else:
                ai.strategy_mode = strategy_mode
                ai.enable_crash_protection = app_state.settings.getboolean(
                    "STRATEGY", "enable_crash_protection", True
                )
            logger.info(
                "Brain Preview using strategy: %s, Crash protection: %s",
                strategy_mode,
                ai.enable_crash_protection,
            )

        df_for_ai = ai.calculate_technical_indicators(df.copy())
        latest_row = df_for_ai.iloc[-1]
        decision = ai.analyze_market_conditions(latest_row, df_for_ai, datetime.now())
        logger.info(
            "Brain Preview Result - Signal: %s, Confidence: %.1f%%, Trade: %s",
            decision.get("signal", "None"),
            decision.get("confidence", 0),
            decision.get("trade_signal", "hold"),
        )

        local_ts = latest_row["timestamp"]
        try:
            local_ts = local_ts.tz_convert(pytz.timezone("UTC")).astimezone()
        except Exception:
            try:
                local_ts = local_ts.tz_localize("UTC").astimezone()
            except Exception:
                pass
        last_candle = {
            "timestamp": local_ts.isoformat() if hasattr(local_ts, "isoformat") else str(local_ts),
            "open": float(latest_row.get("openPrice", latest_row.get("open", 0)) or 0),
            "high": float(latest_row.get("highPrice", latest_row.get("high", 0)) or 0),
            "low": float(latest_row.get("lowPrice", latest_row.get("low", 0)) or 0),
            "close": float(latest_row.get("closePrice", latest_row.get("close", 0)) or 0),
            "volume": float(latest_row.get("lastTradedVolume", latest_row.get("volume", 0)) or 0),
        }

        rules = market_info.get("dealingRules", {})
        snapshot = market_info.get("snapshot", {})
        bid = float(snapshot.get("bid", 0) or 0)
        offer = float(snapshot.get("offer", 0) or 0)
        direction = (
            "long"
            if decision.get("trade_signal") == "buy"
            else ("short" if decision.get("trade_signal") == "sell" else "hold")
        )
        entry_price = offer if direction == "long" else (bid if direction == "short" else 0)
        min_size = float(rules.get("minDealSize", {}).get("value", 0.1))
        max_size = float(rules.get("maxDealSize", {}).get("value", 3250))
        increment = float(rules.get("minSizeIncrement", {}).get("value", 0.1))

        strategy_leverage = decision.get("strategy_leverage", None)
        if strategy_leverage is not None:
            logger.info(
                "Brain Preview: Using leverage %s from strategy '%s'",
                strategy_leverage,
                decision.get("strategy_used", "N/A"),
            )

        sizing = None
        if direction in ("long", "short") and entry_price:
            available = 0.0
            if app_state.current_account and app_state.current_account.get("balance"):
                available = float(app_state.current_account["balance"].get("available", 0) or 0)
            invest_pct = app_state.settings.getfloat("BOT_CONFIG", "investment_pct", 99) / 100
            leverage = (
                float(strategy_leverage)
                if strategy_leverage is not None
                else app_state.settings.getfloat("BOT_CONFIG", "leverage", 1)
            )
            raw_contracts = (available * invest_pct * leverage) / entry_price
            contracts = max(min_size, min(max_size, raw_contracts))
            contracts = (contracts // increment) * increment
            sl_type = app_state.settings.get("BOT_CONFIG", "stop_loss_type", "normal")
            sl_pct = app_state.settings.getfloat("BOT_CONFIG", "stop_loss_pct", 2) / 100
            if sl_type in ("normal", "trailing"):
                stop_level = (
                    entry_price * (1 - sl_pct)
                    if direction == "long"
                    else entry_price * (1 + sl_pct)
                )
            else:
                first_use = app_state.settings.get("BOT_CONFIG", "sl_use", "0,1,2,4,6,8,10").split(",")[0]
                first_pct = float(first_use) / 100 if first_use and first_use != "0" else sl_pct
                stop_level = (
                    entry_price * (1 - first_pct)
                    if direction == "long"
                    else entry_price * (1 + first_pct)
                )
            sizing = {
                "available": available,
                "investment_pct": invest_pct,
                "leverage": leverage,
                "strategy_leverage": strategy_leverage,
                "leverage_source": "strategy" if strategy_leverage is not None else "settings",
                "entry_price": entry_price,
                "contracts": contracts,
                "min_size": min_size,
                "max_size": max_size,
                "increment": increment,
                "stop_level": stop_level,
                "sl_type": sl_type,
            }

        import numpy as np

        def convert_numpy(obj):
            if isinstance(obj, np.bool_):
                return bool(obj)
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.floating):
                return float(obj)
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, dict):
                return {k: convert_numpy(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [convert_numpy(item) for item in obj]
            return obj

        decision = convert_numpy(decision)
        fired_signals = decision.get("fired_signals", {})
        last_candle_time = df.iloc[-1]["timestamp"] if "timestamp" in df.columns else str(df.index[-1])

        data_source = "Alpha Vantage (historical only)"
        if bot_instance and getattr(bot_instance, "_temp_gap_data", None) is not None:
            data_source = "Alpha Vantage + Capital.com (gap-filled)"
        else:
            try:
                last_candle_dt = pd.to_datetime(last_candle_time)
                if last_candle_dt.tzinfo is None:
                    last_candle_dt = pytz.UTC.localize(last_candle_dt)
                now_utc = datetime.now(pytz.UTC)
                hours_ago = (now_utc - last_candle_dt).total_seconds() / 3600
                if hours_ago < 2:
                    data_source = "Alpha Vantage + Capital.com (gap-filled)"
            except Exception:
                pass

        app_state.data_source = data_source
        return {
            "ok": True,
            "strategy_mode": strategy_mode if "strategy_mode" in locals() else "enhanced",
            "crash_protection": bool(ai.enable_crash_protection),
            "decision": decision,
            "sizing": sizing,
            "market_info": market_info,
            "last_candle": last_candle,
            "last_candle_time": str(last_candle_time),
            "selected_strategy": decision.get("selected_strategy", "N/A"),
            "fired_signals": fired_signals,
            "strategy_config": decision.get("strategy_config", None),
            "data_source": data_source,
        }
    except Exception as exc:
        logger.error(f"Brains preview error: {exc}")
        return {"ok": False, "error": str(exc)}


@app.get("/account/preferences")
async def get_account_preferences():
    try:
        if not app_state.api:
            return {"ok": False, "error": "no_api_connection"}
        prefs = await app_state.api.get_account_preferences()
        return {"ok": prefs is not None, "preferences": prefs}
    except Exception as exc:
        logger.error(f"Error fetching account preferences: {exc}")
        return {"ok": False, "error": str(exc)}


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
        return await app_state.api.update_account_leverage(category, leverage_val, hedging)
    except Exception as exc:
        logger.error(f"Error updating account leverage: {exc}")
        return {"ok": False, "error": str(exc)}


@app.get("/config")
async def get_config():
    env = app_state.api.environment if app_state.api else "demo"
    selected = app_state.settings.get("ENV_ACCOUNTS", env, "") or app_state.settings.get(
        "CREDENTIALS", "account_id", ""
    )
    override_flag = app_state.settings.getboolean("MARKET_HOURS", "use_override", False)
    override_epic = app_state.settings.get("MARKET_HOURS", "override_epic", "")
    return {
        "environment": env,
        "selected_account_id": selected,
        "is_connected": app_state.is_connected,
        "market_hours_override": {
            "enabled": override_flag,
            "epic": override_epic,
        },
    }


@app.post("/api/log/level")
async def set_log_level_endpoint(payload: dict = Body(...)):
    try:
        debug_mode = payload.get("debug_mode", False)
        set_log_level(debug_mode)
        level = "DEBUG/INFO" if debug_mode else "ERROR/WARNING"
        logger.info("Log level changed to: %s", level)
        return {"success": True, "message": f"Log level set to {level}"}
    except Exception as exc:
        logger.error(f"Error setting log level: {exc}")
        return {"success": False, "error": str(exc)}


@app.get("/api/log/sessions")
async def get_log_sessions():
    try:
        sessions = log_manager.get_session_logs()
        return {"success": True, "sessions": sessions}
    except Exception as exc:
        logger.error(f"Error getting log sessions: {exc}")
        return {"success": False, "error": str(exc)}


@app.post("/api/strategy/settings")
async def save_strategy_settings(payload: dict = Body(...)):
    try:
        strategy_mode = payload.get("strategy_mode", "enhanced")
        enable_crash_protection = payload.get("enable_crash_protection", True)

        app_state.settings.set_value("STRATEGY", "strategy_mode", strategy_mode)
        app_state.settings.set_value(
            "STRATEGY", "enable_crash_protection", str(enable_crash_protection)
        )

        if "market_hours_override" in payload:
            override_payload = payload.get("market_hours_override", {}) or {}
            override_enabled = bool(override_payload.get("enabled", False))
            override_epic = override_payload.get("epic", "")
            app_state.settings.set_value("MARKET_HOURS", "use_override", str(override_enabled))
            if override_epic:
                app_state.settings.set_value("MARKET_HOURS", "override_epic", override_epic)

        if strategy_mode in ("test8_no_protection", "test8_with_protection"):
            epic_override = payload.get("epic") or app_state.settings.get(
                "STRATEGY", "test8_epic", fallback="SOXL"
            )
            if epic_override:
                app_state.settings.set_value("STRATEGY", "test8_epic", epic_override)

        app_state.settings.save()

        if app_state.bot and app_state.bot.ai_system:
            if strategy_mode == "test6_no_protection":
                app_state.bot.ai_system.strategy_mode = "test6"
                app_state.bot.ai_system.enable_crash_protection = False
            elif strategy_mode == "test6_with_protection":
                app_state.bot.ai_system.strategy_mode = "test6"
                app_state.bot.ai_system.enable_crash_protection = True
            elif strategy_mode in ("test8_no_protection", "test8_with_protection"):
                app_state.bot.ai_system.strategy_mode = "test8"
                app_state.bot.ai_system.enable_crash_protection = (
                    strategy_mode == "test8_with_protection"
                )
                app_state.bot.epic = app_state.settings.get("STRATEGY", "test8_epic", fallback="SOXL")
            else:
                app_state.bot.ai_system.strategy_mode = strategy_mode
                app_state.bot.ai_system.enable_crash_protection = enable_crash_protection

            logger.info(
                "Strategy updated: %s, Crash protection: %s",
                strategy_mode,
                app_state.bot.ai_system.enable_crash_protection,
            )

            if strategy_mode == "all_signals" and enable_crash_protection:
                logger.info("Expected: $699,074 (57.2% WR, -96.9% DD) - PROVEN RESULT")
            elif strategy_mode == "all_signals" and not enable_crash_protection:
                logger.info("WARNING: Expected: $376,004 (56.1% WR, -98.7% DD) - NO PROTECTION")
            elif strategy_mode == "two_rsi_only" and enable_crash_protection:
                logger.info("Expected: $485,948 (59.6% WR, -33.9% DD) - LOWEST RISK")
            elif strategy_mode == "two_rsi_only" and not enable_crash_protection:
                logger.info("WARNING: Expected: $348,803 (58.1% WR, -68.5% DD) - NO PROTECTION")

        return {"success": True, "message": "Strategy settings saved"}
    except Exception as exc:
        logger.error(f"Error saving strategy settings: {exc}")
        return {"success": False, "error": str(exc)}


@app.post("/config/stoploss")
async def save_stoploss_settings(payload: dict = Body(...)):
    try:
        app_state.settings.set_value("BOT_CONFIG", "stop_loss_type", payload.get("stop_loss_type", "normal"))
        app_state.settings.set_value("BOT_CONFIG", "stop_loss_pct", payload.get("stop_loss_pct", "2.0"))
        app_state.settings.set_value(
            "BOT_CONFIG",
            "override_strategy_sl",
            str(payload.get("override_strategy_sl", False))
        )
        app_state.settings.set_value("BOT_CONFIG", "sl_thresholds", payload.get("sl_thresholds", "5,10,15"))
        app_state.settings.set_value("BOT_CONFIG", "sl_adjustments", payload.get("sl_adjustments", "2,5,8"))
        app_state.settings.set_value("BOT_CONFIG", "sl_when_at", payload.get("sl_when_at", "2,4,5,7,10,12,15"))
        app_state.settings.set_value("BOT_CONFIG", "sl_use", payload.get("sl_use", "0,1,2,4,6,8,10"))
        app_state.settings.set_value(
            "BOT_CONFIG",
            "use_trailing_sl",
            str(payload.get("stop_loss_type") in ["trailing", "staggered"]),
        )
        logger.info("Stop loss settings updated: %s", payload.get("stop_loss_type"))
        return {"ok": True}
    except Exception as exc:
        logger.error(f"Error saving stop loss settings: {exc}")
        return {"ok": False, "error": str(exc)}


@app.post("/config/environment")
async def set_environment(payload: dict = Body(...)):
    env = (payload or {}).get("environment", "demo").lower()
    if env not in ["demo", "live"]:
        return {"ok": False, "error": "invalid_environment"}

    app_state.settings.set_value("API_CONFIG", "environment", env)
    from bot.api import CapitalComAPI

    app_state.api = CapitalComAPI(app_state.settings, environment=env)
    logger.info("Environment changed to %s; re-authenticating", env)

    if await app_state.api.authenticate():
        app_state.is_connected = True
        accounts = await app_state.api.get_accounts()
        saved_id = app_state.settings.get("ENV_ACCOUNTS", env, "")
        target = next((acc for acc in accounts if acc.get("accountId") == saved_id), None)
        target = target or (accounts[0] if accounts else None)
        if target:
            await app_state.api.switch_account(target.get("accountId"))
            app_state.current_account = target
        return {"ok": True, "environment": env}
    app_state.is_connected = False
    return {"ok": False, "error": "auth_failed"}


@app.get("/accounts")
async def list_accounts():
    if not app_state.api:
        return {"accounts": []}
    accounts = await app_state.api.get_accounts()
    return {
        "accounts": [
            {"accountId": acc.get("accountId"), "accountName": acc.get("accountName")}
            for acc in accounts
        ]
    }


@app.post("/accounts/select")
async def select_account(payload: dict = Body(...)):
    account_id = (payload or {}).get("account_id")
    if not account_id:
        return {"ok": False, "error": "missing_account_id"}

    logger.info("Selecting account %s", account_id)
    ok = await app_state.api.switch_account(account_id)
    if ok:
        app_state.settings.set_env_account(app_state.api.environment, account_id)
        accounts = await app_state.api.get_accounts()
        app_state.current_account = next(
            (acc for acc in accounts if acc.get("accountId") == account_id),
            {"accountId": account_id},
        )
    return {"ok": ok}


if __name__ == "__main__":
    settings = TradingBotSettings()
    port = settings.getint("DISPLAY_CONFIG", "port", 8011)
    kill_port_if_posix(port)
    uvicorn.run(app, host="0.0.0.0", port=port)
