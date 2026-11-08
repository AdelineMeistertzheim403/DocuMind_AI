"""Scoped persistent holds; strict mutations hold the SQLite writer fence."""
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from uuid import UUID

from .lifecycle_durability import ConfirmationStore, canonical, separate_directories
from .lifecycle_retention_policy import _time, receipt_expiry_plan


class ActiveHoldError(ValueError):
    pass


class HoldStore:
    def __init__(self, path, authenticated):
        self.store = ConfirmationStore(path)
        self.path = self.store.path
        self.authenticated = authenticated
        separate_directories((self.path.parent, authenticated.store.path.parent))

    def initialize(self):
        self.store.initialize()
        with self.store.connection() as db:
            db.executescript('''
                CREATE TABLE holds_v2 (
                    id TEXT PRIMARY KEY, scope_kind TEXT NOT NULL, scope_id TEXT NOT NULL,
                    content TEXT NOT NULL, released INTEGER NOT NULL CHECK(released IN (0,1)));
                CREATE TABLE hold_decisions_v2 (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, hold_id TEXT NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL,
                    decision_id TEXT, evidence_sha256 TEXT);
                PRAGMA user_version=2;
            ''')

    @staticmethod
    def _validate(hold, at):
        if not isinstance(hold, dict) or set(hold) != {
            'id', 'responsible_id', 'scope_id', 'scope_kind', 'reason',
            'reviewed_at', 'review_at', 'ends_at', 'end_event',
        } or hold['scope_kind'] not in ('account', 'owner', 'document'):
            raise ValueError('Incomplete scoped hold')
        for field in ('id', 'responsible_id', 'scope_id'):
            if not isinstance(hold[field], str) or str(UUID(hold[field])) != hold[field]:
                raise ValueError('Canonical hold identity required')
        receipt_expiry_plan(at, at, None, coverage_attested=False, exceptions_complete=True,
                            holds=[{key: value for key, value in hold.items() if key != 'scope_kind'}])

    def _snapshots(self, db):
        self._schema(db)
        snapshots = {}
        rows = db.execute('SELECT * FROM holds_v2 ORDER BY id').fetchall()
        for row in rows:
            hold = json.loads(row['content'])
            if (not isinstance(hold, dict) or canonical(hold) != row['content']
                    or hold.get('id') != row['id'] or hold.get('scope_kind') != row['scope_kind']
                    or hold.get('scope_id') != row['scope_id']):
                raise ValueError('Conflicting hold scope')
            events = db.execute('SELECT action,actor,at,decision_id,evidence_sha256 FROM hold_decisions_v2 '
                                'WHERE hold_id=? ORDER BY sequence', (row['id'],)).fetchall()
            actions = [event['action'] for event in events]
            if actions != (['created', 'released'] if row['released'] else ['created']):
                raise ValueError('Incomplete hold decision history')
            created = dict(events[0])
            if created['actor'] != hold.get('responsible_id') or created['decision_id'] or created['evidence_sha256']:
                raise ValueError('Invalid hold creation')
            _time(datetime.fromisoformat(created['at']))
            release = dict(events[1]) if row['released'] else None
            if release:
                for field in ('actor', 'decision_id'):
                    if not isinstance(release[field], str) or str(UUID(release[field])) != release[field]:
                        raise ValueError('Invalid hold release identity')
                if (not isinstance(release['evidence_sha256'], str)
                        or not re.fullmatch(r'[0-9a-f]{64}', release['evidence_sha256'])
                        or _time(datetime.fromisoformat(release['at'])) < _time(datetime.fromisoformat(created['at']))):
                    raise ValueError('Invalid hold release evidence')
            snapshots[row['id']] = {'id': row['id'], 'hold': hold, 'created': created, 'release': release}
        if db.execute('SELECT COUNT(*) FROM hold_decisions_v2').fetchone()[0] != sum(
                2 if snapshot['release'] else 1 for snapshot in snapshots.values()):
            raise ValueError('Orphan hold decision')
        return snapshots

    def create(self, hold, at):
        self._validate(hold, at)
        serialized = canonical({key: value.isoformat() if isinstance(value, datetime) else value
                                for key, value in hold.items()})
        identifier, scope = str(UUID(str(hold['id']))), str(UUID(str(hold['scope_id'])))
        actor = str(UUID(str(hold['responsible_id'])))
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            expected = self._snapshots(db)
            self.authenticated.verify_holds(expected)
            existing = expected.get(identifier)
            if existing is not None:
                if canonical(existing['hold']) != serialized or existing['release']:
                    raise ValueError('Conflicting or released hold')
                return
            created = {'action': 'created', 'actor': actor, 'at': _time(at).isoformat(),
                       'decision_id': None, 'evidence_sha256': None}
            snapshot = {'id': identifier, 'hold': json.loads(serialized), 'created': created, 'release': None}
            self.authenticated.update_hold(expected, snapshot)
            db.execute('INSERT INTO holds_v2 VALUES (?,?,?,?,0)', (identifier, hold['scope_kind'], scope, serialized))
            db.execute('INSERT INTO hold_decisions_v2 (hold_id,action,actor,at) VALUES (?,?,?,?)',
                       (identifier, 'created', actor, created['at']))

    def release(self, identifier, actor, decision_id, evidence, at):
        identifier, actor = str(UUID(str(identifier))), str(UUID(str(actor)))
        decision_id = str(UUID(str(decision_id)))
        if not isinstance(evidence, bytes) or not 1 <= len(evidence) <= 1024 * 1024:
            raise ValueError('Documented release evidence required')
        evidence_sha256 = hashlib.sha256(evidence).hexdigest()
        timestamp = _time(at).isoformat()
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            expected = self._snapshots(db)
            self.authenticated.verify_holds(expected)
            snapshot = expected.get(identifier)
            if snapshot is None or timestamp < snapshot['created']['at']:
                raise ValueError('Unknown hold or invalid release chronology')
            if snapshot['release']:
                previous = snapshot['release']
                if (previous['actor'], previous['decision_id'], previous['evidence_sha256']) != (
                        actor, decision_id, evidence_sha256):
                    raise ValueError('Conflicting release decision')
                return
            release = {'action': 'released', 'actor': actor, 'at': timestamp,
                       'decision_id': decision_id, 'evidence_sha256': evidence_sha256}
            self.authenticated.update_hold(expected, {**snapshot, 'release': release})
            db.execute('UPDATE holds_v2 SET released=1 WHERE id=?', (identifier,))
            db.execute('INSERT INTO hold_decisions_v2 (hold_id,action,actor,at,decision_id,evidence_sha256) '
                       'VALUES (?,?,?,?,?,?)',
                       (identifier, 'released', actor, timestamp, decision_id, evidence_sha256))

    @staticmethod
    def _schema(db):
        if db.execute('PRAGMA user_version').fetchone()[0] != 2:
            raise ValueError('Scoped hold registry required')

    @contextmanager
    def guard(self, scopes, at=None):
        at = _time(at or datetime.now(timezone.utc))
        normalized = {(kind, str(UUID(str(identifier)))) for kind, identifier in scopes}
        if not normalized or any(kind not in ('account', 'owner', 'document') for kind, _ in normalized):
            raise ValueError('Explicit hold scopes required')
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            snapshots = self._snapshots(db)
            self.authenticated.verify_holds(snapshots)
            for kind, identifier in normalized:
                for snapshot in snapshots.values():
                    hold = snapshot['hold'].copy()
                    if hold['scope_kind'] != kind or hold['scope_id'] != identifier:
                        continue
                    if snapshot['release']:
                        continue
                    for field in ('reviewed_at', 'review_at', 'ends_at'):
                        if hold.get(field) is not None:
                            hold[field] = datetime.fromisoformat(hold[field])
                    self._validate(hold, at)
                    raise ActiveHoldError('Active hold blocks mutation')
            yield


def configured_hold_guard(settings, scopes, coordinator):
    if not getattr(settings, 'lifecycle_durable_receipts_required', True):
        return nullcontext()
    path = getattr(settings, 'lifecycle_holds_path', None)
    if not path or not Path(path).is_absolute():
        raise ValueError('Separate scoped hold registry required')
    path = Path(path).absolute()
    if path.is_relative_to(Path(settings.storage_dir).absolute()):
        raise ValueError('Hold registry must be outside document storage')
    if coordinator is None:
        raise ValueError('Authenticated hold confirmation required')
    separate_directories((path.parent, coordinator.registry.path.parent,
                          coordinator.store.path.parent, coordinator.authenticated.store.path.parent,
                          Path(settings.lifecycle_authentication_key_path).parent, settings.storage_dir))
    return HoldStore(path, coordinator.authenticated).guard(scopes)
