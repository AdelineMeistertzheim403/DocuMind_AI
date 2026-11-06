"""Offline standard-profile erasure. Root-owned evidence is never an API privilege."""
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import sys
from uuid import UUID, NAMESPACE_URL, uuid5

from sqlalchemy import inspect, or_, select, text, tuple_

from .account_models import AccountToken, PublicRegistrationQuota, WorkspaceMembership
from .auth import User
from .db import Base, make_engine, make_sessions
from .models import Document
from .recovery_quarantine import read_recovery_state
from .services.document_integrity import STORAGE_NAME, discard_session


class ErasureError(ValueError):
    pass


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), default=str,
                      allow_nan=False).encode()


def fingerprint(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def identifier(value):
    if not isinstance(value, str) or str(UUID(value)) != value:
        raise ErasureError('Canonical UUID required')
    return value


def enabled(settings):
    return settings.erasure_authority_dir is not None


def checked_path(path, uid, *, directory=False, private=False):
    if sys.platform != 'linux':
        raise ErasureError('Native Linux authority required')
    path = Path(path)
    if not path.is_absolute():
        raise ErasureError('Absolute path required')
    for parent in path.parents:
        info = parent.lstat()
        if (not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode)
                or info.st_uid not in (0, uid)
                or info.st_mode & 0o022 and not (info.st_uid == 0 and info.st_mode & stat.S_ISVTX)):
            raise ErasureError('Untrusted authority ancestry')
    info = path.lstat()
    if (not (stat.S_ISDIR if directory else stat.S_ISREG)(info.st_mode)
            or stat.S_ISLNK(info.st_mode) or info.st_uid != uid
            or info.st_mode & (0o077 if private else 0o022)
            or not directory and info.st_nlink != 1):
        raise ErasureError('Unsafe evidence ownership or permissions')
    return path


def read(path, uid, *, private=False):
    path = checked_path(path, uid, private=private)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info, current = os.fstat(stream.fileno()), path.lstat()
        if (info.st_dev, info.st_ino) != (current.st_dev, current.st_ino) or info.st_size > 16 * 1024 * 1024:
            raise ErasureError('Evidence changed or exceeds its bound')
        return stream.read(16 * 1024 * 1024 + 1)


def decode(raw):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ErasureError('Duplicate evidence key')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def write(path, value, uid, *, private=False, replace=False):
    if os.geteuid() != uid:
        raise ErasureError('Wrong evidence writer')
    path = Path(path)
    checked_path(path.parent, uid, directory=True, private=private)
    if os.path.lexists(path):
        checked_path(path, uid, private=private)
        if not replace:
            raise ErasureError('Evidence already exists')
    temporary = path.parent / ('.erasure-write-' + secrets.token_hex(16))
    raw = canonical(value)
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o600 if private else 0o644)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, path)
        else:
            os.link(temporary, path)
            temporary.unlink()
        fsync_directory(path.parent)
        if read(path, uid, private=private) != raw:
            raise ErasureError('Evidence readback failed')
    finally:
        if temporary.exists():
            temporary.unlink()


def fsync_directory(path):
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


@contextmanager
def application_identity(settings):
    previous = os.geteuid()
    if previous != settings.erasure_application_uid:
        if previous != 0:
            raise ErasureError('Wrong application identity')
        os.seteuid(settings.erasure_application_uid)
    try:
        yield
    finally:
        os.seteuid(previous)


class Authority:
    def __init__(self, settings):
        self.settings = settings
        if (not enabled(settings) or settings.application_profile != 'standard'
                or not settings.lifecycle_durable_receipts_required
                or settings.lifecycle_synthetic_mutations_enabled or settings.ai_enabled
                or settings.legacy_api_enabled or settings.owner_demo_enabled or settings.api_keys):
            raise ErasureError('Strict standard erasure configuration required')
        self.root = checked_path(settings.erasure_authority_dir, 0, directory=True)
        self.requests = checked_path(settings.erasure_requests_dir, settings.erasure_application_uid,
                                     directory=True, private=True)
        protected = [settings.storage_dir, self.requests]
        protected += [p.parent for p in (settings.lifecycle_registry_path,
                      settings.lifecycle_confirmation_path, settings.lifecycle_authenticated_confirmation_path,
                      settings.lifecycle_holds_path, settings.lifecycle_authentication_key_path) if p]
        if any(self.root.is_relative_to(Path(p).absolute()) or Path(p).absolute().is_relative_to(self.root)
               for p in protected):
            raise ErasureError('Authority must be outside application and lifecycle data')
        self.header = {'version': 1, 'instance': str(settings.erasure_instance_id),
                       'application_uid': settings.erasure_application_uid}

    def check(self):
        if decode(read(self.root / 'instance.json', 0)) != self.header:
            raise ErasureError('Wrong authority instance')
        if decode(read(self.requests / 'instance.json', self.settings.erasure_application_uid,
                       private=True)) != self.header:
            raise ErasureError('Wrong request instance')

    def initialize(self):
        require_root()
        with self.exclusive():
            with application_identity(self.settings):
                path = self.requests / 'instance.json'
                if os.path.lexists(path):
                    if decode(read(path, self.settings.erasure_application_uid, private=True)) != self.header:
                        raise ErasureError('Wrong request instance')
                else:
                    write(path, self.header, self.settings.erasure_application_uid, private=True)
                fsync_directory(self.requests)
            path = self.root / 'instance.json'
            if os.path.lexists(path):
                if decode(read(path, 0)) != self.header:
                    raise ErasureError('Wrong authority instance')
            else:
                write(path, self.header, 0)
            fsync_directory(self.root)
        self.check()

    @contextmanager
    def exclusive(self):
        require_root()
        import fcntl
        path = self.root / 'authority.lock'
        if not os.path.lexists(path):
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            os.close(fd)
            fsync_directory(self.root)
        checked_path(path, 0, private=True)
        with os.fdopen(os.open(path, os.O_RDWR | os.O_NOFOLLOW), 'rb') as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def request(self, operation_id):
        self.check()
        value = decode(read(self.requests / (identifier(operation_id) + '.json'),
                            self.settings.erasure_application_uid, private=True))
        validate_request(value, self.header)
        if value['id'] != operation_id:
            raise ErasureError('Request identity mismatch')
        return value

    def operation(self, operation_id):
        self.check()
        value = decode(read(self.root / ('op-' + identifier(operation_id) + '.json'), 0))
        validate_request(value['request'], self.header)
        if value['request']['id'] != operation_id or value['plan_sha256'] != fingerprint(value['plan']):
            raise ErasureError('Operation binding mismatch')
        return value

    def operations(self):
        self.check()
        return [self.operation(path.name[3:-5]) for path in sorted(self.root.glob('op-*.json'))]

    def save(self, op, phase):
        require_root()
        op['phase'] = phase
        op['events'].append({'phase': phase, 'at': timestamp()})
        write(self.root / ('op-' + op['request']['id'] + '.json'), op, 0, replace=True)


def validate_request(value, header):
    if (not isinstance(value, dict) or set(value) != {
            'version', 'instance', 'id', 'kind', 'user', 'owner', 'target', 'received_at'}
            or value['version'] != 1 or value['instance'] != header['instance']
            or value['kind'] not in ('document', 'account')):
        raise ErasureError('Invalid request')
    for field in ('id', 'user', 'owner', 'target'):
        identifier(value[field])
    expected = str(uuid5(NAMESPACE_URL, ':'.join(
        ['docnelo-erasure-v1', value['instance'], value['kind'], value['user'], value['owner'], value['target']])))
    if value['id'] != expected or value['kind'] == 'account' and value['target'] != value['user']:
        raise ErasureError('Request scope mismatch')
    if datetime.fromisoformat(value['received_at']).utcoffset() is None:
        raise ErasureError('Request timestamp required')


def submit(session, settings, user, document_id=None, *, administrative=False):
    if session.get_bind().dialect.name != 'postgresql':
        raise ErasureError('PostgreSQL required')
    authority = Authority(settings)
    authority.check()
    if administrative:
        require_maintenance(settings, session)
    elif os.geteuid() != settings.erasure_application_uid:
        raise ErasureError('The API must use its unprivileged identity')
    kind, target = ('account', user.id) if document_id is None else ('document', document_id)
    value = {'version': 1, 'instance': str(settings.erasure_instance_id), 'kind': kind,
             'user': str(user.id), 'owner': str(user.owner_id), 'target': str(target),
             'received_at': timestamp()}
    value['id'] = str(uuid5(NAMESPACE_URL, ':'.join(
        ['docnelo-erasure-v1', value['instance'], kind, value['user'], value['owner'], value['target']])))
    path = authority.requests / (value['id'] + '.json')
    if os.path.lexists(path):
        authority.request(value['id'])
    else:
        if document_id is not None:
            document = session.get(Document, document_id)
            if document is None or document.owner_id != user.owner_id:
                raise ErasureError('Document ownership required')
        with application_identity(settings):
            try:
                write(path, value, settings.erasure_application_uid, private=True)
            except (FileExistsError, ErasureError):
                authority.request(value['id'])
    with application_identity(settings):
        fsync_directory(authority.requests)
        authority.request(value['id'])
    return {'operation_id': value['id'], 'requested': True, 'completed': False,
            'state': 'requested', 'message': 'Demande persistante. Aucun effacement encore confirmé.'}


def require_root():
    if sys.platform != 'linux' or os.geteuid() != 0:
        raise ErasureError('Explicit Linux root authority required')


def require_maintenance(settings, session):
    require_root()
    Authority(settings).check()
    checked_path(settings.recovery_state_path, 0)
    if (read_recovery_state(settings.recovery_state_path) != 'quarantined'
            or settings.registration_mode != 'disabled'
            or session.get_bind().dialect.name != 'postgresql'):
        raise ErasureError('Offline quarantined PostgreSQL installation required')
    quota = session.get(PublicRegistrationQuota, 'public', populate_existing=True)
    if quota is None or not quota.closed or quota.issued_count < 0:
        raise ErasureError('Closed, consistent cumulative quota required')
    if session.execute(text("SELECT 1 FROM pg_stat_activity WHERE datname=current_database() "
                            "AND backend_type='client backend' AND pid<>pg_backend_pid() LIMIT 1")).first():
        raise ErasureError('Stop API and all other database clients before administrative erasure')
    return quota.issued_count


@contextmanager
def existing_holds(settings, request, files):
    from .lifecycle_durability import configured_coordinator
    from .lifecycle_holds import configured_hold_guard
    from .lifecycle_registry import configured_registry
    with ExitStack() as stack:
        with application_identity(settings):
            coordinator = configured_coordinator(settings, configured_registry(settings))
            scopes = [('account', request['user']), ('owner', request['owner'])]
            scopes += [('document', item['id']) for item in files]
            stack.enter_context(configured_hold_guard(settings, scopes, coordinator))
        yield


def source(settings, document):
    root = checked_path(settings.storage_dir, settings.erasure_application_uid, directory=True, private=True)
    if not STORAGE_NAME.fullmatch(document.storage_name):
        raise ErasureError('Unsafe document identity')
    path = checked_path(root / document.storage_name, settings.erasure_application_uid, private=True)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        before, current = os.fstat(stream.fileno()), path.lstat()
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    if ((before.st_dev, before.st_ino) != (current.st_dev, current.st_ino)
            or before.st_size != document.size_bytes or digest != document.sha256):
        raise ErasureError('Document source changed')
    return {'id': str(document.id), 'owner': str(document.owner_id), 'name': document.storage_name,
            'size': document.size_bytes, 'sha256': digest, 'device': before.st_dev, 'inode': before.st_ino}


def verify_source(settings, item):
    document = Document(id=UUID(item['id']), owner_id=UUID(item['owner']), storage_name=item['name'],
                        size_bytes=item['size'], sha256=item['sha256'])
    if source(settings, document) != item:
        raise ErasureError('Source replaced after authorization')


def schema(session):
    inspector = inspect(session.connection())
    actual = set(inspector.get_table_names())
    if actual != set(Base.metadata.tables) | {'alembic_version'}:
        raise ErasureError('Unknown database dependencies require review')
    if (any(name not in ('public', 'information_schema') and not name.startswith('pg_')
            for name in inspector.get_schema_names())
            or inspector.get_view_names() or inspector.get_materialized_view_names()
            or session.execute(text("SELECT 1 FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
                "JOIN pg_namespace n ON n.oid=c.relnamespace WHERE NOT t.tgisinternal "
                "AND n.nspname='public' LIMIT 1")).first()):
        raise ErasureError('Unknown database storage or triggers require review')
    columns = inspector.get_multi_columns()
    foreign_keys = inspector.get_multi_foreign_keys()
    for name, table in Base.metadata.tables.items():
        if {c['name'] for c in columns[(None, name)]} != set(table.c.keys()):
            raise ErasureError('Unknown database columns require review')
        expected = {(tuple(f.column_keys), f.referred_table.name,
                     tuple(e.column.name for e in f.elements), f.ondelete, f.onupdate)
                    for f in table.foreign_key_constraints}
        actual_keys = {(tuple(f['constrained_columns']), f['referred_table'],
                        tuple(f['referred_columns']), f['options'].get('ondelete'), f['options'].get('onupdate'))
                       for f in foreign_keys[(None, name)]}
        if actual_keys != expected:
            raise ErasureError('Unknown database foreign keys require review')
    return sorted(actual)


def inventory(session, request):
    from .ai.models import AIReservation
    from .ai.long_models import LongSummaryJob
    from .rag.models import IndexJob, OperationDocument, RAGDocument, RAGResult
    owner, user_id = UUID(request['owner']), UUID(request['user'])
    user = session.get(User, user_id, populate_existing=True)
    if user is None or user.owner_id != owner:
        raise ErasureError('Account identity changed')
    if len(session.scalars(select(User.id).where(User.owner_id == owner)).all()) != 1:
        raise ErasureError('Shared account scope requires review')
    for model, condition in (
            (AIReservation, AIReservation.status == 'reserved'),
            (LongSummaryJob, LongSummaryJob.status.not_in(['completed', 'cancelled'])),
            (IndexJob, IndexJob.status.in_(['queued', 'running']))):
        if session.scalar(select(model.id).where(model.owner_id == owner, condition).limit(1)):
            raise ErasureError('Active work requires reconciliation')
    docs = select(Document.id).where(Document.owner_id == owner)
    if request['kind'] == 'document':
        docs = docs.where(Document.id == UUID(request['target']))
    doc_ids = session.scalars(docs).all()
    if request['kind'] == 'document' and len(doc_ids) != 1:
        raise ErasureError('Document no longer matches request')
    reservations = set(session.scalars(select(OperationDocument.reservation_id).where(
        OperationDocument.document_id.in_(doc_ids))))
    reservations.update(session.scalars(select(AIReservation.id).where(AIReservation.document_id.in_(doc_ids))))
    results = set(session.scalars(select(RAGDocument.result_id).where(RAGDocument.document_id.in_(doc_ids))))
    if request['kind'] == 'account':
        reservations.update(session.scalars(select(AIReservation.id).where(AIReservation.owner_id == owner)))
        results.update(session.scalars(select(RAGResult.id).where(RAGResult.owner_id == owner)))
    reservations.update(session.scalars(select(RAGResult.reservation_id).where(
        RAGResult.id.in_(results), RAGResult.reservation_id.is_not(None))))
    for table in Base.metadata.sorted_tables:
        if 'document_id' in table.c and 'reservation_id' in table.c:
            reservations.update(session.scalars(select(table.c.reservation_id).where(
                table.c.document_id.in_(doc_ids), table.c.reservation_id.is_not(None))))
    for table in Base.metadata.sorted_tables:
        if 'document_id' in table.c and 'reservation_id' in table.c:
            if session.execute(select(table).where(table.c.reservation_id.in_(reservations),
                    table.c.document_id.not_in(doc_ids)).limit(1)).first():
                raise ErasureError('Shared reservation requires a wider reviewed request')
    if (session.scalar(select(AIReservation.id).where(
            AIReservation.id.in_(reservations), AIReservation.owner_id != owner).limit(1))
            or session.scalar(select(RAGResult.id).where(
                RAGResult.id.in_(results), RAGResult.owner_id != owner).limit(1))):
        raise ErasureError('Cross-owner derived dependency')
    if session.scalar(select(OperationDocument.document_id).where(
            OperationDocument.reservation_id.in_(reservations),
            OperationDocument.document_id.not_in(doc_ids)).limit(1)):
        raise ErasureError('Shared reservation requires a wider reviewed request')
    if session.scalar(select(Document.id).join(RAGDocument).where(
            RAGDocument.result_id.in_(results), Document.owner_id != owner).limit(1)):
        raise ErasureError('Cross-owner derived dependency')
    jobs = select(LongSummaryJob.id).where(LongSummaryJob.document_id.in_(doc_ids))
    rows = {}
    for table in Base.metadata.sorted_tables:
        columns = table.c
        if request['kind'] == 'account' and 'owner_id' in columns:
            condition = columns.owner_id == owner
        elif table.name == 'users' and request['kind'] == 'account':
            condition = columns.id == user_id
        elif table.name in ('workspace_memberships', 'account_deletion_requests') and request['kind'] == 'account':
            condition = columns.user_id == user_id
        elif table.name == 'account_tokens' and request['kind'] == 'account':
            condition = columns.email == user.email
        elif table.name == 'documents':
            condition = columns.id.in_(doc_ids)
        elif 'document_id' in columns:
            condition = columns.document_id.in_(doc_ids)
        elif table.name == 'summary_steps':
            condition = columns.job_id.in_(jobs)
        elif table.name == 'ai_reservations':
            condition = columns.id.in_(reservations)
        elif table.name == 'rag_results':
            condition = columns.id.in_(results)
        else:
            continue
        if 'reservation_id' in columns and request['kind'] == 'document':
            condition = or_(condition, columns.reservation_id.in_(reservations))
        if table.name == 'rag_documents':
            condition = or_(condition, columns.result_id.in_(results))
        values = session.execute(select(table).where(condition)).mappings().all()
        if 'owner_id' in columns and any(row['owner_id'] != owner for row in values):
            raise ErasureError('Cross-owner SQL dependency')
        if 'document_id' in columns and any(
                row['document_id'] is not None and row['document_id'] not in doc_ids for row in values):
            raise ErasureError('Document dependency outside reviewed scope')
        rows[table.name] = sorted(
            ({'key': [str(row[c.name]) for c in table.primary_key], 'sha256': fingerprint(dict(row))}
             for row in values), key=lambda row: row['key'])
    return rows


def fresh_session(settings):
    engine = make_engine(settings.database_url)
    return engine, make_sessions(engine)


def verify_storage_inventory(session, settings):
    root = checked_path(settings.storage_dir, settings.erasure_application_uid, directory=True, private=True)
    referenced = set(session.scalars(select(Document.storage_name)))
    if any(path.name not in referenced for path in root.iterdir()):
        raise ErasureError('Unattributed storage residue requires review')


def plan(settings, operation_id):
    authority = Authority(settings)
    with authority.exclusive():
        request = authority.request(operation_id)
        path = authority.root / ('op-' + operation_id + '.json')
        if path.exists() and authority.operation(operation_id)['phase'] != 'planned':
            raise ErasureError('Authorized operation cannot be replanned')
        engine, sessions = fresh_session(settings)
        try:
            with sessions() as session:
                count = require_maintenance(settings, session)
                rows = inventory(session, request)
                docs = session.scalars(select(Document).where(
                    Document.owner_id == UUID(request['owner']))).all()
                if request['kind'] == 'document':
                    docs = [doc for doc in docs if str(doc.id) == request['target']]
                files = sorted((source(settings, doc) for doc in docs), key=lambda item: item['id'])
                verify_storage_inventory(session, settings)
                with existing_holds(settings, request, files):
                    user = session.get(User, UUID(request['user']))
                    email_hash = fingerprint(user.email) if request['kind'] == 'account' and user.email else None
                    payload = {'rows': rows, 'files': files, 'schema': schema(session),
                               'issued_count': count, 'account_token_email_sha256': email_hash}
            op = {'request': request, 'plan': payload, 'plan_sha256': fingerprint(payload),
                  'authorization': None, 'events': [], 'phase': 'planned'}
            authority.save(op, 'planned')
            return summary(op)
        finally:
            engine.dispose()


def authorize(settings, operation_id, confirmation, policy_path, identity_evidence):
    if confirmation != operation_id:
        raise ErasureError('Exact operation confirmation required')
    authority = Authority(settings)
    with authority.exclusive():
        op = authority.operation(operation_id)
        if op['phase'] != 'planned':
            raise ErasureError('Only a planned request can be authorized')
        policy = decode(read(policy_path, 0, private=True))
        required = {'version', 'policy_id', 'approved_by', 'approved_at', 'owner_accounting',
                    'backup_retention_days', 'log_retention_days', 'receipt_retention'}
        if (set(policy) != required or policy['version'] != 1 or policy['owner_accounting'] != 'erase'
                or policy['receipt_retention'] != 'until_restore_sources_expire'):
            raise ErasureError('Explicit supported retention decision required')
        identifier(policy['policy_id'])
        identifier(policy['approved_by'])
        if datetime.fromisoformat(policy['approved_at']).utcoffset() is None:
            raise ErasureError('Policy approval timestamp required')
        if any(type(policy[k]) is not int or not 1 <= policy[k] <= 3650
               for k in ('backup_retention_days', 'log_retention_days')):
            raise ErasureError('Explicit backup and log retention required')
        evidence = read(identity_evidence, 0, private=True)
        if not evidence:
            raise ErasureError('Independent identity review evidence required')
        engine, sessions = fresh_session(settings)
        try:
            with sessions() as session:
                if require_maintenance(settings, session) != op['plan']['issued_count']:
                    raise ErasureError('Admission history changed')
                if schema(session) != op['plan']['schema'] or inventory(session, op['request']) != op['plan']['rows']:
                    raise ErasureError('SQL plan changed')
                with existing_holds(settings, op['request'], op['plan']['files']):
                    for item in op['plan']['files']:
                        verify_source(settings, item)
                    op['authorization'] = {'plan_sha256': op['plan_sha256'], 'policy': policy,
                                           'identity_sha256': hashlib.sha256(evidence).hexdigest(),
                                           'at': timestamp(), 'uid': 0}
                    authority.save(op, 'authorized')
            return summary(op)
        finally:
            engine.dispose()


def primary_key(table, values):
    return [UUID(value) if getattr(column.type, 'python_type', None) is UUID else value
            for column, value in zip(table.primary_key, values)]


def absence(session, settings, op):
    if schema(session) != op['plan']['schema']:
        raise ErasureError('Schema changed since authorization')
    for name, rows in op['plan']['rows'].items():
        table = Base.metadata.tables[name]
        for offset in range(0, len(rows), 500):
            keys = [tuple(primary_key(table, row['key'])) for row in rows[offset:offset + 500]]
            if session.execute(select(table).where(tuple_(*table.primary_key).in_(keys)).limit(1)).first():
                return False
    if op['request']['kind'] == 'account':
        for table in Base.metadata.sorted_tables:
            if 'owner_id' in table.c and session.execute(select(table).where(
                    table.c.owner_id == UUID(op['request']['owner'])).limit(1)).first():
                return False
        email_hash = op['plan']['account_token_email_sha256']
        if email_hash and any(fingerprint(email) == email_hash for email in session.scalars(select(AccountToken.email))):
            return False
    for item in op['plan']['files']:
        if session.scalar(select(Document.id).where(Document.storage_name == item['name']).limit(1)):
            return False
    document_ids = [UUID(item['id']) for item in op['plan']['files']]
    for table in Base.metadata.sorted_tables:
        if 'document_id' in table.c and session.execute(select(table).where(
                table.c.document_id.in_(document_ids)).limit(1)).first():
            return False
    return True


def remove_rows(session, op):
    models = {mapper.local_table.name: mapper.class_ for mapper in Base.registry.mappers}
    for table in reversed(Base.metadata.sorted_tables):
        for row in op['plan']['rows'].get(table.name, []):
            obj = session.get(models[table.name], tuple(primary_key(table, row['key'])))
            if obj is not None:
                session.delete(obj)
        session.flush()
        session.expire_all()


def writer_fence(session, owner):
    from .ai.models import AIBudget
    from .account_models import Workspace
    if session.scalar(select(AIBudget.id).where(AIBudget.id == 'development').with_for_update()) is None:
        raise ErasureError('Shared writer fence missing')
    session.scalar(select(Workspace).where(Workspace.owner_id == owner).with_for_update())


def execute(settings, operation_id, confirmation):
    if confirmation != operation_id:
        raise ErasureError('Exact operation confirmation required')
    authority = Authority(settings)
    with authority.exclusive():
        op = authority.operation(operation_id)
        if not op['authorization'] or op['authorization']['plan_sha256'] != op['plan_sha256']:
            raise ErasureError('Independent administrative authorization required')
        if op['phase'] == 'active_verified':
            raise ErasureError('Verified operations require verification, never replay')
        engine, sessions = fresh_session(settings)
        try:
            with sessions() as session:
                count = require_maintenance(settings, session)
                if count != op['plan']['issued_count']:
                    raise ErasureError('Admission history changed')
                with existing_holds(settings, op['request'], op['plan']['files']):
                    writer_fence(session, UUID(op['request']['owner']))
                    if not absence(session, settings, op):
                        if inventory(session, op['request']) != op['plan']['rows']:
                            raise ErasureError('Partial or changed SQL state requires review')
                        for item in op['plan']['files']:
                            verify_source(settings, item)
                        authority.save(op, 'executing')
                        remove_rows(session, op)
                        try:
                            session.commit()
                        except BaseException:
                            discard_session(session)
                            raise
                    else:
                        session.rollback()
                    # The prior writer fence must be released before the independent connection.
                    with sessions() as check:
                        writer_fence(check, UUID(op['request']['owner']))
                        if not absence(check, settings, op):
                            raise ErasureError('SQL commit is not established')
                    authority.save(op, 'files_pending')
                    for item in op['plan']['files']:
                        path = settings.storage_dir / item['name']
                        if os.path.lexists(path):
                            verify_source(settings, item)
                            path.unlink()
                        fsync_directory(path.parent)
                    authority.save(op, 'verification_pending')
            return summary(op)
        except BaseException:
            authority.save(op, 'failed')
            raise
        finally:
            engine.dispose()


def verify(settings, operation_id):
    authority = Authority(settings)
    with authority.exclusive():
        op = authority.operation(operation_id)
        if (not op['authorization']
                or op['authorization']['plan_sha256'] != op['plan_sha256']
                or op['phase'] not in ('executing', 'files_pending', 'verification_pending',
                                       'failed', 'active_verified')):
            raise ErasureError('Administrative authorization required')
        engine, sessions = fresh_session(settings)
        try:
            with sessions() as session:
                count = require_maintenance(settings, session)
                with existing_holds(settings, op['request'], op['plan']['files']):
                    if count < op['plan']['issued_count'] or not absence(session, settings, op):
                        raise ErasureError('SQL residue or restored identity remains')
                    fsync_directory(settings.storage_dir)
                    verify_files_absent(settings, op)
                    verify_storage_inventory(session, settings)
                    authority.save(op, 'active_verified')
            return summary(op)
        except BaseException:
            authority.save(op, 'failed')
            raise
        finally:
            engine.dispose()


def verify_files_absent(settings, op):
    checked_path(settings.storage_dir, settings.erasure_application_uid, directory=True, private=True)
    for item in op['plan']['files']:
        for name in (item['name'], item['name'] + '.deleted', Path(item['name']).stem + '.part'):
            if os.path.lexists(settings.storage_dir / name):
                raise ErasureError('Physical residue remains')


def runtime_guard(settings, session, *, startup=False):
    if not enabled(settings):
        return
    if os.geteuid() != settings.erasure_application_uid:
        raise ErasureError('API must not run as root or another identity')
    authority = Authority(settings)
    operations = authority.operations()
    for op in operations:
        if op['phase'] == 'planned':
            continue
        if op['phase'] != 'active_verified':
            raise ErasureError('Administrative erasure/reconciliation pending')
        quota = session.get(PublicRegistrationQuota, 'public', populate_existing=True)
        if quota is None or quota.issued_count < op['plan']['issued_count'] or not absence(session, settings, op):
            raise ErasureError('Erased identities or admission history reappeared')
        verify_files_absent(settings, op)
    if startup and any(op['phase'] == 'active_verified' for op in operations):
        verify_storage_inventory(session, settings)


def summary(op):
    active = op['phase'] == 'active_verified'
    return {'operation_id': op['request']['id'], 'state': op['phase'],
            'active_erasure_verified': active, 'completed': False,
            'backups': 'retention_pending', 'logs': 'retention_pending'}
