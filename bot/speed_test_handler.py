"""
Speed Test Handler - Graceful time manipulation for rapid testing
"""

import asyncio
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)


class SpeedTestHandler:
    def __init__(self, bot_instance: Any):
        self.bot = bot_instance
        self.epic = self.bot.epic
        self.api = self.bot.api
        self.market_timer = self.bot.market_timer
        self.settings = self.bot.settings

    async def run_speed_test(self, days: int = 5):
        """Execute graceful speed test with smooth transitions"""
        try:
            logger.debug("run_speed_test called with days=%s", days)
            # expose total days for UI progress
            self.total_days = days
            if hasattr(self.bot, "record_action"):
                self.bot.record_action(
                    {"event": "speedtest_start", "days": days}
                )
            logger.info("=" * 60)
            logger.info(f"SPEED TEST: Starting {days} day REAL trading test")
            logger.info(
                "Fast forward until T-30s, then REAL TIME for critical moments"
            )
            logger.info("=" * 60)

            # Check market is open
            market_info = await self.api.get_market_info(self.epic)
            logger.debug(
                "run_speed_test market_info response: %s",
                "snapshot" in market_info if market_info else None,
            )
            if not market_info:
                logger.warning(
                    "run_speed_test exiting: no market info for %s", self.epic
                )
                return {"ok": False, "error": "no_market_info"}

            snapshot = market_info.get("snapshot", {})
            if snapshot.get("marketStatus") != "TRADEABLE":
                logger.warning(
                    "run_speed_test exiting: marketStatus=%s for %s",
                    snapshot.get("marketStatus"),
                    self.epic,
                )
                return {
                    "ok": False,
                    "error": "market_closed",
                    "message": "Market must be OPEN for speed test",
                }

            # Download and verify data first
            logger.info("SPEED TEST: Downloading historical data...")
            data_ready = await self._prepare_data()
            logger.debug("run_speed_test data_ready=%s", data_ready)
            if not data_ready:
                logger.warning(
                    "run_speed_test exiting: data preparation failed for %s",
                    self.epic,
                )
                return {
                    "ok": False,
                    "error": "data_error",
                    "message": "Failed to prepare historical data",
                }

            results = {
                "days_simulated": 0,
                "trades_created": 0,
                "positions_closed": 0,
                "errors": [],
                "daily_results": [],
                "events": [],
            }

            # Run each day
            for day_num in range(1, days + 1):
                logger.info(f"\n{'='*40}")
                logger.info(f"SPEED TEST: Day {day_num}/{days}")
                logger.info(f"{'='*40}")

                day_result = await self._run_single_day(day_num, results)
                results["daily_results"].append(day_result)
                results["days_simulated"] += 1
                results["trades_created"] += day_result["trades_created"]
                results["positions_closed"] += day_result["positions_closed"]

                # Small pause between days
                await asyncio.sleep(0.5)

            logger.info("=" * 60)
            logger.info("SPEED TEST COMPLETE!")
            logger.info(f"Days: {results['days_simulated']}")
            logger.info(f"Trades Created: {results['trades_created']}")
            logger.info(f"Positions Closed: {results['positions_closed']}")
            logger.info("=" * 60)
            logger.debug(
                "run_speed_test completed with results=%s",
                results,
            )

            if hasattr(self.bot, "record_action"):
                self.bot.record_action(
                    {"event": "speedtest_complete", "days": results["days_simulated"]}
                )
            return {"ok": True, "results": results}

        except Exception as e:
            logger.error(f"Speed test error: {e}", exc_info=True)
            return {"ok": False, "error": str(e)}

    async def _prepare_data(self) -> bool:
        """Mirror live pipeline: refresh AV, fill gaps with Capital.com, validate."""
        try:
            logger.debug("_prepare_data called for epic=%s", self.epic)

            # Refresh Alpha Vantage data (forces gap fill against Capital.com if needed)
            refreshed = await self.bot.refresh_alpha_vantage_data(
                force_refresh=True
            )
            logger.debug("_prepare_data refresh result=%s", refreshed)
            if not refreshed:
                logger.warning(
                    "Alpha Vantage refresh failed during speed test setup"
                )

            # Load combined AV + Capital.com gap-fill dataframe just like live bot
            load_kwargs = {
                "limit": 1000,
                "include_gap_fill": True,
            }
            if hasattr(self.bot, "_load_alpha_vantage_dataframe"):
                df = self.bot._load_alpha_vantage_dataframe(**load_kwargs)
            else:
                logger.error(
                    "TradingBot missing _load_alpha_vantage_dataframe"
                )
                return False

            row_count = len(df) if df is not None else 0
            logger.debug(
                "_prepare_data loaded dataframe: rows=%s include_gap_fill=%s",
                row_count,
                True,
            )

            if df is None or row_count < 100:
                logger.error(
                    "Insufficient candles for speed test: %s",
                    row_count,
                )
                return False

            logger.info(
                "Speed test data prepared using AV + Capital.com gap fill"
                " (%s candles)",
                row_count,
            )
            return True

        except Exception as e:
            logger.error(f"Data preparation failed: {e}")
            logger.debug(
                "_prepare_data returning False due to exception", exc_info=True
            )
            return False

    async def _run_single_day(self, day_num: int, results: Dict) -> Dict:
        """Run a single day with graceful speed transitions"""

        day_result = {
            "day": day_num,
            "trades_created": 0,
            "positions_closed": 0,
            "errors": [],
        }
        logger.debug(
            "_run_single_day start: day_num=%s results_so_far=%s",
            day_num,
            {
                "days_simulated": results.get("days_simulated"),
                "trades_created": results.get("trades_created"),
                "positions_closed": results.get("positions_closed"),
            },
        )

        try:
            # Simulate market hours (6.5 hours = 390 minutes = 23400 seconds)
            total_seconds = 23400

            # Add event - Day starts
            results["events"].append(
                {
                    "type": "day_start",
                    "day": day_num,
                    "time": "09:30:00",
                    "message": f"Day {day_num}: Market Opens",
                }
            )

            # PHASE 1: Fast forward (compress 23370 seconds into ~3 seconds)
            # This leaves 30 seconds for the critical end-of-day period
            fast_forward_seconds = total_seconds - 30  # 23370 seconds
            fast_forward_real_time = 3.0  # Compress into 3 real seconds

            logger.info(f"Day {day_num}: Fast forwarding through trading day...")

            # Simulate progress updates during fast forward
            for i in range(10):
                await asyncio.sleep(fast_forward_real_time / 10)

                # Calculate simulated time
                seconds_passed = int(
                    (fast_forward_seconds / 10) * (i + 1)
                )
                hours = 9 + (seconds_passed // 3600)
                minutes = 30 + ((seconds_passed % 3600) // 60)
                if minutes >= 60:
                    hours += minutes // 60
                    minutes = minutes % 60

                # Send progress event
                results["events"].append(
                    {
                        "type": "fast_forward",
                        "day": day_num,
                        "time": f"{hours:02d}:{minutes:02d}:00",
                        "progress": (i + 1) * 10,
                    }
                )
                if hasattr(self.bot, "record_action"):
                    overall = ((day_num - 1) + ((i + 1) / 10)) / float(
                        getattr(self, "total_days", 1)
                    )
                    self.bot.record_action(
                        {
                            "event": "speedtest_progress",
                            "day": day_num,
                            "days_total": getattr(self, "total_days", 1),
                            "phase": "fast_forward",
                            "sim_time": f"{hours:02d}:{minutes:02d}:00",
                            "speed": "⚡ 2880x",
                            "progress": round(overall * 100, 1),
                        }
                    )

            # PHASE 2: T-30s - Slow down to REAL TIME
            logger.info(
                f"Day {day_num}: T-30s - Entering critical period"
                " (REAL TIME)"
            )

            # Mark transition to real time
            results["events"].append(
                {
                    "type": "critical_start",
                    "day": day_num,
                    "time": "15:59:30",
                    "message": "T-30s: Closing positions",
                }
            )
            if hasattr(self.bot, "record_action"):
                self.bot.record_action(
                    {
                        "event": "speedtest_phase",
                        "day": day_num,
                        "phase": "t_minus_30",
                        "message": "Closing positions",
                    }
                )

            # Close positions (if any)
            positions_before = await self.api.get_positions()
            positions_count_before = len(positions_before or [])

            if positions_count_before > 0:
                logger.info(
                    f"Day {day_num}: Closing {positions_count_before} positions..."
                )
                await self.bot.close_all_positions_timer()

                # Wait for positions to close
                await asyncio.sleep(2)

                positions_after = await self.api.get_positions()
                positions_count_after = len(positions_after or [])
                day_result["positions_closed"] = (
                    positions_count_before - positions_count_after
                )

                results["events"].append(
                    {
                        "type": "positions_closed",
                        "day": day_num,
                        "count": day_result["positions_closed"],
                    }
                )
                if hasattr(self.bot, "record_action"):
                    self.bot.record_action(
                        {
                            "event": "speedtest_phase",
                            "day": day_num,
                            "phase": "positions_closed",
                            "count": day_result["positions_closed"],
                        }
                    )

            # REAL TIME countdown from T-30s to T-15s (15 seconds real time)
            logger.info(f"Day {day_num}: Counting down to T-15s...")
            for seconds_left in range(29, 14, -1):
                await asyncio.sleep(1)  # REAL 1 second delay

                results["events"].append(
                    {
                        "type": "countdown",
                        "day": day_num,
                        "seconds_to_close": seconds_left,
                        "time": f"15:59:{60-seconds_left:02d}",
                    }
                )
                if hasattr(self.bot, "record_action"):
                    overall = (
                        (day_num - 1)
                        + 0.95
                        - ((seconds_left - 15) / 15) * 0.01
                    ) / float(getattr(self, "total_days", 1))
                    self.bot.record_action(
                        {
                            "event": "speedtest_progress",
                            "day": day_num,
                            "days_total": getattr(self, "total_days", 1),
                            "phase": "t30_countdown",
                            "sim_time": f"15:59:{60-seconds_left:02d}",
                            "speed": "🐌 1x",
                            "progress": round(overall * 100, 1),
                        }
                    )

            # PHASE 3: T-15s - Force trade creation (bypass Brains)
            logger.info(
                f"Day {day_num}: T-15s - FORCING trade creation (bypass Brains)"
            )

            results["events"].append(
                {
                    "type": "analysis_start",
                    "day": day_num,
                    "time": "15:59:45",
                    "message": "T-15s: Forcing trade creation",
                }
            )
            if hasattr(self.bot, "record_action"):
                self.bot.record_action(
                    {
                        "event": "speedtest_phase",
                        "day": day_num,
                        "phase": "t_minus_15",
                        "message": "Creating trade",
                    }
                )

            # Get fresh market info
            self.bot.market_info = await self.api.get_market_info(self.epic)
            dealing_rules = (self.bot.market_info or {}).get("dealingRules", {})

            # Count before creating trade
            positions_before_trade = await self.api.get_positions()
            positions_count_before_trade = len(positions_before_trade or [])

            # Build a forced AI analysis using settings direction
            try:
                direction_setting = self.settings.get(
                    "BOT_CONFIG", "direction", "long"
                )
            except Exception:
                direction_setting = "long"
            forced_signal = "buy" if direction_setting == "long" else "sell"
            ai_analysis = {"trade_signal": forced_signal, "confidence": 1.0}

            # Create trade directly via timer path (uses dealing rules & sizing)
            created_ok = await self.bot.create_position_timer(
                ai_analysis, dealing_rules
            )

            # Wait for trade creation
            await asyncio.sleep(2)

            positions_after_trade = await self.api.get_positions()
            positions_count_after_trade = len(positions_after_trade or [])

            if created_ok or (
                positions_count_after_trade > positions_count_before_trade
            ):
                day_result["trades_created"] = max(
                    1,
                    positions_count_after_trade - positions_count_before_trade,
                )
                logger.info(
                    f"Day {day_num}: Created {day_result['trades_created']} trades"
                    " (forced)"
                )

                results["events"].append(
                    {
                        "type": "trade_created",
                        "day": day_num,
                        "count": day_result["trades_created"],
                    }
                )
                if hasattr(self.bot, "record_action"):
                    self.bot.record_action(
                        {
                            "event": "speedtest_trade",
                            "day": day_num,
                            "status": "created",
                            "count": day_result["trades_created"],
                        }
                    )
            else:
                logger.info(
                    f"Day {day_num}: Failed to create trade during forced phase"
                )

                results["events"].append(
                    {
                        "type": "no_trade",
                        "day": day_num,
                        "reason": "Forced trade failed",
                    }
                )
                if hasattr(self.bot, "record_action"):
                    self.bot.record_action(
                        {"event": "speedtest_trade", "day": day_num, "status": "failed"}
                    )

            # REAL TIME countdown from T-15s to market close (15 seconds real time)
            logger.info(f"Day {day_num}: Final countdown to market close...")
            for seconds_left in range(14, -1, -1):
                await asyncio.sleep(1)  # REAL 1 second delay

                results["events"].append(
                    {
                        "type": "final_countdown",
                        "day": day_num,
                        "seconds_to_close": seconds_left,
                        "time": (
                            f"16:00:{seconds_left:02d}"
                            if seconds_left > 0
                            else "16:00:00"
                        ),
                    }
                )
                if hasattr(self.bot, "record_action"):
                    overall = (
                        (day_num - 1)
                        + 0.99
                        + ((14 - seconds_left) / 15) * 0.01
                    ) / float(getattr(self, "total_days", 1))
                    self.bot.record_action(
                        {
                            "event": "speedtest_progress",
                            "day": day_num,
                            "days_total": getattr(self, "total_days", 1),
                            "phase": "final_countdown",
                            "sim_time": (
                                f"16:00:{seconds_left:02d}"
                                if seconds_left > 0
                                else "16:00:00"
                            ),
                            "speed": "🐌 1x",
                            "progress": round(min(100.0, overall * 100), 1),
                        }
                    )

            # Market closes
            logger.info(f"Day {day_num}: Market CLOSED")

            results["events"].append(
                {
                    "type": "market_close",
                    "day": day_num,
                    "time": "16:00:00",
                    "message": f"Day {day_num}: Market Closed",
                    "summary": {
                        "positions_closed": day_result["positions_closed"],
                        "trades_created": day_result["trades_created"],
                    },
                }
            )
            if hasattr(self.bot, "record_action"):
                self.bot.record_action(
                    {
                        "event": "speedtest_day_complete",
                        "day": day_num,
                        "positions_closed": day_result["positions_closed"],
                        "trades_created": day_result["trades_created"],
                    }
                )

        except Exception as e:
            error_msg = f"Day {day_num} error: {e}"
            logger.error(error_msg)
            day_result["errors"].append(error_msg)

            results["events"].append({"type": "error", "day": day_num, "error": str(e)})
        finally:
            logger.debug("_run_single_day complete: day_result=%s", day_result)

        return day_result
