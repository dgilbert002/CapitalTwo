#!/usr/bin/env python3
"""
Database utilities for loading per-epic 5-minute data tables from database.db.
Tables are named by epic, e.g., "TECL".
Falls back to legacy candles table if epic table is missing.
"""

import sqlite3
import pandas as pd
from typing import Optional
import configparser
import os


def load_epic_df(db_path: str, epic: str) -> pd.DataFrame:
    """Load an epic table (e.g., TECL) into a standardized OHLCV dataframe.

    Columns returned: timestamp, date, time, openPrice, highPrice, lowPrice, closePrice, lastTradedVolume
    
    Note: For epics with 1-minute data, this will use the 5-minute aggregated table (e.g., TECL_5min)
    """
    conn = sqlite3.connect(db_path)
    try:
        # Prefer vendor-specific 5-minute tables, then generic
        tried = []
        last_err = None
        for table_name in (f"{epic}_av_5min", f"{epic}_5min", f"{epic}"):
            try:
                df = pd.read_sql_query(
                    f"""
                    SELECT timestamp, open, high, low, close, volume
                    FROM "{table_name}"
                    ORDER BY timestamp ASC
                    """,
                    conn,
                )
                break
            except Exception as e:
                tried.append(table_name)
                last_err = e
                df = None  # ensure defined
        if df is None:
            # Fallback to legacy candles table
            df = pd.read_sql_query(
                """
                SELECT timestamp, open, high, low, close, volume
                FROM candles
                WHERE epic = ?
                ORDER BY timestamp ASC
                """,
                conn,
                params=(epic,),
            )
    finally:
        conn.close()

    if df.empty:
        raise RuntimeError(f"No data found for epic '{epic}' in {db_path}")

    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df['date'] = df['timestamp'].dt.date
    df['time'] = df['timestamp'].dt.time
    df.rename(columns={
        'open': 'openPrice',
        'high': 'highPrice',
        'low': 'lowPrice',
        'close': 'closePrice',
        'volume': 'lastTradedVolume'
    }, inplace=True)
    return df


def load_settings(settings_path: str = 'settings.txt') -> dict:
    cfg = configparser.ConfigParser()
    if os.path.exists(settings_path):
        cfg.read(settings_path)
    else:
        # Defaults
        cfg['FINANCE'] = {
            'start_balance': '100',
            'monthly_top_up': '100',
            'top_up_day': '25',
            'invest_pct': '0.99',
        }
        cfg['RISK'] = {
            'max_drawdown_pct': '50',
            'stop_on_zero': 'true',
        }
        cfg['LEVERAGE'] = {'levels': '2,3,4,5'}
        cfg['EXPLOIT'] = {'enabled': 'true', 'top_k': '5'}
        cfg['OUTPUT'] = {
            'save_top_snapshots': 'false',
            'save_global_top': 'false',
            'overwrite_global_top': 'false',
        }

    return {
        'start_balance': float(cfg.get('FINANCE', 'start_balance', fallback='100')),
        'monthly_top_up': float(cfg.get('FINANCE', 'monthly_top_up', fallback='100')),
        'top_up_day': int(cfg.get('FINANCE', 'top_up_day', fallback='25')),
        'invest_pct': float(cfg.get('FINANCE', 'invest_pct', fallback='0.99')),
        'max_drawdown_pct': float(cfg.get('RISK', 'max_drawdown_pct', fallback='50')),
        'stop_on_zero': cfg.getboolean('RISK', 'stop_on_zero', fallback=True),
        'stop_loss_levels': [float(x.strip()) for x in cfg.get('RISK', 'stop_loss_levels', fallback='2,2.5,3,3.5,4,4.5,5').split(',') if x.strip()],
        'leverages': [float(x.strip()) for x in cfg.get('LEVERAGE', 'levels', fallback='2,2.5,3,3.5,4,4.5,5').split(',') if x.strip()],
        'exploit_enabled': cfg.getboolean('EXPLOIT', 'enabled', fallback=True),
        'exploit_top_k': int(cfg.get('EXPLOIT', 'top_k', fallback='5')),
        'save_top_snapshots': cfg.getboolean('OUTPUT', 'save_top_snapshots', fallback=False),
        'save_global_top': cfg.getboolean('OUTPUT', 'save_global_top', fallback=False),
        'overwrite_global_top': cfg.getboolean('OUTPUT', 'overwrite_global_top', fallback=False),
        'lookback_months': int(cfg.get('DATA', 'lookback_months', fallback='0')),
        'start_date': cfg.get('TESTING', 'start_date', fallback=cfg.get('DATA', 'start_date', fallback=None)),
        'end_date': cfg.get('TESTING', 'end_date', fallback=cfg.get('DATA', 'end_date', fallback=None)),
    }
