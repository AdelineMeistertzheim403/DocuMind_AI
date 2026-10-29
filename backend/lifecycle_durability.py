"""Opt-in independent confirmation ledger; no provisioning or network transport."""
from contextlib import contextmanager
import hashlib
import hmac
import json
import os
from pathlib import Path
import sqlite3
import stat
from uuid import NAMESPACE_URL, UUID, uuid5

from .lifecycle_registry import Registry
from .lifecycle_backup_lock import lifecycle_store_lock


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


class ConfirmationStore:
    def __init__(self, path):
        self.registry = Registry(path)
        self.path = self.registry.path

    def _check(self, existing=True):
        info = self.registry._check(existing=existing)
        if os.name == 'posix':
            for path in (self.path.parent, self.path) if existing else (self.path.parent,):
                if path.stat().st_uid != os.geteuid():
                    raise ValueError('Confirmation storage owner mismatch')
        return info

    @contextmanager
    def connection(self):
        with lifecycle_store_lock():
            before = self._check()
            db = sqlite3.connect(self.path.as_uri() + '?mode=rw', uri=True, timeout=5)
            db.row_factory = sqlite3.Row
            try:
                after = self._check()
                if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                    raise ValueError('Confirmation changed while opening')
                db.execute('PRAGMA synchronous=FULL')
                if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('Confirmation integrity failed')
                with db:
                    yield db
            finally:
                db.close()

    def initialize(self):
        with lifecycle_store_lock():
            self._check(existing=False)
            descriptor = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
            with self.connection() as db:
                db.executescript('''
                    CREATE TABLE confirmations (
                        operation TEXT PRIMARY KEY, payload TEXT NOT NULL, digest TEXT NOT NULL);
                    CREATE TABLE admissions (
                        sequence INTEGER PRIMARY KEY CHECK(sequence BETWEEN 1 AND 5),
                        user_id TEXT NOT NULL UNIQUE);
                    PRAGMA user_version=1;
                ''')

    def confirm(self, operation, payload):
        text = canonical(payload)
        digest = hashlib.sha256(text.encode()).hexdigest()
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT payload,digest FROM confirmations WHERE operation=?', (operation,)).fetchone()
            if row is None:
                db.execute('INSERT INTO confirmations VALUES (?,?,?)', (operation, text, digest))
            elif row['payload'] != text or not hmac.compare_digest(row['digest'], digest):
                raise ValueError('Conflicting independent confirmation')
        with self.connection() as db:
            row = db.execute('SELECT payload,digest FROM confirmations WHERE operation=?', (operation,)).fetchone()
            if row is None or row['payload'] != text or not hmac.compare_digest(row['digest'], digest):
                raise ValueError('Independent confirmation not verified')
        return digest

    def reserve_admission(self, count, user_id):
        if type(count) is not int or not 1 <= count <= 5:
            raise ValueError('Invalid admission sequence')
        user = str(UUID(str(user_id)))
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            existing = db.execute('SELECT user_id FROM admissions WHERE sequence=?', (count,)).fetchone()
            if existing is None:
                previous = db.execute('SELECT COALESCE(MAX(sequence),0),COUNT(*) FROM admissions').fetchone()
                if previous[0] != count - 1 or previous[1] != count - 1:
                    raise ValueError('Incomplete admission witness')
                db.execute('INSERT INTO admissions VALUES (?,?)', (count, user))
            elif existing['user_id'] != user:
                raise ValueError('Conflicting admission witness')
        with self.connection() as db:
            row = db.execute('SELECT user_id FROM admissions WHERE sequence=?', (count,)).fetchone()
            if row is None or row['user_id'] != user:
                raise ValueError('Admission witness not verified')

    def admission_entries(self):
        with self.connection() as db:
            rows = db.execute('SELECT sequence,user_id FROM admissions ORDER BY sequence').fetchall()
        entries = [dict(row) for row in rows]
        if ([entry['sequence'] for entry in entries] != list(range(1, len(entries) + 1))
                or len(entries) > 5):
            raise ValueError('Incomplete admission witness')
        return entries

    def restore_evidence(self, restored_count):
        if type(restored_count) is not int or not 0 <= restored_count <= 5:
            raise ValueError('Invalid restored admission count')
        with self.connection() as db:
            rows = db.execute('SELECT sequence FROM admissions ORDER BY sequence').fetchall()
        values = [row['sequence'] for row in rows]
        if values != list(range(1, len(values) + 1)):
            raise ValueError('Incomplete admission witness')
        return {'minimum_issued_count': max(restored_count, len(values)), 'witness_count': len(values),
                'keep_registration_closed': True, 'opening_authorized': False,
                'reconciliation_required': True}


class DurableCoordinator:
    def __init__(self, registry, store):
        if os.name != 'posix':
            raise ValueError('POSIX permissions required for confirmation')
        if registry.path.resolve() != registry.path or store.path.resolve() != store.path:
            raise ValueError('Canonical confirmation paths required')
        if registry.path == store.path or registry.path.parent == store.path.parent:
            raise ValueError('Independent confirmation directory required')
        registry._check()
        store._check()
        if any(path.stat().st_uid != os.geteuid() for path in (registry.path, registry.path.parent)):
            raise ValueError('Registry owner mismatch')
        if os.path.samefile(registry.path, store.path):
            raise ValueError('Independent confirmation file required')
        self.registry = registry
        self.store = store

    def confirm_account(self, receipt_id):
        with self.registry.connection() as db:
            row = db.execute('SELECT id,kind,user_id,owner_id,received_at FROM requests WHERE id=?',
                             (str(UUID(str(receipt_id))),)).fetchone()
        if row is None or row['kind'] != 'erasure' or not row['user_id'] or not row['owner_id']:
            raise ValueError('Account receipt unavailable')
        return self.store.confirm('account:' + row['id'], dict(row))

    def confirm_document(self, document_id):
        identifier = str(UUID(str(document_id)))
        with self.registry.connection() as db:
            row = db.execute('SELECT document_id,owner_id,storage_name,requested_at FROM document_erasures '
                             'WHERE document_id=?', (identifier,)).fetchone()
        if row is None:
            raise ValueError('Document receipt unavailable')
        return self.store.confirm('document:' + identifier, dict(row))

    def verify_recovery_receipts(self):
        """Check exact receipt sets while all writers are stopped; never creates confirmations."""
        with self.registry.connection() as db:
            accounts = db.execute("SELECT id,kind,user_id,owner_id,received_at FROM requests "
                                  "WHERE kind='erasure'").fetchall()
            documents = db.execute('SELECT document_id,owner_id,storage_name,requested_at '
                                   'FROM document_erasures').fetchall()
        if any(not row['id'] or not row['user_id'] or not row['owner_id'] or not row['received_at']
               for row in accounts):
            raise ValueError('Incomplete account receipt requires reconciliation')
        expected = {**{'account:' + row['id']: canonical(dict(row)) for row in accounts},
                    **{'document:' + row['document_id']: canonical(dict(row)) for row in documents}}
        with self.store.connection() as db:
            actual = db.execute('SELECT operation,payload,digest FROM confirmations').fetchall()
        if {row['operation'] for row in actual} != set(expected):
            raise ValueError('Recovery receipt sets differ')
        for row in actual:
            text = expected[row['operation']]
            if row['payload'] != text or not hmac.compare_digest(row['digest'], hashlib.sha256(text.encode()).hexdigest()):
                raise ValueError('Recovery receipt mismatch')
        return {'complete_for_observed_stores': True, 'account_receipts': len(accounts),
                'document_receipts': len(documents), 'opening_authorized': False}


def _read_private_key(path):
    path = Path(path)
    if os.name != 'posix' or not path.is_absolute() or path.resolve() != path:
        raise ValueError('A canonical POSIX key path is required')
    if any(parent.is_symlink() for parent in (path.parent, *path.parent.parents)):
        raise ValueError('Unsafe key directory')
    directory = path.parent.stat()
    if not stat.S_ISDIR(directory.st_mode) or directory.st_uid != os.geteuid() or directory.st_mode & 0o077:
        raise ValueError('Private key directory required')
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        info = os.fstat(descriptor)
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o077 or info.st_nlink != 1 or info.st_size != 32):
            raise ValueError('Private 256-bit key required')
        key = os.read(descriptor, 33)
        if len(key) != 32:
            raise ValueError('Incomplete authentication key')
        return key
    finally:
        os.close(descriptor)


def separate_directories(directories):
    paths = [Path(path).absolute() for path in directories]
    for index, first in enumerate(paths):
        if first.resolve() != first:
            raise ValueError('Canonical private directories required')
        for second in paths[index + 1:]:
            if first.is_relative_to(second) or second.is_relative_to(first):
                raise ValueError('Separate private directories required')


def require_synthetic_mutation(settings):
    if (getattr(settings, 'lifecycle_durable_receipts_required', True)
            and not getattr(settings, 'lifecycle_synthetic_mutations_enabled', False)):
        raise ValueError('Experimental lifecycle mutations are disabled')


class AuthenticatedCoordinator(DurableCoordinator):
    """Local receipt binding; legacy SHA-only records never become HMAC proofs."""

    def __init__(self, registry, store, authenticated):
        super().__init__(registry, store)
        self.authenticated = authenticated
        if (authenticated.store.path.parent in (registry.path.parent, store.path.parent)
                or authenticated.store.path.resolve() != authenticated.store.path):
            raise ValueError('Separate authenticated confirmation directory required')
        authenticated.check_header()

    def _operation(self, kind, identifier):
        identifier = str(UUID(str(identifier)))
        with self.registry.connection() as db:
            if kind == 'account':
                row = db.execute('SELECT id,kind,user_id,owner_id,received_at FROM requests WHERE id=?',
                                 (identifier,)).fetchone()
                if row is None or row['kind'] != 'erasure' or not row['user_id'] or not row['owner_id']:
                    raise ValueError('Account receipt unavailable')
                mutation, target = 'account_deactivation', row['user_id']
            elif kind == 'document':
                row = db.execute('SELECT document_id,owner_id,storage_name,requested_at FROM document_erasures '
                                 'WHERE document_id=?', (identifier,)).fetchone()
                if row is None:
                    raise ValueError('Document receipt unavailable')
                mutation, target = 'document_erasure', row['document_id']
            else:
                raise ValueError('Unsupported receipt')
        with self.store.connection() as db:
            legacy = db.execute('SELECT 1 FROM confirmations WHERE operation=?', (kind + ':' + identifier,)).fetchone()
        if legacy:
            raise ValueError('Legacy receipt requires explicit review; no automatic authentication')
        digest = hashlib.sha256(canonical(dict(row)).encode()).hexdigest()
        return {'id': str(uuid5(NAMESPACE_URL, 'documind:receipt-v2:' + kind + ':' + identifier)),
                'type': mutation, 'target': str(UUID(target)), 'receipt_sha256': digest}

    def _confirm(self, kind, identifier):
        with self.registry.connection() as db:
            if kind == 'account':
                row = db.execute('SELECT state FROM requests WHERE id=?', (str(UUID(str(identifier))),)).fetchone()
                expected_state = 'received'
            elif kind == 'document':
                row = db.execute('SELECT state FROM document_erasures WHERE document_id=?',
                                 (str(UUID(str(identifier))),)).fetchone()
                expected_state = 'requested'
            else:
                raise ValueError('Unsupported receipt')
        if row is None or row['state'] != expected_state:
            raise ValueError('Receipt state requires reconciliation')
        operation = self._operation(kind, identifier)
        self.authenticated.prepare(operation)
        return self.authenticated.confirm(operation)

    def confirm_account(self, receipt_id):
        return self._confirm('account', receipt_id)

    def confirm_document(self, document_id):
        return self._confirm('document', document_id)

    def authorize_account(self, receipt_id):
        return self.authenticated.authorize_once(self._operation('account', receipt_id))

    def authorize_document(self, document_id):
        return self.authenticated.authorize_once(self._operation('document', document_id))

    def account_result(self, receipt_id):
        return self.authenticated.record_result(self._operation('account', receipt_id))

    def document_result(self, document_id):
        return self.authenticated.record_result(self._operation('document', document_id))

    def verify_recovery_receipts(self):
        with self.registry.connection() as db:
            accounts = db.execute("SELECT id,user_id,owner_id,state FROM requests WHERE kind='erasure'").fetchall()
            documents = db.execute('SELECT document_id,state FROM document_erasures').fetchall()
        if any(not row['id'] or not row['user_id'] or not row['owner_id'] for row in accounts):
            raise ValueError('Incomplete account receipt requires reconciliation')
        with self.store.connection() as db:
            if db.execute('SELECT 1 FROM confirmations LIMIT 1').fetchone():
                raise ValueError('Legacy receipts require explicit review')
        expected = [self._operation('account', row['id']) for row in accounts]
        expected += [self._operation('document', row['document_id']) for row in documents]
        with self.authenticated.store.connection() as db:
            actual = {row[0] for row in db.execute('SELECT DISTINCT operation FROM synthetic_transitions')}
        if actual != {operation['id'] for operation in expected}:
            raise ValueError('Recovery receipt sets differ')
        for operation, row in zip(expected, [*accounts, *documents]):
            proof_state = self.authenticated.verify(operation)
            allowed = {'received': ('confirmed',), 'requested': ('confirmed',),
                       'deactivated': ('result_recorded', 'closed'),
                       'active_erased': ('result_recorded', 'closed'),
                       'closed': ('result_recorded', 'closed')}
            if proof_state not in allowed.get(row['state'], ()):
                raise ValueError('Uncertain mutation requires reconciliation')
        return {'complete_for_observed_stores': True, 'account_receipts': len(accounts),
                'document_receipts': len(documents), 'opening_authorized': False}


def configured_coordinator(settings, registry):
    if not getattr(settings, 'lifecycle_durable_receipts_required', True):
        return None
    path = getattr(settings, 'lifecycle_confirmation_path', None)
    if registry is None or path is None or not Path(path).is_absolute():
        raise ValueError('Independent confirmation is required')
    if Path(path).absolute().is_relative_to(Path(settings.storage_dir).absolute()):
        raise ValueError('Confirmation must be outside document storage')
    authenticated_path = getattr(settings, 'lifecycle_authenticated_confirmation_path', None)
    key_path = getattr(settings, 'lifecycle_authentication_key_path', None)
    if not authenticated_path or not key_path or not Path(authenticated_path).is_absolute():
        raise ValueError('Authenticated confirmation and separate key are required')
    authenticated_path, key_path = Path(authenticated_path).absolute(), Path(key_path)
    directories = [registry.path.parent, Path(path).absolute().parent, authenticated_path.parent, key_path.parent]
    separate_directories([*directories, settings.storage_dir])
    from .lifecycle_authenticated import AuthenticatedConfirmationStore
    authenticated = AuthenticatedConfirmationStore(authenticated_path, _read_private_key(key_path), 'documind-local-v2')
    return AuthenticatedCoordinator(registry, ConfirmationStore(path), authenticated)
