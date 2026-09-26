"""Dip strategy shared by the live bot (bot/dip_bot.py) and the backtester.

Rule (chosen from ~80M honest backtests, see Scripts/mega_sweep.py):
  At T-15s before the US close, on 5-minute mid-price candles built from
  1-minute Capital.com candles (the still-forming 15:59 minute excluded), BUY if
    * price is down more than ROC_DROP_PCT over the last ROC_BARS candles, and
    * the slow MACD(19/39/9) histogram is below -MACD_FRAC x price.
  Hold overnight; close at T-30s before the next close.

Both the live bot and the backtester must call build_5min() and decide() so a
live decision is exactly what was backtested.
"""
from dataclasses import dataclass

import pandas as pd

ROC_BARS = 78          # ~1 regular session of 5-min candles
ROC_DROP_PCT = 2.0
MACD_FAST, MACD_SLOW, MACD_SIGNAL = 19, 39, 9
MACD_FRAC = 0.001
MIN_HISTORY_BARS = 400  # EMA warm-up; decisions with less history are refused


@dataclass
class Decision:
    buy: bool
    roc_pct: float
    macd_hist_frac: float
    last_bar: pd.Timestamp
    bars: int
    reason: str


def build_5min(m1: pd.DataFrame) -> pd.DataFrame:
    """1-minute candles -> 5-minute mid candles.

    m1 needs columns: t (US/Eastern naive timestamp of bar start) and
    bid_open/high/low/close + ask_open/high/low/close. Weekends and minutes
    outside 04:00-20:00 ET are dropped, and so is every 15:59 minute so the
    15:55 candle equals what is visible at 15:59:45.
    """
    x = m1.copy()
    x['t'] = pd.to_datetime(x['t'])
    tt = x['t'].dt.time
    x = x[(x['t'].dt.weekday < 5) & (tt >= pd.Timestamp('04:00').time())
          & (tt < pd.Timestamp('20:00').time()) & (tt != pd.Timestamp('15:59').time())]
    for k in ('open', 'high', 'low', 'close'):
        x[k] = (x[f'bid_{k}'] + x[f'ask_{k}']) / 2
    out = (x.set_index('t')[['open', 'high', 'low', 'close']]
           .resample('5min', label='left', closed='left')
           .agg({'open': 'first', 'high': 'max', 'low': 'min', 'close': 'last'})
           .dropna().reset_index())
    return out


def indicators(close: pd.Series) -> pd.DataFrame:
    roc = (close / close.shift(ROC_BARS) - 1) * 100
    macd = close.ewm(span=MACD_FAST, adjust=False).mean() - close.ewm(span=MACD_SLOW, adjust=False).mean()
    hist = (macd - macd.ewm(span=MACD_SIGNAL, adjust=False).mean()) / close
    return pd.DataFrame({'roc_pct': roc, 'macd_hist_frac': hist})


def signal_series(m5: pd.DataFrame) -> pd.Series:
    ind = indicators(m5['close'])
    return (ind['roc_pct'] < -ROC_DROP_PCT) & (ind['macd_hist_frac'] < -MACD_FRAC)


def decide(m5: pd.DataFrame) -> Decision:
    """Decision on the last candle of m5 (the partial 15:55 candle when live)."""
    if len(m5) < MIN_HISTORY_BARS:
        return Decision(False, float('nan'), float('nan'), m5['t'].iloc[-1] if len(m5) else pd.NaT,
                        len(m5), f'not enough history ({len(m5)} bars)')
    ind = indicators(m5['close']).iloc[-1]
    buy = bool(ind['roc_pct'] < -ROC_DROP_PCT and ind['macd_hist_frac'] < -MACD_FRAC)
    reason = (f"ROC{ROC_BARS}={ind['roc_pct']:+.2f}% (need < -{ROC_DROP_PCT}%), "
              f"MACD hist={ind['macd_hist_frac']*100:+.3f}% (need < -{MACD_FRAC*100:.2f}%)")
    return Decision(buy, float(ind['roc_pct']), float(ind['macd_hist_frac']), m5['t'].iloc[-1], len(m5), reason)
