#!/usr/bin/env python3
"""
Independent verifier for Brain Preview's Test8 (SOXL Top 100) selection.

What it does:
- Loads 5m candles via the same pipeline as the bot (Alpha Vantage + Capital.com gap-fill if available)
- Evaluates Test8 profitability-ranked configs using Brains/strategy_signals.py
- Reports which signal fired and which configuration was selected (by final_balance)
- Prints whether this matches "rsi_oversold" as shown in Brain Preview

Run:
  .venv\Scripts\python verify_test8_preview.py
"""

import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime
import json
import sys
from typing import Any, Dict, List, Optional

import pandas as pd
import pytz

from bot.settings import TradingBotSettings
from bot.trader import TradingBot

try:
    # Capital.com API is optional for running (gap-fill); script still works with AV-only
    from bot.api import CapitalComAPI  # type: ignore
except Exception:  # pragma: no cover - tolerate missing/old SDKs
    CapitalComAPI = None  # type: ignore


@dataclass
class VerificationResult:
    ok: bool
    error: Optional[str]
    epic: str
    strategy_mode: str
    enable_crash_protection: bool
    last_candle_time_local: str
    last_candle_time_dubai: str
    selected_signal: Optional[str]
    winner_summary: Optional[Dict[str, Any]]
    fired_count: int
    agrees_with_preview_claim: Optional[bool]


def _fmt_ts_for_display(ts) -> str:
    try:
        if getattr(ts, "tzinfo", None) is None:
            ts = pytz.UTC.localize(pd.to_datetime(ts).to_pydatetime())
        return ts.astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts)


def _fmt_ts_dubai(ts) -> str:
    try:
        if getattr(ts, "tzinfo", None) is None:
            ts = pytz.UTC.localize(pd.to_datetime(ts).to_pydatetime())
        return ts.astimezone(pytz.timezone("Asia/Dubai")).strftime("%Y-%m-%d %H:%M:%S %Z")
    except Exception:
        return str(ts)


async def _load_dataframe(settings: TradingBotSettings, epic: str) -> pd.DataFrame:
    bot = TradingBot(settings)
    # Honor Test8 epic override
    bot.epic = epic

    # Attach API if available to allow Capital.com gap-fill
    if CapitalComAPI is not None:
        try:
            env = settings.get("API_CONFIG", "environment", "demo").lower()
            api = CapitalComAPI(settings, environment=env)
            ok = await api.authenticate()
            if ok:
                bot.api = api
                bot.api_connected = True
        except Exception:
            pass  # proceed with AV-only

    # Refresh AV data (this triggers gap-fill when API is set)
    try:
        await bot.refresh_alpha_vantage_data(force_refresh=True)
    except Exception:
        # Still attempt to load cached/DB data
        pass

    df = bot._load_alpha_vantage_dataframe(limit=500, include_gap_fill=True)
    if df is None or len(df) < 100:
        raise RuntimeError(f"Insufficient candles loaded: {0 if df is None else len(df)}")
    return df


def _evaluate_test8(df: pd.DataFrame, strategy_mode: str, enable_crash_protection: bool) -> Dict[str, Any]:
    # Use the Test8 logic from Brains/strategy_signals (profitability-based selection)
    from Brains.strategy_signals import get_strategy_analysis

    # Pass current_date for crash protection logic (date of last candle)
    current_date = pd.to_datetime(df["timestamp"].iloc[-1]).date()
    analysis = get_strategy_analysis(
        df,
        strategy_mode="test8",  # force Test8 core logic
        enable_crash_protection=enable_crash_protection,
        current_date=current_date,
    )
    return analysis


async def verify() -> VerificationResult:
    settings = TradingBotSettings()

    # Derive strategy mode and crash protection intent (mirror main.py mapping)
    raw_mode = settings.get("STRATEGY", "strategy_mode", "enhanced") if settings.has_section("STRATEGY") else "enhanced"
    if raw_mode in ("test8_no_protection", "test8_with_protection"):
        strategy_mode = "test8"
        enable_crash = raw_mode == "test8_with_protection"
        epic = settings.get("STRATEGY", "test8_epic", fallback="SOXL")
    else:
        # Allow ad-hoc verification of Test8 even if UI is on another mode
        strategy_mode = "test8"
        enable_crash = settings.getboolean("STRATEGY", "enable_crash_protection", True)
        epic = settings.get("STRATEGY", "test8_epic", fallback="SOXL")

    df = await _load_dataframe(settings, epic)

    # Ensure expected columns exist for strategy_signals
    required = {"timestamp", "openPrice", "highPrice", "lowPrice", "closePrice", "lastTradedVolume"}
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise RuntimeError(f"Missing required columns for analysis: {missing}")

    analysis = _evaluate_test8(df, strategy_mode, enable_crash)

    selected_signal = analysis.get("selected_strategy")
    fired = analysis.get("fired_signals", {}) or {}
    fired_cfgs: List[Dict[str, Any]] = fired.get("__test8_configs__", []) if isinstance(fired, dict) else []
    winner_meta = analysis.get("strategy_config") or {}

    # Compose result
    last_ts = df.iloc[-1]["timestamp"]
    result = VerificationResult(
        ok=True,
        error=None,
        epic=epic,
        strategy_mode=("test8_with_protection" if enable_crash else "test8_no_protection"),
        enable_crash_protection=enable_crash,
        last_candle_time_local=_fmt_ts_for_display(last_ts),
        last_candle_time_dubai=_fmt_ts_dubai(last_ts),
        selected_signal=selected_signal,
        winner_summary={
            "signal": selected_signal,
            "rank": winner_meta.get("rank"),
            "final_balance": winner_meta.get("final_balance"),
            "win_rate": winner_meta.get("win_rate"),
            "params": winner_meta.get("params"),
        } if winner_meta else None,
        fired_count=len(fired_cfgs),
        agrees_with_preview_claim=(selected_signal == "rsi_oversold"),
    )

    # Pretty print summary and machine-readable JSON
    print("=== Test8 Verification Summary ===")
    print(f"Epic: {result.epic}")
    print(f"Mode: {result.strategy_mode} (crash_protection={result.enable_crash_protection})")
    print(f"Last Candle (Local): {result.last_candle_time_local}")
    print(f"Last Candle (Dubai): {result.last_candle_time_dubai}")
    print(f"Selected Signal: {result.selected_signal}")
    if result.winner_summary:
        print("Winner Details:")
        for k, v in result.winner_summary.items():
            print(f"  - {k}: {v}")
    print(f"Fired Configs: {result.fired_count}")
    print(f"Agrees with Brain Preview claim (rsi_oversold): {result.agrees_with_preview_claim}")
    print("=== JSON ===")
    print(json.dumps(asdict(result), indent=2))

    return result


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}))
        sys.exit(1)




