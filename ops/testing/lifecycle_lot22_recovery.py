"""Disposable PostgreSQL 0007 recovery exercise; only fixed synthetic paths and hosts."""
import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import tarfile
from types import SimpleNamespace
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.engine import make_url

from backend.account_api import PasswordInput, deletion
from backend.account_admin import purge_account
from backend.account_models import DeletionRequest, PublicRegistrationQuota, Workspace, WorkspaceMembership
from backend.auth import SessionVault, User, hash_password
from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.lifecycle_admissions import AdmissionAnchor, configured_admissions
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore, configured_coordinator
from backend.lifecycle_holds import HoldStore, configured_hold_guard
from backend.lifecycle_registry import Registry
from backend.models import Document, DocumentPage, now
from backend.resource_limits import RateLimiter
from backend.services.document_integrity import check_document_integrity
from backend.services.documents import delete_document
from ops.testing.lifecycle_lot22_backup import PersistentSyntheticBackups
from tools.validate_restore import seal_restored_registration


ROOT = Path('/synthetic')
REGISTRY = ROOT / 'registry' / 'primary' / 'registry.sqlite'
WITNESS = ROOT / 'witness' / 'witness.sqlite'
PROOF = ROOT / 'proof' / 'proof.sqlite'
HOLDS = ROOT / 'holds' / 'holds.sqlite'
ANCHOR = ROOT / 'anchor' / 'anchor.sqlite'
AUTH_KEY = ROOT / 'keys' / 'auth' / 'synthetic.key'
ANCHOR_KEY = ROOT / 'keys' / 'anchor' / 'synthetic.key'
BACKUP_KEYS = {version: ROOT / 'keys' / 'backup' / (version + '.key') for version in ('v1', 'v2')}
COPIES, ALERTS = ROOT / 'copies', ROOT / 'alerts'
SOURCE = ROOT / 'data' / 'source'
RECOVERED = ROOT / 'recovery' / 'registry' / 'registry.sqlite'
RESTORED = ROOT / 'recovery' / 'documents'
EVIDENCE = ROOT / 'evidence'
PASSWORD = 'synthetic-only-password-123'


def environment():
    if os.environ.get('PHASE154L22_SYNTHETIC') != 'isolated':
        raise ValueError('Synthetic-only execution required')
    url = make_url(os.environ['DATABASE_URL'])
    if (url.get_backend_name(), url.host, url.username, url.database) != (
            'postgresql', 'phase154l22-db', 'phase154l22', 'phase154l22'):
        raise ValueError('Dedicated disposable PostgreSQL required')
    os.umask(0o077)
    for path in (REGISTRY.parent, WITNESS.parent, PROOF.parent, HOLDS.parent, ANCHOR.parent,
                 AUTH_KEY.parent, ANCHOR_KEY.parent, BACKUP_KEYS['v1'].parent, COPIES, ALERTS,
                 SOURCE, RECOVERED.parent, RESTORED, EVIDENCE):
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    (ROOT / '.synthetic-only').write_bytes(b'documind-synthetic-only\n')
    return url


def settings(url, *, restored=False):
    database = 'phase154l22_restore' if restored else 'phase154l22'
    return Settings(_env_file=None, database_url=url.set(database=database).render_as_string(hide_password=False),
                    storage_dir=RESTORED if restored else SOURCE,
                    lifecycle_registry_path=RECOVERED if restored else REGISTRY,
                    lifecycle_confirmation_path=WITNESS, lifecycle_authenticated_confirmation_path=PROOF,
                    lifecycle_authentication_key_path=AUTH_KEY, lifecycle_holds_path=HOLDS,
                    lifecycle_admission_anchor_path=ANCHOR, lifecycle_admission_key_path=ANCHOR_KEY,
                    lifecycle_durable_receipts_required=True, lifecycle_synthetic_mutations_enabled=True,
                    registration_mode='disabled',
                    public_registration_limit=5, ai_enabled=False, owner_demo_enabled=False,
                    legacy_api_enabled=False)


def key(path):
    descriptor = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        value = os.urandom(32)
        if os.write(descriptor, value) != len(value):
            raise OSError('Incomplete synthetic key')
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def write_json(name, content):
    path = EVIDENCE / name
    with path.open('x', encoding='utf-8') as stream:
        json.dump(content, stream, sort_keys=True)
    print(json.dumps({'stage': name, 'passed': True}, sort_keys=True))


def create_user(session, index):
    owner = uuid4()
    session.add(Workspace(owner_id=owner))
    session.flush()
    user = User(owner_id=owner, username=f'synthetic-{index}', email=f'synthetic-{index}@example.test',
                password_hash=hash_password(PASSWORD), registration_kind='public',
                email_verified_at=now(), terms_version='synthetic', terms_accepted_at=now())
    session.add(user)
    session.flush()
    session.add(WorkspaceMembership(user_id=user.id, owner_id=owner))
    return user


def create_document(session, owner, index):
    content = f'synthetic-document-{index}'.encode()
    name = uuid4().hex + '.txt'
    (SOURCE / name).write_bytes(content)
    document = Document(owner_id=owner, filename='synthetic.txt', storage_name=name, media_type='text/plain',
                        size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    session.add(document)
    session.flush()
    session.add(DocumentPage(document_id=document.id, page_number=1, text=content.decode()))
    return document


def backup(registry, active='v1'):
    return PersistentSyntheticBackups(registry, COPIES, ALERTS, BACKUP_KEYS, active, ROOT)


def bootstrap(url):
    for path in (REGISTRY, WITNESS, PROOF, HOLDS, ANCHOR, AUTH_KEY, ANCHOR_KEY, *BACKUP_KEYS.values()):
        if path.exists():
            raise ValueError('Synthetic bootstrap requires empty volumes')
    for path in (AUTH_KEY, ANCHOR_KEY, *BACKUP_KEYS.values()):
        key(path)
    registry = Registry(REGISTRY)
    registry.initialize()
    witness = ConfirmationStore(WITNESS)
    witness.initialize()
    authenticated = AuthenticatedConfirmationStore(PROOF, AUTH_KEY.read_bytes(), 'documind-local-v2')
    authenticated.initialize()
    HoldStore(HOLDS, authenticated).initialize()
    AdmissionAnchor(ANCHOR, ANCHOR_KEY.read_bytes()).initialize()
    cfg = settings(url)
    command.upgrade(Config('/app/alembic.ini'), '0007')
    engine = make_engine(cfg.database_url)
    try:
        admissions = configured_admissions(cfg, configured_coordinator(cfg, registry))
        users = []
        for index in (1, 2):
            with make_sessions(engine)() as session:
                user = create_user(session, index)
                quota = session.get(PublicRegistrationQuota, 'public')
                quota.issued_count, quota.closed = index, True
                admissions.reserve(index, user.id)
                session.commit()
                admissions.settle(index, user.id)
                users.append((user.id, user.owner_id))
        with make_sessions(engine)() as session:
            documents = [create_document(session, users[0][1], 1),
                         create_document(session, users[1][1], 2),
                         create_document(session, users[1][1], 3)]
            session.commit()
            manifest = {'account': str(users[0][0]), 'erase_documents': [str(documents[0].id), str(documents[1].id)],
                        'keep_document': str(documents[2].id),
                        'hashes': {str(document.id): document.sha256 for document in documents}}
        with tarfile.open(EVIDENCE / 'synthetic-documents.tar', 'x') as archive:
            for path in sorted(SOURCE.iterdir()):
                archive.add(path, arcname=path.name)
        assert check_document_integrity(engine, SOURCE)['consistent']
        baseline = backup(registry).daily(datetime.now(timezone.utc))
        manifest['baseline_copy'] = baseline.name
        write_json('snapshot.json', manifest)
    finally:
        engine.dispose()


def make_hold(kind, identifier):
    current = datetime.now(timezone.utc)
    return {'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(identifier),
            'scope_kind': kind, 'reason': 'legal_hold', 'reviewed_at': current,
            'review_at': current + timedelta(days=29), 'ends_at': None,
            'end_event': 'legal_hold_lifted'}, current


def mutate(url):
    manifest = json.loads((EVIDENCE / 'snapshot.json').read_text(encoding='utf-8'))
    cfg, registry = settings(url), Registry(REGISTRY)
    coordinator = configured_coordinator(cfg, registry)
    admissions = configured_admissions(cfg, coordinator)
    hold_store = HoldStore(HOLDS, coordinator.authenticated)
    copies = backup(registry, 'v2')
    engine = make_engine(cfg.database_url)
    try:
        with make_sessions(engine)() as session:
            third = create_user(session, 3)
            session.get(PublicRegistrationQuota, 'public').issued_count = 3
            admissions.reserve(3, third.id)
            session.commit()
            admissions.settle(3, third.id)
        held, timestamp = make_hold('document', manifest['erase_documents'][1])
        hold_store.create(held, timestamp)
        copies.after_administrative_update(datetime.now(timezone.utc))
        with make_sessions(engine)() as session:
            try:
                delete_document(session, cfg, session.get(Document, UUID(manifest['erase_documents'][1])))
            except HTTPException as exc:
                if exc.status_code != 409:
                    raise
                session.rollback()
            else:
                raise AssertionError('Synthetic hold did not block deletion')
        hold_store.release(held['id'], held['responsible_id'], str(uuid4()),
                           b'synthetic release evidence', datetime.now(timezone.utc))
        keep_hold, timestamp = make_hold('document', manifest['keep_document'])
        hold_store.create(keep_hold, timestamp)
        copies.after_administrative_update(datetime.now(timezone.utc))
        with make_sessions(engine)() as session:
            user = session.get(User, UUID(manifest['account']))
            context = SimpleNamespace(user_id=user.id, owner_id=user.owner_id)
            state = SimpleNamespace(settings=cfg, rate_limiter=RateLimiter(), session_vault=SessionVault(600))
            request = SimpleNamespace(state=SimpleNamespace(user_session=context), app=SimpleNamespace(state=state))
            assert deletion(PasswordInput(password=PASSWORD), request, user.owner_id, session)['requested']
            copies.after_administrative_update(datetime.now(timezone.utc))
            for identifier in manifest['erase_documents']:
                delete_document(session, cfg, session.get(Document, UUID(identifier)))
                copies.after_administrative_update(datetime.now(timezone.utc))
            assert session.scalar(select(func.count()).select_from(Document)) == 1
            with_hold = session.get(Document, UUID(manifest['keep_document']))
            assert (SOURCE / with_hold.storage_name).exists()
            try:
                purge_account(session, cfg, user.id)
            except ValueError as exc:
                if 'Account purge disabled' not in str(exc):
                    raise
            else:
                raise AssertionError('Synthetic strict account purge unexpectedly enabled')
        latest = copies.after_administrative_update(datetime.now(timezone.utc))
        assert admissions.inspect(3)['state'] == 'observed_consistent'
        write_json('mutated.json', {'latest_copy': latest.name, 'witness_count': 3,
                                    'account_purge_blocked': True, 'active_hold': keep_hold['id']})
    finally:
        engine.dispose()


def replay(url):
    manifest = json.loads((EVIDENCE / 'snapshot.json').read_text(encoding='utf-8'))
    latest = json.loads((EVIDENCE / 'mutated.json').read_text(encoding='utf-8'))['latest_copy']
    if RECOVERED.exists() or any(RESTORED.iterdir()):
        raise ValueError('Synthetic recovery targets must be empty')
    _, plaintext = backup(Registry(REGISTRY), 'v2').restore(COPIES / latest)
    descriptor = os.open(RECOVERED, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(descriptor, 'wb', closefd=False) as stream:
            stream.write(plaintext)
            stream.flush()
            os.fsync(descriptor)
    finally:
        os.close(descriptor)
    with tarfile.open(EVIDENCE / 'synthetic-documents.tar') as archive:
        archive.extractall(RESTORED, filter='data')
    cfg, registry = settings(url, restored=True), Registry(RECOVERED)
    coordinator = configured_coordinator(cfg, registry)
    admissions = configured_admissions(cfg, coordinator)
    engine = make_engine(cfg.database_url)
    try:
        assert check_document_integrity(engine, RESTORED)['consistent']
        assert seal_restored_registration(engine)['closed']
        assert coordinator.verify_recovery_receipts()['complete_for_observed_stores']
        evidence = admissions.inspect(2)
        assert evidence['minimum_issued_count'] == 3 and evidence['state'] == 'reconciliation_required'
        with make_sessions(engine)() as session:
            user = session.get(User, UUID(manifest['account']))
            with registry.connection() as db:
                receipt = db.execute("SELECT id FROM requests WHERE user_id=? AND kind='erasure'",
                                     (str(user.id),)).fetchone()['id']
            assert coordinator.authenticated.verify(coordinator._operation('account', receipt)) == 'result_recorded'
            with configured_hold_guard(cfg, [('account', user.id), ('owner', user.owner_id)], coordinator):
                user.disabled_at = now()
                session.add(DeletionRequest(user_id=user.id, owner_id=user.owner_id))
                session.commit()
            for identifier in manifest['erase_documents']:
                document = session.get(Document, UUID(identifier))
                assert document.sha256 == manifest['hashes'][identifier]
                assert coordinator.authenticated.verify(coordinator._operation('document', identifier)) == 'result_recorded'
                account = session.scalar(select(User.id).where(User.owner_id == document.owner_id))
                scopes = [('owner', document.owner_id), ('document', document.id)]
                if account:
                    scopes.append(('account', account))
                path = RESTORED / document.storage_name
                with configured_hold_guard(cfg, scopes, coordinator):
                    if path.is_symlink() or hashlib.sha256(path.read_bytes()).hexdigest() != document.sha256:
                        raise ValueError('Synthetic replay source mismatch')
                    session.delete(document)
                    session.commit()
                    path.unlink()
            assert_active_hold_blocks(cfg, coordinator, manifest['keep_document'])
            quota = session.get(PublicRegistrationQuota, 'public')
            quota.issued_count, quota.closed = evidence['minimum_issued_count'], True
            session.commit()
            assert session.get(User, UUID(manifest['account'])).disabled_at is not None
            assert all(session.get(Document, UUID(identifier)) is None for identifier in manifest['erase_documents'])
            assert session.get(Document, UUID(manifest['keep_document'])) is not None
            assert quota.issued_count == 3 and quota.closed
        assert check_document_integrity(engine, RESTORED)['consistent']
        write_json('replayed.json', {'snapshot_counter': 2, 'reconciled_counter': 3,
                                   'registration_closed': True, 'account_deactivated': True,
                                   'account_purge_blocked': True, 'documents_replayed': 2,
                                   'active_hold_preserved': True, 'opening_authorized': False})
    finally:
        engine.dispose()


def assert_active_hold_blocks(cfg, coordinator, identifier):
    try:
        with configured_hold_guard(cfg, [('document', identifier)], coordinator):
            pass
    except ValueError as exc:
        if 'Active hold' not in str(exc):
            raise
        return
    raise AssertionError('Synthetic active hold did not survive recovery')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('bootstrap', 'mutate', 'replay'))
    stage = parser.parse_args().stage
    url = environment()
    {'bootstrap': bootstrap, 'mutate': mutate, 'replay': replay}[stage](url)


if __name__ == '__main__':
    main()
