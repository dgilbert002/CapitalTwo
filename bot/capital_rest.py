"""Minimal, strict Capital.com REST client for the dip bot.

Every call has a timeout, every order/close is confirmed via /confirms, and
errors raise instead of being swallowed. Replaces the capitalcom SDK, whose
live client lacks the trading methods bot/api.py relies on.
"""
import logging
import time
from typing import Dict, List, Optional

import pandas as pd
import requests

log = logging.getLogger('capital_rest')

URLS = {'demo': 'https://demo-api-capital.backend-capital.com/api/v1',
        'live': 'https://api-capital.backend-capital.com/api/v1'}
TIMEOUT = 15


class CapitalError(RuntimeError):
    pass


class CapitalREST:
    def __init__(self, api_key: str, identifier: str, password: str, environment: str = 'demo'):
        if environment not in URLS:
            raise ValueError(f'environment must be demo or live, got {environment!r}')
        self.base = URLS[environment]
        self.environment = environment
        self._key, self._id, self._pw = api_key, identifier, password
        self._hdr: Dict[str, str] = {}
        self._login_at = 0.0
        self.s = requests.Session()

    # ---------------------------------------------------------------- session
    def login(self) -> None:
        r = self.s.post(f'{self.base}/session', timeout=TIMEOUT, headers={'X-CAP-API-KEY': self._key},
                        json={'identifier': self._id, 'password': self._pw, 'encryptedPassword': False})
        if r.status_code != 200:
            raise CapitalError(f'login failed {r.status_code}: {r.text[:200]}')
        self._hdr = {'X-SECURITY-TOKEN': r.headers['X-SECURITY-TOKEN'], 'CST': r.headers['CST']}
        self._login_at = time.time()

    def _req(self, method: str, path: str, retry_auth: bool = True, **kw) -> dict:
        # sessions expire after 10 min idle; refresh proactively
        if not self._hdr or time.time() - self._login_at > 8 * 60:
            self.login()
        r = self.s.request(method, f'{self.base}{path}', headers=self._hdr, timeout=TIMEOUT, **kw)
        if r.status_code == 401 and retry_auth:
            self.login()
            return self._req(method, path, retry_auth=False, **kw)
        if r.status_code >= 400:
            raise CapitalError(f'{method} {path} -> {r.status_code}: {r.text[:300]}')
        self._login_at = time.time()
        return r.json() if r.content else {}

    def switch_account(self, account_id: str) -> None:
        cur = self._req('GET', '/session').get('currentAccountId') or self._req('GET', '/session').get('accountId')
        if str(cur) == str(account_id):
            return
        self._req('PUT', '/session', json={'accountId': str(account_id)})
        now = self._req('GET', '/session')
        if str(now.get('currentAccountId') or now.get('accountId')) != str(account_id):
            raise CapitalError(f'account switch to {account_id} did not take effect: {now}')

    def accounts(self) -> List[dict]:
        return self._req('GET', '/accounts')['accounts']

    def account(self, account_id: str) -> dict:
        for a in self.accounts():
            if str(a['accountId']) == str(account_id):
                return a
        raise CapitalError(f'account {account_id} not found')

    # ---------------------------------------------------------------- market
    def market(self, epic: str) -> dict:
        return self._req('GET', f'/markets/{epic}')

    def candles_1m(self, epic: str, start_utc: pd.Timestamp, end_utc: pd.Timestamp) -> pd.DataFrame:
        """1-minute bid/ask candles, US/Eastern naive bar-start timestamps."""
        rows, cur = [], start_utc
        while cur < end_utc:
            nxt = min(cur + pd.Timedelta(hours=16), end_utc)
            try:
                j = self._req('GET', f'/prices/{epic}', params={
                    'resolution': 'MINUTE', 'max': 1000,
                    'from': cur.strftime('%Y-%m-%dT%H:%M:%S'), 'to': nxt.strftime('%Y-%m-%dT%H:%M:%S')})
            except CapitalError as e:
                if '404' not in str(e):   # 404 = no prices in window
                    raise
                j = {'prices': []}
            for p in j.get('prices', []):
                rows.append({'t': pd.Timestamp(p['snapshotTimeUTC']).tz_localize('UTC').tz_convert('America/New_York').tz_localize(None),
                             **{f'bid_{k}': p[f'{k}Price']['bid'] for k in ('open', 'high', 'low', 'close')},
                             **{f'ask_{k}': p[f'{k}Price']['ask'] for k in ('open', 'high', 'low', 'close')}})
            cur = nxt
        return pd.DataFrame(rows).drop_duplicates('t').sort_values('t').reset_index(drop=True) if rows else pd.DataFrame()

    # ---------------------------------------------------------------- trading
    def positions(self, epic: Optional[str] = None) -> List[dict]:
        ps = self._req('GET', '/positions')['positions']
        return [p for p in ps if epic is None or p['market']['epic'] == epic]

    def confirm(self, deal_ref: str, wait_s: float = 10.0) -> dict:
        end = time.time() + wait_s
        last = None
        while time.time() < end:
            try:
                c = self._req('GET', f'/confirms/{deal_ref}')
                if c.get('dealStatus') in ('ACCEPTED', 'REJECTED'):
                    return c
                last = c
            except CapitalError as e:
                last = str(e)
            time.sleep(0.5)
        raise CapitalError(f'no confirmation for {deal_ref}: {last}')

    def open_long(self, epic: str, size: int, stop_level: Optional[float]) -> dict:
        body = {'epic': epic, 'direction': 'BUY', 'size': size, 'guaranteedStop': False}
        if stop_level is not None:
            body['stopLevel'] = stop_level
        ref = self._req('POST', '/positions', json=body)['dealReference']
        c = self.confirm(ref)
        if c.get('dealStatus') != 'ACCEPTED':
            raise CapitalError(f'open REJECTED: {c.get("reason")} {c}')
        return c

    def close(self, deal_id: str) -> dict:
        ref = self._req('DELETE', f'/positions/{deal_id}')['dealReference']
        c = self.confirm(ref)
        if c.get('dealStatus') != 'ACCEPTED':
            raise CapitalError(f'close REJECTED: {c.get("reason")} {c}')
        return c
