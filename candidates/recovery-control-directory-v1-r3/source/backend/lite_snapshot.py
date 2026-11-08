"""Versioned Lite captures and conservative, isolated recovery.

The operator ledger and its keys are never payloads. A successful restore is
quarantined, not an authorization to resume application writers.
"""
from contextlib import closing, contextmanager
import hashlib
import io
import os
from pathlib import Path
import re
import secrets
import shutil
import sqlite3
import subprocess
import tarfile
import tempfile
from uuid import uuid4

from sqlalchemy import create_engine, inspect, select, text

from .account_models import PublicRegistrationQuota
from .auth import User
from .lifecycle_snapshot import STORES, _schema, _snapshot
from .lite_authority import (AuthorityError, canonical, digest, hex64,
                             read, secure_path, strict, timestamp, uuid, view, write)
from .lite_deletions import no_workers, source
from .models import Document
from .recovery_quarantine import read_recovery_state


STORE_ATTRIBUTES = {
    'registry': 'lifecycle_registry_path',
    'witness': 'lifecycle_confirmation_path',
    'authenticated': 'lifecycle_authenticated_confirmation_path',
    'holds': 'lifecycle_holds_path',
    'admission_anchor': 'lifecycle_admission_anchor_path',
}
KEY_ATTRIBUTES = ('lifecycle_authentication_key_path', 'lifecycle_admission_key_path')
LOCAL_TABLES = {'operations', 'metadata', 'deletions', 'retired_admissions'}
CONTROL_NAME = re.compile(r'(?:accepted|effect-[0-9a-f-]{36}|fence-[0-9a-f-]{36})\.json')
PAYLOADS = {'database.dump', 'application.tar.gz'}
MAX_CAPSULE_BYTES = 256 * 1024 * 1024


def root_required():
    if os.name != 'posix' or os.geteuid() != 0:
        raise AuthorityError('Lite capture and recovery require a POSIX administrator')


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read_blob(path):
    path = secure_path(path, 0)
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        info, current = os.fstat(stream.fileno()), path.lstat()
        if ((info.st_dev, info.st_ino) != (current.st_dev, current.st_ino)
                or info.st_size > MAX_CAPSULE_BYTES):
            raise AuthorityError('Changed or oversized lab capsule (256 MiB maximum)')
        return stream.read(MAX_CAPSULE_BYTES+1)


def write_blob(path, raw):
    path = Path(path)
    secure_path(path.parent, 0, directory=True)
    if len(raw) > MAX_CAPSULE_BYTES:
        raise AuthorityError('Lab capsule exceeds the explicit 256 MiB limit')
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'wb') as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
    if file_hash(path) != hashlib.sha256(raw).hexdigest():
        raise AuthorityError('Lab capsule readback differs')


def store_paths(settings):
    paths = {name: Path(getattr(settings, attribute)) for name, attribute in STORE_ATTRIBUTES.items()}
    if len(set(paths.values())) != 5:
        raise AuthorityError('Five distinct lifecycle paths required')
    for path in paths.values():
        secure_path(path, path.lstat().st_uid)
    if any(a.parent == b.parent or a.parent in b.parents or b.parent in a.parents
           for i, a in enumerate(paths.values()) for b in list(paths.values())[i+1:]):
        raise AuthorityError('Separate lifecycle store directories required')
    return paths


@contextmanager
def sqlite_copy(path, *, local=False, name=None):
    """Use SQLite's backup API, including committed WAL pages, never a hot file copy."""
    path = Path(path)
    secure_path(path, path.lstat().st_uid)
    if not local:
        target, metadata = _snapshot(path, name)
        try:
            yield target
        finally:
            metadata['_temporary'].cleanup()
        return
    with tempfile.TemporaryDirectory(prefix='.lite-snapshot-', dir=path.parent) as directory:
        target = Path(directory) / 'operations.sqlite'
        original = sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)
        copied = sqlite3.connect(target)
        target.chmod(0o600)
        try:
            original.backup(copied)
            validate_local(copied)
            if copied.execute('PRAGMA journal_mode=DELETE').fetchone()[0] != 'delete':
                raise AuthorityError('Local cache journal normalization failed')
            copied.commit()
        finally:
            copied.close()
            original.close()
        yield target


def validate_local(connection):
    tables = {r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
    if (tables != LOCAL_TABLES
            or connection.execute('PRAGMA user_version').fetchone()[0] != 0
            or connection.execute('PRAGMA integrity_check').fetchone()[0] != 'ok'):
        raise AuthorityError('Unexpected or damaged Lite cache')


def sql_fingerprints(connection):
    result = {}
    preparer = connection.dialect.identifier_preparer
    for name in sorted(inspect(connection).get_table_names(schema='public')):
        table = preparer.quote_schema('public')+'.'+preparer.quote(name)
        rows = connection.scalars(text(f'SELECT row_to_json(t)::text FROM {table} AS t')).all()
        result[name] = {'count': len(rows), 'sha256': digest(sorted(rows))}
    return result


def schema(connection):
    versions = connection.scalars(text('SELECT version_num FROM alembic_version')).all()
    major = int(connection.scalar(text("SHOW server_version_num"))) // 10000
    if versions != ['0007'] or major != 17:
        raise AuthorityError('Lite snapshot requires the qualified PostgreSQL 17/schema 0007 pair')
    return {'migration': '0007', 'postgresql_major': major}


def no_clients(connection):
    count = connection.scalar(text(
        "SELECT count(*) FROM pg_stat_activity WHERE datname=current_database() "
        "AND backend_type='client backend' AND pid<>pg_backend_pid()"))
    if count:
        raise AuthorityError('Another PostgreSQL client prevents offline capture/recovery')
    if connection.scalar(text("SELECT count(*) FROM pg_prepared_xacts WHERE database=current_database()")):
        raise AuthorityError('Prepared SQL transactions require reconciliation')


def pg_command(engine, executable, arguments, *, output=None):
    url = engine.url
    if engine.dialect.name != 'postgresql' or not url.host or not url.port or not url.username:
        raise AuthorityError('Explicit PostgreSQL host/port/user/database required')
    executable = shutil.which(executable)
    if executable is None:
        raise AuthorityError('PostgreSQL client executable unavailable')
    env = os.environ.copy()
    for key in ('PGSERVICE', 'PGSERVICEFILE', 'PGPASSFILE', 'PGOPTIONS', 'PGDATABASE'):
        env.pop(key, None)
    env['PGPASSWORD'] = url.password or ''
    env['PGSSLMODE'] = str(url.query.get('sslmode', 'prefer'))
    subprocess.run([executable, '--host', url.host, '--port', str(url.port),
                    '--username', url.username, '--dbname', url.database, *arguments],
                   env=env, stdout=output or subprocess.PIPE, stderr=subprocess.PIPE,
                   check=True, timeout=3600)


def document_inventory(session, settings):
    documents = [source(settings, doc) for doc in session.scalars(select(Document).order_by(Document.id))]
    root = Path(settings.storage_dir)
    secure_path(root, root.lstat().st_uid, directory=True)
    if {p.name for p in root.iterdir()} != {d['name'] for d in documents}:
        raise AuthorityError('Unattributed or missing document file')
    users = {str(u.id): str(u.owner_id) for u in session.scalars(select(User))}
    if any(d['owner'] not in users.values() for d in documents):
        raise AuthorityError('Document owner cannot be corroborated')
    return documents, users


def add_file(archive, path, name, entries, *, private=True, uid=None):
    path = Path(path)
    secure_path(path, path.lstat().st_uid if uid is None else uid, private=private)
    info = tarfile.TarInfo(name)
    info.size = path.stat().st_size
    info.mode = 0o600
    with path.open('rb') as stream:
        archive.addfile(info, stream)
    entries[name] = {'size': info.size, 'sha256': file_hash(path)}


def capture(settings, adapter, session, destination, *, candidate, offline_confirmed=False):
    """Offline capture only. Stopping privileged external writers remains an operator duty."""
    from .lite_deletions import application_identity, require_profile
    from .lifecycle_backup_lock import lifecycle_store_lock
    root_required()
    hex64(candidate)
    require_profile(settings, adapter)
    if not offline_confirmed:
        raise AuthorityError('Explicit API/CLI/jobs/external-SQL shutdown attestation required')
    paths = store_paths(settings)
    if any(p.lstat().st_uid != adapter.store.uid for p in paths.values()):
        raise AuthorityError('Lifecycle store owner differs from provisioned application')
    destination = Path(destination)
    secure_path(destination.parent, 0, directory=True)
    with adapter.exclusive():
        # Lifecycle stores are application-owned; acquire their common barrier as that UID.
        with application_identity(adapter):
            barrier = lifecycle_store_lock(exclusive=True, required=True)
            barrier.__enter__()
        try:
            no_clients(session.connection())
            version = schema(session.connection())
            quota = session.get(PublicRegistrationQuota, 'public', populate_existing=True)
            operations, committed = adapter._proof()
            if (not quota or not quota.closed or quota.issued_count != committed
                    or any(e['phase'] in ('reserve', 'authorize') for e in operations.values())
                    or any(o.state == 'uncertain' for o in adapter.store.all())):
                raise AuthorityError('Close admissions and resolve uncertain/unfinished operations before capture')
            payloads = adapter.store.payloads()
            from .lite_authority import RECOVERY_KINDS
            application_operations = {k: e for k, e in operations.items() if e['operation']['kind'] not in RECOVERY_KINDS}
            if (any(payloads.get(k) != e['operation'] for k, e in application_operations.items())
                    or set(payloads) != set(application_operations)):
                raise AuthorityError('Local evidence does not cover the signed authority history')
            for user in session.scalars(select(User)):
                no_workers(session, user.owner_id)
            documents, users = document_inventory(session, settings)
            fingerprints = sql_fingerprints(session.connection())
            destination.mkdir(mode=0o700)
            with (destination/'database.dump').open('xb') as dump:
                os.chmod(destination/'database.dump', 0o600)
                pg_command(session.get_bind(), 'pg_dump', ['--format=custom', '--no-owner'], output=dump)
                dump.flush()
                os.fsync(dump.fileno())
            entries = {}
            with tarfile.open(destination/'application.tar.gz', 'x:gz') as archive:
                os.chmod(destination/'application.tar.gz', 0o600)
                for name, path in paths.items():
                    with sqlite_copy(path, name=name) as copied:
                        add_file(archive, copied, f'lifecycle/{name}.sqlite', entries)
                with sqlite_copy(adapter.store.path, local=True) as copied:
                    add_file(archive, copied, 'lite/operations.sqlite', entries)
                for path in sorted(adapter.control.iterdir()):
                    if path.name == 'authority.lock' or path.name == 'inbox':
                        continue
                    if not CONTROL_NAME.fullmatch(path.name):
                        raise AuthorityError('Unclassified administrative control file')
                    add_file(archive, path, 'control/'+path.name, entries, private=False, uid=0)
                if 'control/accepted.json' not in entries:
                    raise AuthorityError('Accepted Lite proof missing')
                for attribute in KEY_ATTRIBUTES:
                    path = Path(getattr(settings, attribute))
                    if len(read(path, path.lstat().st_uid)) != 32:
                        raise AuthorityError('Invalid local lifecycle authentication key')
                    add_file(archive, path, 'application_keys/'+attribute, entries)
                for doc in documents:
                    add_file(archive, Path(settings.storage_dir)/doc['name'], 'documents/'+doc['name'], entries)
            with (destination/'application.tar.gz').open('rb') as stream:
                os.fsync(stream.fileno())
            no_clients(session.connection())
            if fingerprints != sql_fingerprints(session.connection()):
                raise AuthorityError('SQL changed during capture')
            after_documents, after_users = document_inventory(session, settings)
            if documents != after_documents or users != after_users:
                raise AuthorityError('Document scope changed during capture')
            accepted = strict(read(adapter.control/'accepted.json', 0, private=False))
            bound, _, _ = view(accepted, adapter.public_key, adapter.instance,
                               str(adapter.cohort_id), adapter.nonce)
            manifest = {
                'backup_format_version': 4, 'profile': 'beta_lite', 'capture_id': str(uuid4()),
                'instance': adapter.instance, 'cohort': str(adapter.cohort_id), 'candidate': candidate,
                'schema': version, 'created_at': timestamp(), 'complete': True,
                'authority_sequence': bound['sequence'], 'authority_head': bound['head'],
                'authority_public_key': adapter.public_key, 'issued_count': committed,
                'sql': fingerprints, 'documents': documents, 'users': users, 'entries': entries,
                'sha256': {name: file_hash(destination/name) for name in sorted(PAYLOADS)},
                'quiescence': {'offline_attested': True, 'sql_clients_checked': True,
                               'lite_lock': True, 'lifecycle_lock': True,
                               'privileged_host_writers': 'trusted_operator_boundary'},
                'operator_domain_included': False, 'opening_authorized': False,
            }
            write(destination/'manifest.json', canonical(manifest), 0)
            verify_capture(destination, expected_sha256=file_hash(destination/'manifest.json'),
                           instance=adapter.instance, cohort=str(adapter.cohort_id), candidate=candidate)
            return manifest
        finally:
            barrier.__exit__(None, None, None)


def verify_capture(snapshot, *, expected_sha256, instance, cohort, candidate):
    root_required()
    snapshot = secure_path(snapshot, 0, directory=True)
    raw = read(snapshot/'manifest.json', 0)
    if hashlib.sha256(raw).hexdigest() != hex64(expected_sha256):
        raise AuthorityError('Manifest differs from the independently retained digest')
    manifest = strict(raw)
    if (manifest.get('backup_format_version') != 4 or manifest.get('profile') != 'beta_lite'
            or manifest.get('instance') != uuid(instance) or manifest.get('cohort') != uuid(cohort)
            or manifest.get('candidate') != hex64(candidate)
            or manifest.get('schema') != {'migration': '0007', 'postgresql_major': 17}
            or manifest.get('complete') is not True or manifest.get('opening_authorized') is not False
            or manifest.get('operator_domain_included') is not False
            or set(manifest.get('sha256', {})) != PAYLOADS
            or {p.name for p in snapshot.iterdir()} != PAYLOADS | {'manifest.json'}):
        raise AuthorityError('Wrong, incomplete or incompatible Lite snapshot')
    uuid(manifest['capture_id'])
    for name in PAYLOADS:
        path = secure_path(snapshot/name, 0)
        if file_hash(path) != manifest['sha256'][name]:
            raise AuthorityError('Snapshot payload checksum mismatch')
    required = {f'lifecycle/{name}.sqlite' for name in STORES}
    required |= {'lite/operations.sqlite', 'control/accepted.json'}
    required |= {'application_keys/'+attribute for attribute in KEY_ATTRIBUTES}
    entries = manifest.get('entries', {})
    documents = manifest.get('documents', [])
    for doc in documents:
        if not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|txt)', doc['name']):
            raise AuthorityError('Unsafe document archive identity')
        uuid(doc['id']); uuid(doc['owner']); hex64(doc['sha256'])
        required.add('documents/'+doc['name'])
    if not required <= set(entries):
        raise AuthorityError('Lite snapshot lacks a required store')
    for name in set(entries)-required:
        if not name.startswith('control/') or not CONTROL_NAME.fullmatch(name[8:]):
            raise AuthorityError('Unapproved Lite snapshot entry')
    with tarfile.open(snapshot/'application.tar.gz', 'r:gz') as archive:
        members = archive.getmembers()
        if len(members) != len(entries) or {m.name for m in members} != set(entries):
            raise AuthorityError('Archive is not the exact declared Lite set')
        for member in members:
            if not member.isfile() or member.mode & 0o077:
                raise AuthorityError('Links, devices and unsafe archive modes refused')
            expected = entries[member.name]
            stream = archive.extractfile(member)
            if (member.size != expected['size'] or stream is None
                    or hashlib.file_digest(stream, 'sha256').hexdigest() != expected['sha256']):
                raise AuthorityError('Archive entry checksum mismatch')
        with tempfile.TemporaryDirectory(prefix='lite-capture-verify-') as temporary:
            for name in STORES:
                stream = archive.extractfile(f'lifecycle/{name}.sqlite')
                if stream is None:
                    raise AuthorityError('Missing lifecycle snapshot')
                path = Path(temporary)/f'{name}.sqlite'
                path.write_bytes(stream.read())
                with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as connection:
                    _schema(connection, name)
            stream = archive.extractfile('lite/operations.sqlite')
            if stream is None:
                raise AuthorityError('Missing Lite snapshot')
            path = Path(temporary)/'operations.sqlite'
            path.write_bytes(stream.read())
            with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as connection:
                validate_local(connection)
                challenge = connection.execute('SELECT challenge FROM metadata WHERE id=1').fetchone()
                if challenge is None:
                    raise AuthorityError('Lite snapshot challenge missing')
            proof = archive.extractfile('control/accepted.json')
            if proof is None:
                raise AuthorityError('Accepted snapshot proof missing')
            bound, _, count = view(strict(proof.read()), manifest['authority_public_key'],
                instance, cohort, challenge[0])
            if (bound['sequence'] != manifest['authority_sequence'] or bound['head'] != manifest['authority_head']
                    or count != manifest['issued_count']):
                raise AuthorityError('Snapshot and authority bounds differ')
    return manifest


def encrypted_copy(snapshot, output, key_path, *, manifest_sha256):
    """Separate lab support and key custody must be established by the caller."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    root_required()
    snapshot, output, key_path = Path(snapshot), Path(output), Path(key_path)
    if (output.parent == key_path.parent or output.is_relative_to(snapshot)
            or key_path.is_relative_to(snapshot)):
        raise AuthorityError('Separate snapshot, copy and key locations required')
    if file_hash(snapshot/'manifest.json') != hex64(manifest_sha256):
        raise AuthorityError('Encrypted copy manifest identity mismatch')
    key = read(key_path, 0)
    if len(key) != 32:
        raise AuthorityError('Separate 256-bit recovery key required')
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode='w:gz') as archive:
        for name in sorted(PAYLOADS | {'manifest.json'}):
            archive.add(Path(snapshot)/name, name, recursive=False)
    aad = bytes.fromhex(hex64(manifest_sha256))
    nonce = secrets.token_bytes(12)
    raw = nonce+AESGCM(key).encrypt(nonce, buffer.getvalue(), aad)
    write_blob(output, raw)
    if decrypt_copy(output, key_path, manifest_sha256=manifest_sha256) != buffer.getvalue():
        raise AuthorityError('Independent encrypted copy failed readback')
    return file_hash(output)


def decrypt_copy(path, key_path, *, manifest_sha256):
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    root_required()
    raw = read_blob(path)
    try:
        return AESGCM(read(key_path, 0)).decrypt(
            raw[:12], raw[12:], bytes.fromhex(hex64(manifest_sha256)))
    except (InvalidTag, ValueError):
        raise AuthorityError('Encrypted copy is incomplete, altered or uses another key') from None


def recover_encrypted_copy(path, key_path, destination, *, manifest_sha256, instance, cohort, candidate):
    root_required()
    raw = decrypt_copy(path, key_path, manifest_sha256=manifest_sha256)
    destination = Path(destination)
    secure_path(destination.parent, 0, directory=True)
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as archive:
        members = archive.getmembers()
        if (len(members) != 3 or {m.name for m in members} != PAYLOADS | {'manifest.json'}
                or any(not m.isfile() or m.mode & 0o077 for m in members)):
            raise AuthorityError('Encrypted snapshot contains an unsafe or incomplete set')
        destination.mkdir(mode=0o700)
        for member in members:
            stream = archive.extractfile(member)
            if stream is None:
                raise AuthorityError('Encrypted snapshot entry missing')
            write_blob(destination/member.name, stream.read(MAX_CAPSULE_BYTES+1))
    return verify_capture(destination, expected_sha256=manifest_sha256,
                          instance=instance, cohort=cohort, candidate=candidate)


def restore(snapshot, *, root, database, admin_url, expected_sha256, instance, cohort, candidate):
    """Restore once into a marked fresh lab DB and a new private filesystem destination."""
    from tools.validate_restore import _validate_lab
    root_required()
    root = Path(root)
    _validate_lab(Path(snapshot), database, root)
    secure_path(root, 0, directory=True)
    manifest = verify_capture(snapshot, expected_sha256=expected_sha256, instance=instance,
                              cohort=cohort, candidate=candidate)
    target = root/database
    if os.path.lexists(target):
        raise AuthorityError('Destination already used; inspect the quarantined attempt')
    if (admin_url.get_backend_name() != 'postgresql' or admin_url.host not in ('127.0.0.1', '::1')
            or admin_url.database != 'documind_restore_admin' or admin_url.port is None):
        raise AuthorityError('Explicit loopback isolated restore administrator required')
    admin = create_engine(admin_url, isolation_level='AUTOCOMMIT')
    try:
        with admin.connect() as connection:
            if connection.scalar(text("SHOW cluster_name")) != 'documind-restore-lab':
                raise AuthorityError('Unmarked PostgreSQL cluster')
            if connection.scalar(text('SELECT 1 FROM pg_database WHERE datname=:name'), {'name': database}):
                raise AuthorityError('PostgreSQL destination already exists')
            # Filesystem reservation is durable before creating/restoring SQL.
            target.mkdir(mode=0o700)
            write(target/'recovery-state.json', canonical({'format': 1, 'state': 'quarantined'}), 0)
            identity = {'destination': str(uuid4()), 'database': database, 'instance': instance,
                        'cohort': cohort, 'candidate': candidate, 'manifest_sha256': expected_sha256,
                        'challenge': secrets.token_hex(32), 'opening_authorized': False}
            write(target/'destination.json', canonical(identity), 0)
            connection.execute(text(f'CREATE DATABASE "{database}"'))
    finally:
        admin.dispose()
    engine = create_engine(admin_url.set(database=database))
    try:
        pg_command(engine, 'pg_restore', ['--no-owner', '--exit-on-error', str(Path(snapshot)/'database.dump')])
        with engine.connect() as connection:
            if schema(connection) != manifest['schema'] or sql_fingerprints(connection) != manifest['sql']:
                raise AuthorityError('Restored SQL differs from the captured set')
        with tarfile.open(Path(snapshot)/'application.tar.gz', 'r:gz') as archive:
            for member in archive:
                path = target/member.name
                path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
                with path.open('xb') as output:
                    os.chmod(path, 0o600)
                    stream = archive.extractfile(member)
                    if stream is None:
                        raise AuthorityError('Missing restore stream')
                    shutil.copyfileobj(stream, output)
                    output.flush()
                    os.fsync(output.fileno())
        with engine.begin() as connection:
            connection.execute(text("UPDATE public_registration_quota SET closed=true WHERE id='public'"))
        for directory in ('documents', 'control', 'lite', 'lifecycle', 'application_keys'):
            (target/directory).mkdir(mode=0o700, exist_ok=True)
        with closing(sqlite3.connect((target/'lite/operations.sqlite').as_uri()+'?mode=ro', uri=True)) as cache:
            validate_local(cache)
        for name in STORES:
            with sqlite_copy(target/f'lifecycle/{name}.sqlite', name=name):
                pass
        for doc in manifest['documents']:
            path = target/'documents'/doc['name']
            if path.stat().st_size != doc['size'] or file_hash(path) != doc['sha256']:
                raise AuthorityError('Restored active document differs')
        # A fresh challenge cannot be replaced by the one restored from the old cache.
        return {'status': 'quarantined', 'destination': identity['destination'],
                'documents_verified': len(manifest['documents']), 'lifecycle_stores': 5,
                'lite_cache': True, 'opening_authorized': False}
    finally:
        engine.dispose()


def assess_recovery(target, snapshot, engine, envelope, *, confirmation, offline_confirmed=False):
    """Read-only assessment. No synthetic confirmations, repair, unlink or latch promotion."""
    root_required()
    target = secure_path(target, 0, directory=True)
    identity = strict(read(target/'destination.json', 0))
    if not offline_confirmed or confirmation != identity['destination']:
        raise AuthorityError('Explicit destination and offline confirmation required')
    if read_recovery_state(target/'recovery-state.json') != 'quarantined':
        raise AuthorityError('Recovery destination must remain quarantined')
    manifest = verify_capture(snapshot, expected_sha256=identity['manifest_sha256'],
                              instance=identity['instance'], cohort=identity['cohort'],
                              candidate=identity['candidate'])
    if engine.url.database != identity['database']:
        raise AuthorityError('Wrong recovery database')
    current, operations, committed = view(envelope, manifest['authority_public_key'],
        identity['instance'], identity['cohort'], identity['challenge'])
    if (current['sequence'] < manifest['authority_sequence']
            or (digest(current['events'][manifest['authority_sequence']-1])
                if manifest['authority_sequence'] else '') != manifest['authority_head']):
        raise AuthorityError('Current authority does not extend the capture')
    reasons = []
    with engine.connect() as connection:
        no_clients(connection)
        if schema(connection) != manifest['schema']:
            raise AuthorityError('Incompatible restored schema')
        row = connection.execute(text(
            "SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")).one()
        if not row.closed:
            raise AuthorityError('Restored admissions must remain closed')
        if row.issued_count != committed:
            reasons.append('cumulative_counter_conflict')
        users = {str(u): str(o) for u, o in connection.execute(text('SELECT id,owner_id FROM users'))}
        for entry in operations.values():
            op = entry['operation']
            if op['kind'] == 'admission' and entry['phase'] == 'result':
                if users.get(op['user_id']) != op['owner_id']:
                    reasons.append('admission_sql_not_reconstructible')
            elif op['kind'] == 'admission' and entry['phase'] == 'reserve':
                reasons.append('uncertain_reservation')
            elif op['kind'] != 'admission':
                # Signed plans include source inode/device and SQL hashes. Restoration
                # changes these identities; 3B's authorization must not be weakened.
                reasons.append('deletion_requires_destination_bound_reconciliation')
        docs = connection.execute(text('SELECT storage_name,sha256,size_bytes FROM documents')).all()
        for name, checksum, size in docs:
            if not re.fullmatch(r'[0-9a-f]{32}\.(?:pdf|txt)', name):
                raise AuthorityError('Unsafe restored document name')
            path = secure_path(target/'documents'/name, 0)
            if path.stat().st_size != size or file_hash(path) != checksum:
                reasons.append('active_document_integrity_conflict')
    # Neither a fresh view of admissions/deletions nor the old holds database
    # proves completeness of post-capture holds or newly uploaded active documents.
    reasons.extend(['current_holds_completeness_unproven', 'current_active_documents_completeness_unproven'])
    report = {'format': 1, 'status': 'blocked', 'destination': identity['destination'],
              'manifest_sha256': identity['manifest_sha256'], 'candidate': identity['candidate'],
              'authority_sequence': current['sequence'], 'authority_head': current['head'],
              'counter_restored': row.issued_count, 'counter_independent': committed,
              'reasons': sorted(set(reasons)), 'opening_authorized': False,
              'quarantine_release_authorized': False}
    write(target/'recovery-assessment.json', canonical(report), 0, replace=True)
    return report
