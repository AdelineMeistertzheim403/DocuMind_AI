"""Versioned HMAC confirmation ledger for explicitly provisioned local use."""
from datetime import datetime, timezone
import hashlib
import hmac
import json
import re
from typing import Protocol
from uuid import UUID

from .lifecycle_durability import ConfirmationStore, canonical


class ConfirmationBackend(Protocol):
    def prepare(self, operation: dict) -> str: ...
    def confirm(self, operation: dict) -> str: ...
    def verify(self, operation: dict) -> str: ...
    def reconcile(self, operation: dict) -> str: ...


STATES = ('prepared', 'confirmed', 'authorized', 'result_recorded', 'closed')


class AuthenticatedConfirmationStore:
    """Key is supplied separately and never persisted in the ledger."""

    def __init__(self, path, key: bytes, domain: str):
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError('A separate 256-bit key is required')
        if not re.fullmatch(r'[a-z0-9-]{1,64}', domain):
            raise ValueError('Invalid confirmation domain')
        self.store = ConfirmationStore(path)
        self.key = key
        self.domain = domain

    def initialize(self):
        self.store.initialize()
        with self.store.connection() as db:
            db.execute('''CREATE TABLE synthetic_transitions (
                operation TEXT NOT NULL, sequence INTEGER NOT NULL,
                envelope TEXT NOT NULL, tag TEXT NOT NULL,
                PRIMARY KEY (operation, sequence))''')
            db.execute('''CREATE TABLE hold_mirrors (
                hold_id TEXT PRIMARY KEY, envelope TEXT NOT NULL, tag TEXT NOT NULL)''')
            db.execute('''CREATE TABLE authenticated_header (
                id INTEGER PRIMARY KEY CHECK(id=1), domain TEXT NOT NULL, tag TEXT NOT NULL)''')
            db.execute('INSERT INTO authenticated_header VALUES (1,?,?)',
                       (self.domain, self._header_tag()))
            db.execute('PRAGMA user_version=2')

    def _header_tag(self):
        payload = canonical({'version': 2, 'domain': self.domain, 'purpose': 'key-check'})
        return hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()

    def _check_header(self, db):
        if db.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('Authenticated confirmation schema required')
        row = db.execute('SELECT domain,tag FROM authenticated_header WHERE id=1').fetchone()
        if (row is None or row['domain'] != self.domain or not isinstance(row['tag'], str)
                or not hmac.compare_digest(row['tag'], self._header_tag())):
            raise ValueError('Confirmation key authentication failed')

    def check_header(self):
        with self.store.connection() as db:
            self._check_header(db)

    def _identity(self, operation):
        if not isinstance(operation, dict) or set(operation) != {'id', 'type', 'target', 'receipt_sha256'}:
            raise ValueError('Incomplete operation')
        identifier = str(UUID(operation['id']))
        target = str(UUID(operation['target']))
        if identifier != operation['id'] or target != operation['target']:
            raise ValueError('Canonical opaque UUIDs required')
        if operation['type'] not in ('account_erasure', 'account_deactivation', 'document_erasure'):
            raise ValueError('Unsupported mutation')
        if not re.fullmatch(r'[0-9a-f]{64}', operation['receipt_sha256']):
            raise ValueError('Invalid receipt fingerprint')
        return {'id': identifier, 'type': operation['type'], 'target': target,
                'receipt_sha256': operation['receipt_sha256']}

    def _read(self, db, operation):
        self._check_header(db)
        identity = self._identity(operation)
        rows = db.execute('SELECT sequence,envelope,tag FROM synthetic_transitions '
                          'WHERE operation=? ORDER BY sequence', (identity['id'],)).fetchall()
        previous = ''
        for index, row in enumerate(rows):
            envelope = json.loads(row['envelope'])
            if (index >= len(STATES) or row['sequence'] != index + 1 or
                    set(envelope) != {'version', 'domain', 'operation', 'state', 'at', 'previous'} or
                    envelope['version'] != 2 or envelope['domain'] != self.domain or
                    envelope['operation'] != identity or envelope['state'] != STATES[index] or
                    envelope['previous'] != previous or canonical(envelope) != row['envelope']):
                raise ValueError('Conflicting or incomplete confirmation history')
            timestamp = datetime.fromisoformat(envelope['at'])
            if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                raise ValueError('Confirmation timestamp lacks timezone')
            expected = hmac.new(self.key, row['envelope'].encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(row['tag'], expected):
                raise ValueError('Confirmation authentication failed')
            previous = row['tag']
        return len(rows), previous

    def _advance(self, operation, state, *, once=False):
        desired = STATES.index(state)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            count, previous = self._read(db, operation)
            if count > desired:
                if once:
                    raise ValueError('Mutation state requires reconciliation')
            elif count != desired:
                raise ValueError('Previous confirmation transition missing')
            else:
                envelope = canonical({'version': 2, 'domain': self.domain,
                    'operation': self._identity(operation), 'state': state,
                    'at': datetime.now(timezone.utc).isoformat(), 'previous': previous})
                tag = hmac.new(self.key, envelope.encode(), hashlib.sha256).hexdigest()
                db.execute('INSERT INTO synthetic_transitions VALUES (?,?,?,?)',
                           (operation['id'], count + 1, envelope, tag))
        current = self.verify(operation)
        if STATES.index(current) < desired:
            raise ValueError('Confirmation transition not durable')
        return current

    def prepare(self, operation):
        return self._advance(operation, 'prepared')

    def confirm(self, operation):
        return self._advance(operation, 'confirmed')

    def authorize(self, operation):
        return self._advance(operation, 'authorized')

    def authorize_once(self, operation):
        return self._advance(operation, 'authorized', once=True)

    def record_result(self, operation):
        return self._advance(operation, 'result_recorded')

    def close(self, operation):
        return self._advance(operation, 'closed')

    def verify(self, operation):
        with self.store.connection() as db:
            count, _ = self._read(db, operation)
        if not count:
            raise ValueError('Confirmation missing')
        return STATES[count - 1]

    def reconcile(self, operation):
        return self.verify(operation)

    def _hold_mirrors(self, db):
        self._check_header(db)
        result = {}
        for row in db.execute('SELECT hold_id,envelope,tag FROM hold_mirrors ORDER BY hold_id'):
            envelope = json.loads(row['envelope'])
            if (not isinstance(envelope, dict) or set(envelope) != {'version', 'domain', 'snapshot'}
                    or envelope['version'] != 2 or envelope['domain'] != self.domain
                    or not isinstance(envelope['snapshot'], dict)
                    or envelope['snapshot'].get('id') != row['hold_id']
                    or canonical(envelope) != row['envelope']):
                raise ValueError('Conflicting hold confirmation')
            tag = hmac.new(self.key, row['envelope'].encode(), hashlib.sha256).hexdigest()
            if not isinstance(row['tag'], str) or not hmac.compare_digest(row['tag'], tag):
                raise ValueError('Hold authentication failed')
            result[row['hold_id']] = envelope['snapshot']
        return result

    def verify_holds(self, expected):
        with self.store.connection() as db:
            if self._hold_mirrors(db) != expected:
                raise ValueError('Hold registries differ')

    def update_hold(self, expected, snapshot):
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if self._hold_mirrors(db) != expected:
                raise ValueError('Hold registries differ')
            envelope = canonical({'version': 2, 'domain': self.domain, 'snapshot': snapshot})
            tag = hmac.new(self.key, envelope.encode(), hashlib.sha256).hexdigest()
            db.execute('INSERT INTO hold_mirrors VALUES (?,?,?) '
                       'ON CONFLICT(hold_id) DO UPDATE SET envelope=excluded.envelope,tag=excluded.tag',
                       (snapshot['id'], envelope, tag))
