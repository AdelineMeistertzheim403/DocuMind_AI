"""Private operator ledger, separate from the application DB and its restores.

No HTTP API, email, document text or free-form notes. Provision explicitly before
enabling integration. POSIX permissions are enforced; Windows ACLs are operational.
"""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import os
import re
from pathlib import Path
import sqlite3
import stat
from uuid import UUID, uuid4

from .lifecycle_backup_lock import lifecycle_store_lock

KINDS = frozenset(('access', 'rectification', 'erasure', 'restriction', 'objection', 'portability'))


def utc(value=None):
    value = value or datetime.now(timezone.utc)
    if value.tzinfo is None:
        raise ValueError('Timezone required')
    return value.astimezone(timezone.utc).isoformat()


class Registry:
    def __init__(self, path):
        self.path = Path(path).absolute()

    def _check(self, existing=True):
        # Reject symlinked ancestors too: never resolve first and lose the evidence.
        for parent in (self.path.parent, *self.path.parent.parents):
            if parent.is_symlink():
                raise ValueError('Unsafe registry directory')
        directory = self.path.parent.stat()
        if not stat.S_ISDIR(directory.st_mode) or (os.name == 'posix' and directory.st_mode & 0o077):
            raise ValueError('Private registry directory required')
        if existing:
            info = self.path.lstat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or (os.name == 'posix' and info.st_mode & 0o077):
                raise ValueError('Private regular registry required')
            return info

    def initialize(self):
        with lifecycle_store_lock():
            self._check(existing=False)
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with self.connection() as db:
                db.executescript('''
                    CREATE TABLE requests (
                        id TEXT PRIMARY KEY, kind TEXT NOT NULL, user_id TEXT,
                        owner_id TEXT, received_at TEXT NOT NULL, state TEXT NOT NULL,
                        closed_at TEXT, expires_at TEXT, failure_code TEXT);
                    CREATE UNIQUE INDEX deletion_identity ON requests(user_id, owner_id)
                        WHERE kind='erasure' AND user_id IS NOT NULL;
                    CREATE TABLE admission_watermark (
                        id INTEGER PRIMARY KEY CHECK(id=1), issued_count INTEGER NOT NULL,
                        observed_at TEXT NOT NULL);
                    CREATE TABLE document_erasures (
                        document_id TEXT PRIMARY KEY, owner_id TEXT NOT NULL,
                        storage_name TEXT NOT NULL, requested_at TEXT NOT NULL,
                        state TEXT NOT NULL, completed_at TEXT);
                    PRAGMA user_version=1;
                ''')

    @contextmanager
    def connection(self):
        with lifecycle_store_lock():
            before = self._check()
            # mode=rw prevents accidental creation during an application request.
            db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
            db.row_factory = sqlite3.Row
            try:
                after = self._check()
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise ValueError('Registry changed while opening')
                db.execute('PRAGMA synchronous=FULL')
                db.execute('PRAGMA secure_delete=ON')
                with db:
                    yield db
            finally:
                db.close()

    def receive(self, kind, *, user_id=None, owner_id=None, received_at=None):
        if kind not in KINDS:
            raise ValueError('Unsupported request kind')
        user_id = str(UUID(str(user_id))) if user_id else None
        owner_id = str(UUID(str(owner_id))) if owner_id else None
        if (user_id is None) != (owner_id is None):
            raise ValueError('Both internal identities required')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if kind == 'erasure' and user_id:
                row = db.execute("SELECT id FROM requests WHERE kind='erasure' AND user_id=? AND owner_id=?",
                                 (user_id, owner_id)).fetchone()
                if row:
                    return row['id']
            identifier = str(uuid4())
            db.execute('INSERT INTO requests VALUES (?,?,?,?,?,?,?,?,?)',
                       (identifier, kind, user_id, owner_id, utc(received_at), 'received', None, None, None))
            return identifier

    def active_erased(self, identifier):
        with self.connection() as db:
            db.execute("UPDATE requests SET state='active_erased', failure_code=NULL WHERE id=? AND state!='closed'",
                       (str(UUID(str(identifier))),))

    def account_deactivated(self, identifier):
        with self.connection() as db:
            changed = db.execute("UPDATE requests SET state='deactivated' WHERE id=? AND kind='erasure' "
                                 "AND state='received'", (str(UUID(str(identifier))),)).rowcount
            if changed != 1:
                raise ValueError('Account receipt cannot record deactivation')

    def document_requested(self, document_id, owner_id, storage_name):
        if not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|txt)', storage_name):
            raise ValueError('Unsafe storage identity')
        with self.connection() as db:
            db.execute('INSERT OR IGNORE INTO document_erasures VALUES (?,?,?,?,?,NULL)',
                       (str(UUID(str(document_id))),str(UUID(str(owner_id))),storage_name,utc(),'requested'))
            row=db.execute('SELECT owner_id,storage_name FROM document_erasures WHERE document_id=?',
                           (str(document_id),)).fetchone()
            if row['owner_id']!=str(owner_id) or row['storage_name']!=storage_name:
                raise ValueError('Conflicting erasure identity')

    def document_finished(self, document_id, cleaned):
        with self.connection() as db:
            db.execute('UPDATE document_erasures SET state=?,completed_at=? WHERE document_id=?',
                       ('active_erased' if cleaned else 'cleanup_pending',utc() if cleaned else None,str(UUID(str(document_id)))))

    def pending_document_files(self, owner_id):
        with self.connection() as db:
            return [row[0] for row in db.execute("SELECT storage_name FROM document_erasures WHERE owner_id=? AND state!='active_erased'",
                                               (str(UUID(str(owner_id))),))]

    def confirm_document_absent(self, document_id, settings):
        """Operator-only completion after offline reconciliation; no file deletion."""
        from sqlalchemy import select
        from .db import make_engine
        from .models import Document
        with self.connection() as db:
            row=db.execute('SELECT * FROM document_erasures WHERE document_id=?',
                           (str(UUID(str(document_id))),)).fetchone()
        if row is None:raise ValueError('Unknown document receipt')
        if not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|txt)',row['storage_name']):
            raise ValueError('Unsafe storage identity')
        root=settings.storage_dir.absolute()
        if any(path.is_symlink() for path in (root,*root.parents)) or not root.is_dir():
            raise ValueError('Unsafe storage root')
        engine=make_engine(settings.database_url)
        try:
            with engine.connect() as connection:
                if connection.scalar(select(Document.id).where(Document.id==UUID(row['document_id']))) is not None:
                    raise ValueError('Document still active')
        finally:engine.dispose()
        for name in (row['storage_name'],row['storage_name']+'.deleted',Path(row['storage_name']).stem+'.part'):
            # lexists also refuses dangling symlinks.
            if os.path.lexists(root/name):raise ValueError('Residual document source remains')
        self.document_finished(document_id,True)

    def expire_documents(self, *, retention_days, at, backup_safe_before, execute=False):
        if execute:
            raise ValueError('Receipt expiry execution disabled pending independent evidence')
        if type(retention_days) is not int or not 1 <= retention_days <= 3650:
            raise ValueError('Explicit document receipt retention required')
        current=datetime.fromisoformat(utc(at))
        safe=utc(backup_safe_before)
        if safe>utc(current):raise ValueError('Backup boundary cannot be in the future')
        cutoff=utc(current-timedelta(days=retention_days))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            identifiers=[row[0] for row in db.execute("SELECT document_id FROM document_erasures WHERE state='active_erased' AND completed_at<=? AND completed_at<=?",
                                                     (cutoff,safe))]
        return {'simulation':not execute,'eligible':len(identifiers)}

    def finish(self, identifier, *, retention_days=None, closed_at=None, failed=False):
        identifier=str(UUID(str(identifier)))
        if retention_days is not None and (type(retention_days) is not int or not 1 <= retention_days <= 3650):
            raise ValueError('Explicit retention must be between 1 and 3650 days')
        closed = datetime.fromisoformat(utc(closed_at))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM requests WHERE id=?', (str(UUID(str(identifier))),)).fetchone()
            if row is None:
                raise ValueError('Unknown request')
            if row['state'] == 'closed':
                if row['expires_at'] is None and retention_days is not None:
                    expiry=datetime.fromisoformat(row['closed_at'])+timedelta(days=retention_days)
                    db.execute('UPDATE requests SET expires_at=? WHERE id=?',(utc(expiry),identifier))
                return  # Retrying must not extend retention or reopen a completed case.
            if closed < datetime.fromisoformat(row['received_at']):
                raise ValueError('Closure predates receipt')
            if failed:
                db.execute("UPDATE requests SET state='failed', failure_code='processing_failed' WHERE id=?", (identifier,))
            else:
                expires = utc(closed + timedelta(days=retention_days)) if retention_days else None
                db.execute("UPDATE requests SET state='closed', closed_at=?, expires_at=?, failure_code=NULL WHERE id=?",
                           (utc(closed), expires, identifier))

    def observe_admissions(self, count, observed_at=None):
        if type(count) is not int or count < 0:
            raise ValueError('Invalid cumulative admission count')
        with self.connection() as db:
            db.execute('''INSERT INTO admission_watermark VALUES (1,?,?)
                ON CONFLICT(id) DO UPDATE SET issued_count=max(issued_count,excluded.issued_count),
                observed_at=excluded.observed_at''', (count, utc(observed_at)))

    def expiry_plan(self, *, at=None, backup_safe_before=None):
        """No deletion: erasure receipts remain until old recoverable copies are gone."""
        current = utc(at)
        safe = utc(backup_safe_before) if backup_safe_before else None
        if safe is not None and safe > current:
            raise ValueError('Backup boundary cannot be in the future')
        with self.connection() as db:
            rows = db.execute('SELECT * FROM requests ORDER BY received_at,id').fetchall()
        result = []
        for row in rows:
            reason = ('not_closed' if row['state'] != 'closed' else
                      'policy_undecided' if row['expires_at'] is None else
                      'not_due' if row['expires_at'] > current else
                      'restore_evidence_required' if row['kind'] == 'erasure' and
                      (safe is None or row['closed_at'] > safe) else 'eligible')
            result.append({'id': row['id'], 'reason': reason})
        return {'simulation': True, 'requests': result}

    def expire(self, *, at, backup_safe_before, execute=False):
        """Simulate only; a declared backup boundary is not evidence of neutralization."""
        if execute:
            raise ValueError('Receipt expiry execution disabled pending independent evidence')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            plan = self.expiry_plan(at=at, backup_safe_before=backup_safe_before)
            identifiers = [row['id'] for row in plan['requests'] if row['reason'] == 'eligible']
        return {'simulation': not execute, 'eligible': len(identifiers)}

    def restore_plan(self, restored_count):
        if type(restored_count) is not int or restored_count < 0:
            raise ValueError('Invalid restored admission count')
        with self.connection() as db:
            watermark = db.execute('SELECT issued_count,observed_at FROM admission_watermark WHERE id=1').fetchone()
            # Include pending/failed requests: the requested disable must survive a restore.
            rows = db.execute("SELECT user_id,owner_id FROM requests WHERE kind='erasure' AND user_id IS NOT NULL").fetchall()
            documents=db.execute('SELECT document_id,owner_id,storage_name,state FROM document_erasures').fetchall()
        return {'simulation': True, 'keep_registration_closed': True,
                'watermark_present': watermark is not None,
                'watermark_observed_at': watermark['observed_at'] if watermark else None,
                'authoritative_counter_reconciliation_required': True,
                'minimum_issued_count': max(restored_count, watermark[0]) if watermark else restored_count,
                'erasure_requests': [dict(row) for row in rows],
                'document_erasures': [dict(row) for row in documents],
                'opening_authorized': False}


def configured_registry(settings):
    path = getattr(settings, 'lifecycle_registry_path', None)
    if path and (not Path(path).is_absolute() or Path(path).absolute().is_relative_to(settings.storage_dir.absolute())):
        raise ValueError('Independent absolute registry path required')
    return Registry(path) if path else None
