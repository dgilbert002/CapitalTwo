#!/usr/bin/env python3
"""
SOXL Test8 Strategy Checker

Replicates the user's Test8 SOXL batch simulation while allowing a quick check
of the strategy with and without crash protection.  The script:

- Loads SOXL 5‑minute candles from `settings.txt` (Alpha Vantage database/table)
- Reads the top profitability configs from `Results/global_top300__SOXL.tsv`
- Deduplicates unique parameter sets (keeping the highest final_balance entry)
- Simulates the “pick the most profitable firing signal” loop exactly as the
  user’s reference script, including their stop-loss handling
- Optionally applies the proven crash protection logic when requested

Output is limited to the two requested modes: WITH protection and WITHOUT.
"""

import json
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import time as dt_time
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd
import sqlite3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from bot.settings import TradingBotSettings
from focused_optimizer import calculate_trading_costs, get_price_at_time
from indicators import create_indicator_library
from Brains.strategy_signals import (
    calculate_daily_indicators,
    should_block_trade,
    CRASH_PROTECTION_CONFIG,
)

# ---------------------------------------------------------------------------
# CONSTANTS (mirroring the reference script)
# ---------------------------------------------------------------------------
ENTRY_TIME = dt_time(15, 59, 45)
EXIT_TIME = dt_time(15, 59, 30)
SPREAD_BPS = 13
SPREAD_RATE = SPREAD_BPS / 10_000
OVERNIGHT_FUNDING_RATE = 0.00023
MIN_CONTRACTS = 1
TSV_PATH = Path(__file__).resolve().parents[1] / 'Results' / 'global_top300__SOXL.tsv'


@dataclass(frozen=True)
class StrategyConfig:
    condition: str
    leverage: float
    period: Optional[int] = None
    multiplier: Optional[float] = None
    stop_loss_pct: float = 5.0
    threshold: Optional[float] = None
    final_balance: float = 0.0
    win_rate: float = 0.0
    sharpe_ratio: float = 0.0
    source_rank: int = 0

    @property
    def identifier(self) -> str:
        parts = [self.condition, f"lev{self.leverage:g}"]
        if self.period is not None:
            parts.append(f"p{self.period}")
        if self.multiplier is not None:
            parts.append(f"m{self.multiplier:g}")
        if self.threshold is not None:
            parts.append(f"t{self.threshold:g}")
        parts.append(f"sl{self.stop_loss_pct:g}")
        parts.append(f"rank{self.source_rank}")
        return "_".join(parts)

    def profitability_score(self) -> Tuple[float, float, float]:
        return (self.final_balance, self.win_rate, -self.source_rank)


# ---------------------------------------------------------------------------
# DATA LOADERS
# ---------------------------------------------------------------------------

def load_av_df(settings: TradingBotSettings) -> pd.DataFrame:
    db_path = settings.get('ALPHA_VANTAGE', 'database', 'database_av.db')
    table = settings.get('ALPHA_VANTAGE', 'table_name', 'SOXL_av_5min')
    start_date = settings.get('TESTING', 'start_date', '')
    end_date = settings.get('TESTING', 'end_date', '')

    conn = sqlite3.connect(db_path)
    df = pd.read_sql_query(f'SELECT * FROM {table}', conn)
    conn.close()

    if 'timestamp' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['timestamp'])
    elif 'snapshotTime' in df.columns:
        df['snapshotTime'] = pd.to_datetime(df['snapshotTime'])
    else:
        raise RuntimeError('No timestamp column found in table: ' + table)

    rename = {}
    for a, b in [('open', 'openPrice'), ('high', 'highPrice'), ('low', 'lowPrice'),
                 ('close', 'closePrice'), ('volume', 'lastTradedVolume')]:
        if a in df.columns:
            rename[a] = b
    if rename:
        df.rename(columns=rename, inplace=True)

    df.sort_values('snapshotTime', inplace=True)
    df.reset_index(drop=True, inplace=True)

    if start_date:
        start = pd.to_datetime(start_date)
        df = df[df['snapshotTime'] >= start]
    if end_date:
        end = pd.to_datetime(end_date) + pd.Timedelta(days=1)
        df = df[df['snapshotTime'] < end]

    df['date'] = df['snapshotTime'].dt.date
    df['time'] = df['snapshotTime'].dt.time
    return df


def load_top_configs(limit: int = 100) -> List[StrategyConfig]:
    if not TSV_PATH.exists():
        raise FileNotFoundError(f"Missing {TSV_PATH}")

    df = pd.read_csv(TSV_PATH, sep='\t').head(limit)
    dedup: Dict[str, StrategyConfig] = {}

    for idx, row in df.iterrows():
        params = json.loads(row['params_json'])
        key = json.dumps({'condition': row['condition'], 'params': params}, sort_keys=True)
        config = StrategyConfig(
            condition=row['condition'],
            leverage=float(params.get('leverage', 1.0)),
            period=int(params['period']) if 'period' in params else None,
            multiplier=float(params['multiplier']) if 'multiplier' in params else None,
            stop_loss_pct=float(params.get('stop_loss_pct', 5.0)),
            threshold=float(params['threshold']) if 'threshold' in params else None,
            final_balance=float(row.get('final_balance', 0.0)),
            win_rate=float(row.get('win_rate', 0.0)),
            sharpe_ratio=float(row.get('sharpe_ratio', 0.0)),
            source_rank=idx + 1,
        )
        existing = dedup.get(key)
        if not existing or config.final_balance > existing.final_balance:
            dedup[key] = config

    return sorted(dedup.values(), key=lambda cfg: cfg.final_balance, reverse=True)


# ---------------------------------------------------------------------------
# SIMULATION HELPERS
# ---------------------------------------------------------------------------

def evaluate_conditions(hist: pd.DataFrame, configs: List[StrategyConfig]) -> Dict[StrategyConfig, bool]:
    library = create_indicator_library(hist)
    conds = library.get_conditions()
    idx = len(hist) - 1
    fired: Dict[StrategyConfig, bool] = {}

    for cfg in configs:
        if cfg.condition not in conds:
            fired[cfg] = False
            continue
        try:
            if cfg.condition == 'keltner_lower_break':
                fired[cfg] = conds[cfg.condition](hist, idx, period=cfg.period, multiplier=cfg.multiplier)
            elif cfg.condition == 'rsi_oversold':
                fired[cfg] = conds[cfg.condition](hist, idx, period=cfg.period, threshold=cfg.threshold)
            else:
                fired[cfg] = False
        except Exception:
            fired[cfg] = False
    return fired


def calculate_drawdowns(balances: Iterable[float]) -> Tuple[float, float]:
    peak = None
    drawdowns = []
    for bal in balances:
        if peak is None:
            peak = bal
        peak = max(peak, bal)
        if peak == 0:
            drawdowns.append(0.0)
        else:
            drawdowns.append(((bal - peak) / peak) * 100)
    max_dd = min(drawdowns) if drawdowns else 0.0
    avg_dd = (sum(drawdowns) / len(drawdowns)) if drawdowns else 0.0
    return max_dd, avg_dd


# ---------------------------------------------------------------------------
# CORE SIMULATION (based on provided script)
# ---------------------------------------------------------------------------

def run_simulation(df: pd.DataFrame, configs: List[StrategyConfig], settings: Dict,
                   enable_crash_protection: bool) -> Dict:
    trading_days = sorted({d for d in df['date'].unique() if pd.Timestamp(d).weekday() < 5})

    balance = settings['start_balance']
    total_contributions = 0.0
    current_position: Optional[Dict] = None
    trades: List[Dict] = []
    balances: List[float] = [balance]

    if enable_crash_protection:
        daily_indicators = calculate_daily_indicators(df, CRASH_PROTECTION_CONFIG['timeframe_days'])
    else:
        daily_indicators = None

    monthly_groups: Dict[Tuple[int, int], List[pd.Timestamp]] = {}
    for day in trading_days:
        monthly_groups.setdefault((day.year, day.month), []).append(pd.Timestamp(day))
    contribution_dates = [days[0].date() for days in monthly_groups.values() if len(days) > 10]

    for current_date in trading_days:
        if current_date in contribution_dates and settings['monthly_top_up'] > 0 and balance > 0:
            balance += settings['monthly_top_up']
            total_contributions += settings['monthly_top_up']

        day_candles = df[df['date'] == current_date].sort_values('snapshotTime').reset_index(drop=True)
        if day_candles.empty:
            continue

        # Close prior position
        if current_position is not None:
            stop_price = current_position['entry_price'] * (1 - current_position['stop_loss_pct'] / 100)
            stop_hit = False
            for _, candle in day_candles.iterrows():
                if candle['lowPrice'] <= stop_price:
                    stop_hit = True
                    exit_price = stop_price
                    exit_time = candle['time']
                    break
            if not stop_hit:
                exit_price = get_price_at_time(day_candles, EXIT_TIME, 'closePrice') or current_position['entry_price']
                exit_time = EXIT_TIME

            change = (exit_price - current_position['entry_price']) / current_position['entry_price']
            spread_cost = current_position['notional_value'] * SPREAD_RATE
            gross = current_position['notional_value'] * change
            fees = calculate_trading_costs(current_position['notional_value'], 'long', is_overnight=True)
            net = gross - (fees + spread_cost)
            balance += net
            balances.append(balance)

            trades.append({
                'entry_date': current_position['entry_date'],
                'entry_time': ENTRY_TIME,
                'entry_price': current_position['entry_price'],
                'exit_date': current_date,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': 'STOP_LOSS' if stop_hit else 'NORMAL_EXIT',
                'leverage': current_position['leverage'],
                'stop_loss_pct': current_position['stop_loss_pct'],
                'notional_value': current_position['notional_value'],
                'contracts': current_position.get('contracts'),
                'fees': fees + spread_cost,
                'pnl_gross': gross,
                'pnl_net': net,
                'balance_after': balance,
                'selected_signal': current_position['config'].condition,
                'signal_rank': current_position['config'].source_rank,
                'signal_identifier': current_position['config'].identifier,
                'signal_final_balance': current_position['config'].final_balance,
            })
            current_position = None

        hist = df[df['date'] <= current_date]
        if hist.empty or balance <= 0:
            continue

        if enable_crash_protection and daily_indicators is not None:
            block, _, _ = should_block_trade(daily_indicators, current_date, CRASH_PROTECTION_CONFIG)
            if block:
                continue

        fired_map = evaluate_conditions(hist, configs)
        fired_configs = [cfg for cfg, fired in fired_map.items() if fired]
        if not fired_configs:
            continue
        fired_configs.sort(key=lambda cfg: cfg.profitability_score(), reverse=True)
        selected_config = fired_configs[0]

        entry_price = get_price_at_time(day_candles, ENTRY_TIME, 'closePrice')
        if entry_price is None:
            continue

        raw_notional = balance * settings['invest_pct'] * selected_config.leverage
        contracts = int(raw_notional / entry_price) if entry_price else 0
        if contracts < MIN_CONTRACTS:
            continue

        notional_value = contracts * entry_price
        current_position = {
            'entry_date': current_date,
            'entry_price': entry_price,
            'notional_value': notional_value,
            'contracts': contracts,
            'leverage': selected_config.leverage,
            'stop_loss_pct': selected_config.stop_loss_pct,
            'config': selected_config,
        }

        after_hours = day_candles[(day_candles['time'] > ENTRY_TIME)]
        if not after_hours.empty:
            stop_price_same_day = entry_price * (1 - selected_config.stop_loss_pct / 100)
            for _, candle in after_hours.iterrows():
                if candle['lowPrice'] <= stop_price_same_day:
                    change = (stop_price_same_day - entry_price) / entry_price
                    spread_cost = notional_value * SPREAD_RATE
                    gross = notional_value * change
                    fees = calculate_trading_costs(notional_value, 'long', is_overnight=False)
                    net = gross - (fees + spread_cost)
                    balance += net
                    balances.append(balance)

                    trades.append({
                        'entry_date': current_date,
                        'entry_time': ENTRY_TIME,
                        'entry_price': entry_price,
                        'exit_date': current_date,
                        'exit_time': candle['time'],
                        'exit_price': stop_price_same_day,
                        'exit_reason': 'STOP_LOSS',
                        'leverage': selected_config.leverage,
                        'stop_loss_pct': selected_config.stop_loss_pct,
                        'notional_value': notional_value,
                        'contracts': contracts,
                        'fees': fees + spread_cost,
                        'pnl_gross': gross,
                        'pnl_net': net,
                        'balance_after': balance,
                        'selected_signal': selected_config.condition,
                        'signal_rank': selected_config.source_rank,
                        'signal_identifier': selected_config.identifier,
                        'signal_final_balance': selected_config.final_balance,
                    })
                    current_position = None
                    break

    final_balance = max(balance, 0)
    wins = sum(1 for t in trades if t['pnl_net'] > 0)
    losses = len(trades) - wins
    max_dd, avg_dd = calculate_drawdowns(balances)

    return {
        'final_balance': final_balance,
        'trades': len(trades),
        'wins': wins,
        'losses': losses,
        'max_drawdown_pct': max_dd,
        'avg_drawdown_pct': avg_dd,
    }


# ---------------------------------------------------------------------------
# ENTRY POINT
# ---------------------------------------------------------------------------

def main() -> None:
    settings = TradingBotSettings('settings.txt')
    df = load_av_df(settings)

    finance = settings.config['FINANCE'] if settings.has_section('FINANCE') else {}
    sim_settings = {
        'start_balance': float(finance.get('start_balance', 500.0)),
        'monthly_top_up': float(finance.get('monthly_top_up', 100.0)),
        'invest_pct': float(finance.get('invest_pct', 0.99)),
    }

    configs = load_top_configs(limit=100)

    print(f"Loaded {len(df):,} candles\n")
    print("Strategy Backtest Summary")
    print("==========================")

    for enable_protection, label in (
        (True, 'Test8 - SOXL Top 100 WITH Protection'),
        (False, 'Test8 - SOXL Top 100 NO Protection'),
    ):
        result = run_simulation(df, configs, sim_settings, enable_protection)
        print(
            f"{label:<40}  ${result['final_balance']:>12,.0f}  | "
            f"trades={result['trades']}, W/L={result['wins']}/{result['losses']}"
        )


if __name__ == '__main__':
    main()


