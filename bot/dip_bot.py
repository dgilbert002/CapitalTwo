#!/usr/bin/env python3
"""Standalone dip-strategy trading engine for Capital.com.

    python -m bot.dip_bot            # uses settings.txt; paper mode by default

Daily cycle (NYSE calendar, so holidays and 13:00 half-days are handled):
  T-120s  prefetch ~7 days of 1-min candles (slow part, done early)
  T-30s   close THIS bot's epic positions; re-check until none remain
  T-15s   fetch the last minutes, build 5-min candles exactly like the
          backtester, decide; if BUY and the close step succeeded, open a
          long sized to `leverage` x equity with an emergency stop
Every order/close is confirmed. State is saved per trading day in
state/dip_bot_state.json so restarts neither double-trade nor forget.

settings.txt [DIP_BOT] (all optional):
  epic = SOXL
  leverage = 3            (hard-capped at 5 = Capital.com 20% margin)
  invest_pct = 0.95       (fraction of equity used, leaves margin buffer)
  emergency_stop_pct = 15
  trend_sma_days = 200    (below the N-day average use trend_below_mult x leverage; 0 = off)
  trend_below_mult = 0.5  (0 = no trades below the average)
  brake_dd_pct = 20       (account drawdown that pauses trading; 0 = off)
  brake_pause_days = 20
  paper = true            (true: no orders, paper trades logged to CSV)
"""
import configparser
import json
import logging
import math
import os
import sys
import time
from pathlib import Path

import pandas as pd
import pandas_market_calendars as mcal

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from bot import dip_strategy as DS  # noqa: E402
from bot.capital_rest import CapitalError, CapitalREST  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'state' / 'dip_bot_state.json'
PAPER_LOG = ROOT / 'Results' / 'dip_bot_paper_trades.csv'
MAX_LEVERAGE = 5.0
T_PREFETCH, T_CLOSE, T_OPEN, T_LAST = 120, 30, 15, 3   # seconds before close

log = logging.getLogger('dip_bot')


# ------------------------------------------------------------------ config / state
def load_config():
    c = configparser.ConfigParser(strict=False)
    c.read(ROOT / 'settings.txt', encoding='utf-8')
    d = c['DIP_BOT'] if c.has_section('DIP_BOT') else {}
    env = c.get('API_CONFIG', 'environment', fallback='demo').strip().lower()
    cfg = {
        'api_key': c.get('CREDENTIALS', 'api_key'), 'email': c.get('CREDENTIALS', 'email'),
        'password': c.get('CREDENTIALS', 'password'), 'environment': env,
        'account_id': c.get('ENV_ACCOUNTS', env, fallback=None),
        'epic': d.get('epic', 'SOXL'),
        'leverage': min(float(d.get('leverage', 3)), MAX_LEVERAGE),
        'invest_pct': min(float(d.get('invest_pct', 0.95)), 0.99),
        'stop_pct': float(d.get('emergency_stop_pct', 15)),
        'paper': str(d.get('paper', 'true')).lower() in ('1', 'true', 'yes'),
        'trend_days': int(d.get('trend_sma_days', DS.TREND_SMA_DAYS)),
        'trend_mult': float(d.get('trend_below_mult', DS.TREND_BELOW_MULT)),
        'brake_dd': float(d.get('brake_dd_pct', DS.BRAKE_DD_PCT)),
        'brake_pause': int(d.get('brake_pause_days', DS.BRAKE_PAUSE_DAYS)),
    }
    return cfg


def load_state():
    try:
        return json.loads(STATE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {'days': {}, 'paper_position': None, 'paper_equity': None}


def save_state(st):
    STATE.parent.mkdir(exist_ok=True)
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(st, indent=1, default=str))
    tmp.replace(STATE)


# ------------------------------------------------------------------ engine
class DipBot:
    def __init__(self, cfg):
        self.cfg = cfg
        self.api = CapitalREST(cfg['api_key'], cfg['email'], cfg['password'], cfg['environment'])
        self.cal = mcal.get_calendar('NYSE')
        self.st = load_state()
        self.history = None
        self.daily = None

    def day(self, d):
        return self.st['days'].setdefault(str(d), {})

    def session_close(self, now_utc):
        s = self.cal.schedule(start_date=(now_utc - pd.Timedelta(days=1)).date(),
                              end_date=(now_utc + pd.Timedelta(days=10)).date())
        s = s[s['market_close'] > now_utc - pd.Timedelta(seconds=5)]
        return s.index[0].date(), s['market_close'].iloc[0]

    def connect(self):
        self.api.login()
        if self.cfg['account_id']:
            self.api.switch_account(self.cfg['account_id'])
        acc = self.api.account(self.cfg['account_id']) if self.cfg['account_id'] else self.api.accounts()[0]
        log.info('Connected %s account %s (%s) balance %s %s | epic %s lev %.1fx stop %.0f%% | %s',
                 self.cfg['environment'], acc['accountId'], acc.get('accountName'), acc['balance'].get('balance'),
                 acc.get('currency'), self.cfg['epic'], self.cfg['leverage'], self.cfg['stop_pct'],
                 'PAPER MODE (no orders)' if self.cfg['paper'] else 'LIVE ORDERS')

    def equity(self):
        if self.cfg['paper']:
            if self.st.get('paper_equity') is None:
                acc = self.api.account(self.cfg['account_id']) if self.cfg['account_id'] else self.api.accounts()[0]
                self.st['paper_equity'] = float(acc['balance']['balance'])
            return self.st['paper_equity']
        acc = self.api.account(self.cfg['account_id']) if self.cfg['account_id'] else self.api.accounts()[0]
        return float(acc['balance']['balance'])

    # -- steps
    def prefetch(self, now_utc):
        self.history = self.api.candles_1m(self.cfg['epic'], now_utc - pd.Timedelta(days=7), now_utc)
        log.info('Prefetched %d 1-min candles (to %s ET)', len(self.history),
                 self.history['t'].iloc[-1] if len(self.history) else '-')
        if self.cfg['trend_days']:
            h1 = self.api.candles(self.cfg['epic'], now_utc - pd.Timedelta(days=int(self.cfg['trend_days'] * 1.6) + 10),
                                  now_utc, 'HOUR', pd.Timedelta(days=40))
            self.daily = DS.daily_closes_from_hourly(h1)
            log.info('Prefetched %d daily closes for the %d-day trend filter', len(self.daily), self.cfg['trend_days'])

    def close_positions(self, d):
        rec = self.day(d)
        if self.cfg['paper']:
            pp = self.st.get('paper_position')
            if pp:
                bid = float(self.api.market(self.cfg['epic'])['snapshot']['bid'])
                self._paper_close(pp, bid, 'T-30s')
            rec['closed'] = True
            self._brake_after_close()
            return
        for attempt in range(5):
            ps = self.api.positions(self.cfg['epic'])
            if not ps:
                rec['closed'] = True
                log.info('No %s positions open', self.cfg['epic'])
                self._brake_after_close()
                return
            for p in ps:
                did = p['position']['dealId']
                try:
                    c = self.api.close(did)
                    log.info('Closed %s size %s at %s', did, p['position']['size'], c.get('level'))
                except CapitalError as e:
                    log.error('Close %s failed (attempt %d): %s', did, attempt + 1, e)
            time.sleep(0.5)
        rec['closed'] = bool(not self.api.positions(self.cfg['epic']))
        if not rec['closed']:
            log.critical('Positions still open after 5 close attempts - will NOT open a new trade today')

    def _brake_after_close(self):
        prot = self.st.setdefault('protection', {})
        before = prot.get('brake_days_left', 0)
        DS.brake_update(prot, self.equity(), self.cfg['brake_dd'], self.cfg['brake_pause'])
        if prot.get('brake_days_left', 0) > before:
            log.warning('BRAKE: account fell more than %.0f%% from its peak - no new trades for %d trading days',
                        self.cfg['brake_dd'], self.cfg['brake_pause'])

    def decide_and_open(self, d, now_utc):
        rec = self.day(d)
        rec['decided'] = True
        save_state(self.st)
        if DS.brake_blocks(self.st.setdefault('protection', {})):
            rec['decision'] = f"SKIP: brake active ({self.st['protection']['brake_days_left']} more days)"
            log.warning(rec['decision'])
            return
        recent = self.api.candles_1m(self.cfg['epic'], now_utc - pd.Timedelta(minutes=30), now_utc)
        m1 = pd.concat([self.history if self.history is not None else pd.DataFrame(), recent])
        m1 = m1.drop_duplicates('t', keep='last').sort_values('t')
        close_et = self._close_et(d)
        m1 = m1[m1['t'] < close_et - pd.Timedelta(minutes=1)]   # drop the still-forming last minute
        m5 = DS.build_5min(m1)
        expect = close_et - pd.Timedelta(minutes=5)
        if m5.empty or m5['t'].iloc[-1] != expect:
            rec['decision'] = f'SKIP: stale data, last 5-min candle {m5["t"].iloc[-1] if len(m5) else None}, expected {expect}'
            log.error(rec['decision'])
            return
        dec = DS.decide(m5)
        rec['decision'] = ('BUY ' if dec.buy else 'NO TRADE ') + dec.reason
        lev = self.cfg['leverage']
        if dec.buy and self.cfg['trend_days']:
            if self.daily is None or len(self.daily) < self.cfg['trend_days'] - 1:
                rec['decision'] = f'SKIP: trend filter has no data ({0 if self.daily is None else len(self.daily)} days)'
                dec.buy = False
            elif DS.below_trend(self.daily[self.daily.index < pd.Timestamp(d)], float(m5['close'].iloc[-1]),
                                self.cfg['trend_days']):
                lev_mult = self.cfg['trend_mult']
                if lev_mult <= 0:
                    rec['decision'] = f"NO TRADE (trend filter: below {self.cfg['trend_days']}-day average) " + dec.reason
                    dec.buy = False
                else:
                    lev *= lev_mult
                    rec['decision'] += f" | below {self.cfg['trend_days']}-day average: leverage x{lev_mult}"
        log.info('Decision: %s', rec['decision'])
        if not dec.buy:
            return
        if not rec.get('closed'):
            log.error('Close step did not complete - not opening')
            return
        mk = self.api.market(self.cfg['epic'])
        snap, rules = mk['snapshot'], mk['dealingRules']
        if snap.get('marketStatus') != 'TRADEABLE':
            rec['decision'] += f' | market {snap.get("marketStatus")} - skipped'
            log.error(rec['decision'])
            return
        ask, bid = float(snap['offer']), float(snap['bid'])
        eq = self.equity()
        step = float(rules['minSizeIncrement']['value'])
        size = math.floor(eq * self.cfg['invest_pct'] * lev / ask / step) * step
        size = int(size) if step >= 1 else round(size, 6)
        if size < float(rules['minDealSize']['value']):
            rec['decision'] += f' | equity {eq:.2f} too small for min size'
            log.error(rec['decision'])
            return
        stop = round(bid * (1 - self.cfg['stop_pct'] / 100), 2)
        log.info('Opening BUY %s x%s at ~%.2f (%.2fx of equity %.2f), stop %.2f',
                 self.cfg['epic'], size, ask, size * ask / eq, eq, stop)
        if self.cfg['paper']:
            self.st['paper_position'] = {'date': str(d), 'size': size, 'entry': ask, 'stop': stop}
            rec['opened'] = {'paper': True, 'size': size, 'entry': ask}
            return
        c = self.api.open_long(self.cfg['epic'], size, stop)
        rec['opened'] = {'dealId': (c.get('affectedDeals') or [{}])[0].get('dealId'), 'level': c.get('level'),
                         'stopLevel': c.get('stopLevel'), 'size': c.get('size')}
        log.info('Order CONFIRMED %s', rec['opened'])

    def _paper_close(self, pp, bid, why):
        eq0 = self.st['paper_equity']
        stop_hit = self._paper_stop_hit(pp)
        exit_px = pp['stop'] if stop_hit else bid
        pnl = pp['size'] * (exit_px - pp['entry'])
        self.st['paper_equity'] = eq0 + pnl
        row = pd.DataFrame([{**pp, 'exit': exit_px, 'exit_reason': 'stop' if stop_hit else why,
                             'pnl': round(pnl, 2), 'equity': round(eq0 + pnl, 2),
                             'closed_at': pd.Timestamp.now(tz='America/New_York')}])
        PAPER_LOG.parent.mkdir(exist_ok=True)
        row.to_csv(PAPER_LOG, mode='a', header=not PAPER_LOG.exists(), index=False)
        log.info('PAPER close: entry %.2f exit %.2f pnl %+.2f equity %.2f', pp['entry'], exit_px, pnl, eq0 + pnl)
        self.st['paper_position'] = None

    def _paper_stop_hit(self, pp):
        try:
            since = pd.Timestamp(pp['date']).tz_localize('America/New_York').tz_convert('UTC').tz_localize(None) + pd.Timedelta(hours=20)
            m1 = self.api.candles_1m(self.cfg['epic'], since, pd.Timestamp.utcnow().tz_localize(None))
            return bool(len(m1) and (m1['bid_low'] <= pp['stop']).any())
        except CapitalError:
            return False

    def _close_et(self, d):
        s = self.cal.schedule(start_date=d, end_date=d)
        return s['market_close'].iloc[0].tz_convert('America/New_York').tz_localize(None)

    # -- main loop
    def run(self):
        self.connect()
        while True:
            try:
                now = pd.Timestamp.now(tz='UTC')
                d, close = self.session_close(now)
                left = (close - now).total_seconds()
                rec = self.day(d)
                if left > T_PREFETCH + 60:
                    time.sleep(min(60, left - T_PREFETCH - 30))
                    continue
                if left <= T_PREFETCH and not rec.get('prefetched'):
                    self.prefetch(now)
                    rec['prefetched'] = True
                if left <= T_CLOSE and not rec.get('close_done'):
                    rec['close_done'] = True
                    self.close_positions(d)
                    save_state(self.st)
                if T_LAST < left <= T_OPEN and not rec.get('decided'):
                    self.decide_and_open(d, now)
                    save_state(self.st)
                elif left <= T_LAST and not rec.get('decided'):
                    rec['decided'] = True
                    rec['decision'] = 'SKIP: missed the T-15s window'
                    log.error(rec['decision'])
                    save_state(self.st)
                if left <= 0:
                    self.history = None
                    time.sleep(10)
                    continue
                time.sleep(0.25)
            except CapitalError as e:
                log.error('API error: %s', e)
                time.sleep(2)
            except Exception:
                log.exception('Unexpected error')
                time.sleep(5)


def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(ROOT / 'dip_bot.log', encoding='utf-8')])
    DipBot(load_config()).run()


if __name__ == '__main__':
    main()
