"""Persistent, scoped A20 hold experiment; never executes a deletion."""
import json
from uuid import UUID

from backend.lifecycle_durability import ConfirmationStore, canonical
from backend.lifecycle_retention_policy import _time, receipt_expiry_plan


class SyntheticHolds:
    def __init__(self, path):
        self.store = ConfirmationStore(path)

    def initialize(self):
        self.store.initialize()
        with self.store.connection() as db:
            db.executescript('''
                CREATE TABLE synthetic_holds (
                    id TEXT PRIMARY KEY, scope_id TEXT NOT NULL, content TEXT NOT NULL,
                    released INTEGER NOT NULL CHECK(released IN (0,1)));
                CREATE TABLE synthetic_hold_history (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT, hold_id TEXT NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, at TEXT NOT NULL);
            ''')

    def create(self, hold, at):
        # Reuse A20 validation, including a review within 30 days and an end condition.
        receipt_expiry_plan(at, at, None, coverage_attested=False, exceptions_complete=True, holds=[hold])
        identifier = str(UUID(str(hold['id'])))
        scope = str(UUID(str(hold['scope_id'])))
        actor = str(UUID(str(hold['responsible_id'])))
        serializable = {key: value.isoformat() if hasattr(value, 'isoformat') else value
                        for key, value in hold.items()}
        text = canonical(serializable)
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            old = db.execute('SELECT content,released FROM synthetic_holds WHERE id=?', (identifier,)).fetchone()
            if old is not None:
                if old['content'] != text:
                    raise ValueError('Conflicting hold')
                if old['released']:
                    raise ValueError('Released hold cannot be recreated with the same identifier')
                return
            db.execute('INSERT INTO synthetic_holds VALUES (?,?,?,0)', (identifier, scope, text))
            db.execute('INSERT INTO synthetic_hold_history (hold_id,action,actor,at) VALUES (?,?,?,?)',
                       (identifier, 'created', actor, _time(at).isoformat()))

    def release(self, identifier, actor, at):
        identifier, actor = str(UUID(str(identifier))), str(UUID(str(actor)))
        timestamp = _time(at).isoformat()
        with self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT released FROM synthetic_holds WHERE id=?', (identifier,)).fetchone()
            if row is None:
                raise ValueError('Unknown hold')
            if not row['released']:
                created = db.execute("SELECT at FROM synthetic_hold_history WHERE hold_id=? AND action='created'",
                                     (identifier,)).fetchone()
                if created is None or timestamp < created['at']:
                    raise ValueError('Hold release predates creation or history is incomplete')
                db.execute('UPDATE synthetic_holds SET released=1 WHERE id=?', (identifier,))
                db.execute('INSERT INTO synthetic_hold_history (hold_id,action,actor,at) VALUES (?,?,?,?)',
                           (identifier, 'released', actor, timestamp))

    def for_scope(self, scope, at):
        from datetime import datetime
        scope = str(UUID(str(scope)))
        with self.store.connection() as db:
            rows = db.execute('SELECT content FROM synthetic_holds WHERE scope_id=? AND released=0', (scope,)).fetchall()
        holds = []
        for row in rows:
            hold = json.loads(row['content'])
            for name in ('reviewed_at', 'review_at', 'ends_at'):
                if hold.get(name) is not None:
                    hold[name] = datetime.fromisoformat(hold[name])
            if str(UUID(str(hold['scope_id']))) != scope:
                raise ValueError('Conflicting hold scope')
            holds.append(hold)
        receipt_expiry_plan(at, at, None, coverage_attested=False, exceptions_complete=True, holds=holds)
        return holds
