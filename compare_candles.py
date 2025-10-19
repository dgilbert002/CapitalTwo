#!/usr/bin/env python3
"""
Compare SOXL 5-minute candles between Alpha Vantage (from database) and
Capital.com (live historical endpoint) for the most recent Friday
regular session (09:30–16:00 ET). Prints a text depiction with diffs.

Usage: python compare_candles.py
"""

import asyncio
import sqlite3
from datetime import datetime, timedelta, time
import os

import pandas as pd
import pytz

from bot.settings import TradingBotSettings
from bot.api import CapitalComAPI


EPIC = "SOXL"

# Allow overriding comparison date via env var COMPARE_DATE=YYYY-MM-DD
COMPARE_DATE = os.environ.get("COMPARE_DATE")


def get_last_friday_eastern(now_utc: datetime) -> datetime:
    eastern = pytz.timezone("US/Eastern")
    now_et = now_utc.astimezone(eastern)
    # Weekday: Monday=0 ... Friday=4 ... Sunday=6
    days_back = (now_et.weekday() - 4) % 7
    last_friday = now_et - timedelta(days=days_back)
    return last_friday.replace(hour=0, minute=0, second=0, microsecond=0)


def load_alpha_window(settings: TradingBotSettings, start_et: datetime, end_et: datetime) -> pd.DataFrame:
    # Prefer configured table, but if it doesn't match SOXL, try SOXL_av_5min
    table = settings.get("ALPHA_VANTAGE", "table_name", f"{EPIC}_av_5min")
    if EPIC not in table.upper():
        table = f"{EPIC}_av_5min"
    db_path = settings.get("ALPHA_VANTAGE", "database", "database_av.db")

    conn = sqlite3.connect(db_path)
    # Many installs store ET strings; select a slightly wider window to capture boundaries
    q = f"""
        SELECT timestamp, open, high, low, close
        FROM {table}
        WHERE timestamp >= ? AND timestamp <= ?
        ORDER BY timestamp
    """
    rows = conn.execute(
        q,
        (
            (start_et - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
            (end_et + timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        ),
    ).fetchall()
    conn.close()

    df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close"])
    eastern = pytz.timezone("US/Eastern")
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])  # naive ET strings
        df["timestamp"] = df["timestamp"].dt.tz_localize(eastern)
        # Clip back to exact window
        df = df[(df["timestamp"] >= start_et) & (df["timestamp"] <= end_et)]
    return df


async def load_capital_window(settings: TradingBotSettings, start_et: datetime, end_et: datetime) -> pd.DataFrame:
    api = CapitalComAPI(settings, environment=settings.get("API_CONFIG", "environment", "demo"))
    ok = await api.authenticate()
    if not ok:
        raise RuntimeError("Capital.com authenticate() failed")

    # Prefer ResolutionType from API helper
    resolution = api.ResolutionType.MINUTE_5 if api.ResolutionType else None
    if resolution is None:
        # Fallback import (older/newer SDKs)
        try:
            from capitalcom.client import ResolutionType as RT
        except Exception:
            from capitalcom.client_demo import ResolutionType as RT
        resolution = RT.MINUTE_5

    # Pull a generous window that certainly covers the session
    # 500 candles ~ 2500 minutes ~ > 1.5 days
    hist = await api.get_historical_prices(EPIC, resolution, 500)
    if not hist or "prices" not in hist:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close"])

    eastern = pytz.timezone("US/Eastern")
    records = []
    for p in hist["prices"]:
        try:
            # Use UTC timestamp and convert to ET to align with AV
            ts_utc = pd.to_datetime(p.get("snapshotTimeUTC"), utc=True)
            ts_et = ts_utc.astimezone(eastern)
            if ts_et < start_et or ts_et > end_et:
                continue
            # Compute mid prices where possible for closer parity with AV
            def mid(field: str) -> float:
                block = p.get(field) or {}
                bid = block.get("bid")
                ask = block.get("ask")
                if bid is not None and ask is not None:
                    return (float(bid) + float(ask)) / 2.0
                # Fallback to bid if ask is missing
                return float(bid) if bid is not None else float(ask)
            records.append(
                {
                    "timestamp": ts_et,
                    "open": mid("openPrice"),
                    "high": mid("highPrice"),
                    "low": mid("lowPrice"),
                    "close": mid("closePrice"),
                }
            )
        except Exception:
            continue

    df = pd.DataFrame(records)
    if not df.empty:
        df = df.sort_values("timestamp")
    return df


def depict_rows(df_alpha: pd.DataFrame, df_capital: pd.DataFrame, limit: int = 10) -> None:
    merged = pd.merge(
        df_alpha.rename(columns={c: f"{c}_alpha" for c in ["open", "high", "low", "close"]}),
        df_capital.rename(columns={c: f"{c}_capital" for c in ["open", "high", "low", "close"]}),
        on="timestamp",
        how="inner",
    )
    if merged.empty:
        print("No overlapping candles found for the requested Friday window.")
        return

    merged["diff_open"] = merged["open_alpha"] - merged["open_capital"]
    merged["diff_high"] = merged["high_alpha"] - merged["high_capital"]
    merged["diff_low"] = merged["low_alpha"] - merged["low_capital"]
    merged["diff_close"] = merged["close_alpha"] - merged["close_capital"]

    print("\n=== Last few candles (ET) ===")
    tail = merged.tail(limit)
    for _, r in tail.iterrows():
        ts = r["timestamp"].strftime("%Y-%m-%d %H:%M")
        print(
            f"{ts}  AV O/H/L/C: {r['open_alpha']:.4f}/{r['high_alpha']:.4f}/"
            f"{r['low_alpha']:.4f}/{r['close_alpha']:.4f}  |  CAP O/H/L/C: "
            f"{r['open_capital']:.4f}/{r['high_capital']:.4f}/{r['low_capital']:.4f}/"
            f"{r['close_capital']:.4f}  |  Δ O/H/L/C: "
            f"{r['diff_open']:.4f}/{r['diff_high']:.4f}/{r['diff_low']:.4f}/{r['diff_close']:.4f}"
        )

    print("\n=== Diff summary (should be ~0.0000 if identical) ===")
    print(
        merged[["diff_open", "diff_high", "diff_low", "diff_close"]]
        .describe()
        .to_string()
    )
    print(f"\nRows compared: {len(merged)}")


def get_db_range(settings: TradingBotSettings) -> tuple[datetime | None, datetime | None]:
    table = settings.get("ALPHA_VANTAGE", "table_name", f"{EPIC}_av_5min")
    if EPIC not in table.upper():
        table = f"{EPIC}_av_5min"
    db_path = settings.get("ALPHA_VANTAGE", "database", "database_av.db")
    conn = sqlite3.connect(db_path)
    row = conn.execute(f"SELECT MIN(timestamp), MAX(timestamp) FROM {table}").fetchone()
    conn.close()
    if not row or not row[0] or not row[1]:
        return None, None
    eastern = pytz.timezone("US/Eastern")
    min_ts = eastern.localize(pd.to_datetime(row[0]).to_pydatetime())
    max_ts = eastern.localize(pd.to_datetime(row[1]).to_pydatetime())
    return min_ts, max_ts


async def main():
    settings = TradingBotSettings()
    eastern = pytz.timezone("US/Eastern")

    # Decide the comparison date
    if COMPARE_DATE:
        day = datetime.strptime(COMPARE_DATE, "%Y-%m-%d").date()
    else:
        # Use the latest date present in the AV DB to guarantee overlap
        _, db_max = get_db_range(settings)
        if not db_max:
            print("No Alpha Vantage data available in database.")
            return
        day = db_max.date()

    start_et = eastern.localize(datetime.combine(day, time(9, 30)))
    end_et = eastern.localize(datetime.combine(day, time(16, 0)))

    print(f"Comparing {EPIC} 5m candles on {start_et.date()} between 09:30 and 16:00 ET")

    df_alpha = load_alpha_window(settings, start_et, end_et)
    print(f"Alpha Vantage candles: {len(df_alpha)}")

    df_capital = await load_capital_window(settings, start_et, end_et)
    print(f"Capital.com candles:  {len(df_capital)}")

    depict_rows(df_alpha, df_capital, limit=12)


if __name__ == "__main__":
    asyncio.run(main())


