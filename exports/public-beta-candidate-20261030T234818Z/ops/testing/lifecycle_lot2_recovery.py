"""Disposable PostgreSQL recovery recipe; synthetic data and private mounts only."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tarfile
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import func, select, text
from sqlalchemy.engine import make_url

import backend.main
from backend.account_admin import purge_account
from backend.account_models import DeletionRequest, PublicRegistrationQuota, Workspace, WorkspaceMembership
from backend.auth import User, hash_password
from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.lifecycle_durability import ConfirmationStore, DurableCoordinator
from backend.lifecycle_registry import Registry
from backend.models import Document, DocumentPage, now
from backend.services.document_integrity import check_document_integrity
from backend.services.documents import delete_document
from ops.testing.lifecycle_lot2_backup import encrypted_snapshot, verify_snapshot
from tools.validate_restore import seal_restored_registration

DATA, LEDGER, EVIDENCE = Path('/data'), Path('/ledger'), Path('/evidence')


def settings(database, directory, ledger):
    if os.environ.get('PHASE154L2_RECIPE') != 'synthetic-only':
        raise ValueError('Synthetic recipe required')
    url = make_url(os.environ['DATABASE_URL'])
    if (url.host, url.username, url.database) != ('phase154l2-db', 'phase154l2', 'phase154l2'):
        raise ValueError('Dedicated disposable database required')
    if database not in ('phase154l2', 'phase154l2_restore'):
        raise ValueError('Invalid synthetic database')
    return Settings(_env_file=None, database_url=url.set(database=database).render_as_string(hide_password=False),
                    storage_dir=DATA / directory, lifecycle_registry_path=ledger,
                    lifecycle_confirmation_path=LEDGER / 'independent' / 'confirm.sqlite',
                    lifecycle_durable_receipts_required=True, registration_mode='disabled',
                    ai_enabled=False, owner_demo_enabled=False, legacy_api_enabled=False)


def write_json(name, content):
    (EVIDENCE / name).write_text(json.dumps(content, sort_keys=True), encoding='utf-8')
    print(json.dumps({'stage': name, 'passed': True}))


def user(session, index):
    owner = uuid4()
    session.add(Workspace(owner_id=owner))
    session.flush()
    result = User(owner_id=owner, username=f'synthetic-{index}', email=f'synthetic-{index}@example.test',
                  password_hash=hash_password('synthetic-only-password-123'),
                  registration_kind='public', email_verified_at=now(),
                  terms_version='synthetic', terms_accepted_at=now())
    session.add(result)
    session.flush()
    session.add(WorkspaceMembership(user_id=result.id, owner_id=owner))
    return result


def document(session, root, owner, index):
    content = f'synthetic-document-{index}'.encode()
    name = uuid4().hex + '.txt'
    (root / name).write_bytes(content)
    result = Document(owner_id=owner, filename='synthetic.txt', storage_name=name, media_type='text/plain',
                      size_bytes=len(content), sha256=hashlib.sha256(content).hexdigest())
    session.add(result)
    session.flush()
    session.add(DocumentPage(document_id=result.id, page_number=1, text=content.decode()))
    return result


def bootstrap():
    (LEDGER / 'primary').mkdir(mode=0o700)
    (LEDGER / 'independent').mkdir(mode=0o700)
    registry = Registry(LEDGER / 'primary' / 'registry.sqlite')
    registry.initialize()
    store = ConfirmationStore(LEDGER / 'independent' / 'confirm.sqlite')
    store.initialize()
    (DATA / 'source').mkdir(mode=0o700)
    cfg = settings('phase154l2', 'source', registry.path)
    os.environ['DATABASE_URL'] = cfg.database_url
    command.upgrade(Config('/app/alembic.ini'), '0007')
    engine = make_engine(cfg.database_url)
    try:
        with make_sessions(engine)() as session:
            a, b = user(session, 1), user(session, 2)
            docs = [document(session, cfg.storage_dir, a.owner_id, 1),
                    document(session, cfg.storage_dir, b.owner_id, 2),
                    document(session, cfg.storage_dir, b.owner_id, 3)]
            store.reserve_admission(1, a.id)
            store.reserve_admission(2, b.id)
            quota = session.get(PublicRegistrationQuota, 'public')
            quota.issued_count, quota.closed = 2, True
            session.commit()
            manifest = {'account': str(a.id), 'erase_document': str(docs[1].id),
                        'keep_document': str(docs[2].id),
                        'hashes': {str(d.id): d.sha256 for d in docs}}
        with tarfile.open(EVIDENCE / 'synthetic-documents.tar.gz', 'w:gz') as archive:
            for path in sorted(cfg.storage_dir.iterdir()):
                archive.add(path, arcname=path.name)
        assert check_document_integrity(engine, cfg.storage_dir)['consistent']
        write_json('snapshot.json', manifest)
    finally:
        engine.dispose()


def mutate():
    manifest = json.loads((EVIDENCE / 'snapshot.json').read_text(encoding='utf-8'))
    registry = Registry(LEDGER / 'primary' / 'registry.sqlite')
    store = ConfirmationStore(LEDGER / 'independent' / 'confirm.sqlite')
    cfg = settings('phase154l2', 'source', registry.path)
    engine = make_engine(cfg.database_url)
    try:
        with make_sessions(engine)() as session:
            third = user(session, 3)
            store.reserve_admission(3, third.id)
            session.get(PublicRegistrationQuota, 'public').issued_count = 3
            account = session.get(User, UUID(manifest['account']))
            account.disabled_at = now()
            session.add(DeletionRequest(user_id=account.id, owner_id=account.owner_id))
            session.commit()
            purge_account(session, cfg, account.id)
            delete_document(session, cfg, session.get(Document, UUID(manifest['erase_document'])))
            assert session.scalar(select(func.count()).select_from(Document)) == 1
        key = os.urandom(32)
        (LEDGER / 'independent' / 'synthetic.key').write_bytes(key)
        (LEDGER / 'independent' / 'registry.aesgcm').write_bytes(encrypted_snapshot(registry, key))
        with store.connection() as db:
            count = db.execute('SELECT count(*) FROM confirmations').fetchone()[0]
            assert count == 3
        assert store.restore_evidence(2)['witness_count'] == 3
        write_json('after-snapshot.json', {'source_count': 3, 'confirmation_count': count})
    finally:
        engine.dispose()


def replay():
    manifest = json.loads((EVIDENCE / 'snapshot.json').read_text(encoding='utf-8'))
    recovered_dir = LEDGER / 'recovered'
    recovered_dir.mkdir(mode=0o700)
    recovered = recovered_dir / 'registry.sqlite'
    key = (LEDGER / 'independent' / 'synthetic.key').read_bytes()
    ciphertext = (LEDGER / 'independent' / 'registry.aesgcm').read_bytes()
    recovered.write_bytes(verify_snapshot(ciphertext, key))
    os.chmod(recovered, 0o600)
    cfg = settings('phase154l2_restore', 'restored', recovered)
    cfg.storage_dir.mkdir(mode=0o700)
    with tarfile.open(EVIDENCE / 'synthetic-documents.tar.gz') as archive:
        archive.extractall(cfg.storage_dir, filter='data')
    engine = make_engine(cfg.database_url)
    try:
        assert check_document_integrity(engine, cfg.storage_dir)['consistent']
        with make_sessions(engine)() as session:
            assert session.scalar(select(func.count()).select_from(User)) == 2
            assert session.scalar(select(func.count()).select_from(Document)) == 3
            assert session.get(PublicRegistrationQuota, 'public').issued_count == 2
            for identifier, expected in manifest['hashes'].items():
                assert session.get(Document, UUID(identifier)).sha256 == expected
        seal_restored_registration(engine)
        ledger = Registry(recovered)
        store = ConfirmationStore(cfg.lifecycle_confirmation_path)
        assert DurableCoordinator(ledger, store).verify_recovery_receipts()['complete_for_observed_stores']
        plan = ledger.restore_plan(2)
        assert len(plan['erasure_requests']) == 1 and len(plan['document_erasures']) == 2
        assert store.restore_evidence(2)['minimum_issued_count'] == 3
        assert store.restore_evidence(2)['opening_authorized'] is False
        with make_sessions(engine)() as session:
            account = session.get(User, UUID(manifest['account']))
            account.disabled_at = now()
            session.add(DeletionRequest(user_id=account.id, owner_id=account.owner_id))
            session.commit()
            purge_account(session, cfg, account.id)
            delete_document(session, cfg, session.get(Document, UUID(manifest['erase_document'])))
        with engine.begin() as connection:
            connection.execute(text("UPDATE public_registration_quota SET issued_count=GREATEST(issued_count,3), "
                                    "closed=true WHERE id='public'"))
        with make_sessions(engine)() as session:
            assert session.get(User, UUID(manifest['account'])) is None
            assert session.get(Document, UUID(manifest['erase_document'])) is None
            assert session.get(Document, UUID(manifest['keep_document'])) is not None
            quota = session.get(PublicRegistrationQuota, 'public')
            assert quota.issued_count == 3 and quota.closed is True
        assert check_document_integrity(engine, cfg.storage_dir)['consistent']
        write_json('replayed.json', {'snapshot_counter': 2, 'reconciled_counter': 3,
                                    'erasure_reapplied': True, 'registration_closed': True,
                                    'encrypted_registry_restored': True, 'ai_enabled': False})
    finally:
        engine.dispose()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=('bootstrap', 'mutate', 'replay'))
    stage = parser.parse_args().stage
    {'bootstrap': bootstrap, 'mutate': mutate, 'replay': replay}[stage]()


if __name__ == '__main__':
    main()
