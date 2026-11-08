"""Synthetic-only recovery recipe. No Docker socket, B2, SMTP or production defaults.

The orchestrator performs real pg_dump/pg_restore between these bounded stages.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tarfile
from uuid import UUID, uuid4

from alembic import command
from alembic.config import Config
from sqlalchemy import select, text, func
from sqlalchemy.engine import make_url

import backend.main  # Register the complete application metadata.
from backend.account_admin import purge_account, registration_control
from backend.account_models import Workspace, WorkspaceMembership, DeletionRequest, PublicRegistrationQuota
from backend.auth import User, hash_password
from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.lifecycle_registry import Registry
from backend.models import Document, DocumentPage, now
from backend.services.documents import delete_document
from backend.services.document_integrity import check_document_integrity
from tools.pending_lifecycle import run as pending_inventory
from tools.validate_restore import seal_restored_registration

DATA=Path('/data')
LEDGER=Path('/ledger')
EVIDENCE=Path('/evidence')
MARKER='SYNTHETIC_DOCUMENT_PRIVATE_MARKER'


def settings(database, storage):
    if os.environ.get('PHASE152_RECIPE')!='synthetic-only':
        raise ValueError('Explicit isolated recipe required')
    url=make_url(os.environ['DATABASE_URL'])
    if url.host!='phase152-db' or url.username!='phase152' or url.database!='documind_recovery_source':
        raise ValueError('Only the dedicated synthetic database host is allowed')
    if database not in ('documind_recovery_source','documind_restore_phase152'):
        raise ValueError('Only the two disposable recipe databases are allowed')
    return Settings(_env_file=None,database_url=url.set(database=database).render_as_string(hide_password=False),
                    storage_dir=DATA/storage,lifecycle_registry_path=LEDGER/'cases.sqlite',
                    registration_mode='disabled',ai_enabled=False,owner_demo_enabled=False,legacy_api_enabled=False,
                    lifecycle_durable_receipts_required=False)


def save(name, report):
    (EVIDENCE/name).write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps({'stage':name,'passed':True},sort_keys=True))


def add_user(session,index):
    owner=uuid4()
    session.add(Workspace(owner_id=owner));session.flush()
    user=User(owner_id=owner,username='synthetic-'+str(index),email=f'synthetic-{index}@example.test',
              password_hash=hash_password('Synthetic-only-password-phase152!'),registration_kind='public',
              email_verified_at=now(),terms_version='synthetic-only',terms_accepted_at=now())
    session.add(user);session.flush()
    session.add(WorkspaceMembership(user_id=user.id,owner_id=owner))
    return user


def add_document(session,root,user,index):
    content=f'{MARKER} {index}\n'.encode()
    name=uuid4().hex+'.txt'
    descriptor=os.open(root/name,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    with os.fdopen(descriptor,'wb') as stream:stream.write(content)
    document=Document(owner_id=user.owner_id,filename='synthetic-original-private.txt',storage_name=name,
                      media_type='text/plain',size_bytes=len(content),sha256=hashlib.sha256(content).hexdigest())
    session.add(document);session.flush()
    session.add(DocumentPage(document_id=document.id,page_number=1,text=content.decode()))
    return document


def bootstrap():
    cfg=settings('documind_recovery_source','source')
    cfg.storage_dir.mkdir(mode=0o700)
    os.environ['DATABASE_URL']=cfg.database_url
    command.upgrade(Config('/app/alembic.ini'),'0007')
    ledger=Registry(cfg.lifecycle_registry_path);ledger.initialize()
    engine=make_engine(cfg.database_url)
    try:
        with make_sessions(engine)() as session:
            a=add_user(session,1);b=add_user(session,2)
            documents=[add_document(session,cfg.storage_dir,a,1),add_document(session,cfg.storage_dir,b,2),
                       add_document(session,cfg.storage_dir,b,3)]
            quota=session.get(PublicRegistrationQuota,'public');quota.issued_count=2;quota.closed=True
            session.commit()
            manifest={'account_erasure':str(a.id),'retained_account':str(b.id),
                      'document_erasure':str(documents[1].id),'retained_document':str(documents[2].id),
                      'source_documents':{str(d.id):{'name':d.storage_name,'sha256':d.sha256} for d in documents},
                      'snapshot_counter':2,'snapshot_closed':True,'schema':'0007'}
        with tarfile.open(EVIDENCE/'synthetic-documents.tar.gz','w:gz') as archive:
            for path in sorted(cfg.storage_dir.iterdir()):archive.add(path,arcname=path.name)
        manifest['documents_archive_sha256']=hashlib.sha256((EVIDENCE/'synthetic-documents.tar.gz').read_bytes()).hexdigest()
        save('recovery-snapshot.json',manifest)
        assert check_document_integrity(engine,cfg.storage_dir)['consistent']
    finally:engine.dispose()


def mutate():
    cfg=settings('documind_recovery_source','source')
    manifest=json.loads((EVIDENCE/'recovery-snapshot.json').read_text())
    engine=make_engine(cfg.database_url)
    try:
        with make_sessions(engine)() as session:
            add_user(session,3)
            session.get(PublicRegistrationQuota,'public').issued_count=3
            user=session.get(User,UUID(manifest['account_erasure']))
            user.disabled_at=now();session.add(DeletionRequest(user_id=user.id,owner_id=user.owner_id));session.commit()
            purge_account(session,cfg,user.id)
            delete_document(session,cfg,session.get(Document,UUID(manifest['document_erasure'])))
            assert session.scalar(select(func.count()).select_from(User))==2
            assert session.scalar(select(func.count()).select_from(Document))==1
            assert session.get(PublicRegistrationQuota,'public').issued_count==3
        ledger=Registry(cfg.lifecycle_registry_path)
        plan=ledger.restore_plan(2)
        assert plan['minimum_issued_count']==3 and plan['opening_authorized'] is False
        assert len(plan['erasure_requests'])==1 and len(plan['document_erasures'])==2
        backup=LEDGER/'independent-backup.sqlite'
        with sqlite3.connect(ledger.path) as source,sqlite3.connect(backup) as target:source.backup(target)
        os.chmod(backup,0o600)
        inventory=pending_inventory(cfg,168)
        assert inventory['execution_enabled'] is False
        save('recovery-post-snapshot.json',{'source_counter':3,'users':2,'documents':1,
                                          'independent_receipts':True,'inventory_read_only':True})
    finally:engine.dispose()


def replay():
    cfg=settings('documind_restore_phase152','restored')
    manifest=json.loads((EVIDENCE/'recovery-snapshot.json').read_text())
    archive=EVIDENCE/'synthetic-documents.tar.gz'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['documents_archive_sha256']
    cfg.storage_dir.mkdir(mode=0o700)
    with tarfile.open(archive) as source:source.extractall(cfg.storage_dir,filter='data')
    engine=make_engine(cfg.database_url)
    try:
        # Prove fidelity BEFORE replaying post-snapshot deletion decisions.
        assert check_document_integrity(engine,cfg.storage_dir)['consistent']
        with make_sessions(engine)() as session:
            assert session.scalar(select(func.count()).select_from(User))==2
            assert session.scalar(select(func.count()).select_from(Document))==3
            quota=session.get(PublicRegistrationQuota,'public')
            assert quota.issued_count==2 and quota.closed is True
            for identifier,expected in manifest['source_documents'].items():
                document=session.get(Document,UUID(identifier))
                assert document.sha256==expected['sha256']
                assert hashlib.sha256((cfg.storage_dir/expected['name']).read_bytes()).hexdigest()==expected['sha256']
        save('restore-fidelity.json',{'pg_restore_executed_by_orchestrator':True,'users':2,'documents':3,
                                    'counter':2,'original_document_hashes_verified':True})
        seal_restored_registration(engine)
        # Missing/stale evidence is never interpreted as authorization to reopen.
        try:Registry(LEDGER/'missing.sqlite').restore_plan(2)
        except FileNotFoundError:pass
        else:raise AssertionError('Missing ledger was accepted')
        empty_dir=LEDGER/'empty-ledger';empty_dir.mkdir(mode=0o700)
        empty=Registry(empty_dir/'cases.sqlite');empty.initialize()
        assert empty.restore_plan(2)['watermark_present'] is False
        assert empty.restore_plan(2)['opening_authorized'] is False
        with make_sessions(engine)() as session:
            try:registration_control(session,cfg,'reopen',execute=True)
            except ValueError:pass
            else:raise AssertionError('Closed recovery profile reopened')
            assert session.get(PublicRegistrationQuota,'public').closed is True
        # Restore the independent ledger to a NEW private target, not from the app snapshot.
        recovered_dir=LEDGER/'recovered';recovered_dir.mkdir(mode=0o700)
        recovered_path=recovered_dir/'cases.sqlite'
        with sqlite3.connect(LEDGER/'independent-backup.sqlite') as source,sqlite3.connect(recovered_path) as target:
            source.backup(target)
        os.chmod(recovered_path,0o600)
        cfg.lifecycle_registry_path=recovered_path
        ledger=Registry(recovered_path)
        plan=ledger.restore_plan(2)
        assert plan['minimum_issued_count']==3
        assert len(plan['erasure_requests'])==1 and len(plan['document_erasures'])==2
        # Availability faults: private mode and locked writer must fail closed.
        os.chmod(recovered_path,0o644)
        try:ledger.restore_plan(2)
        except ValueError:pass
        else:raise AssertionError('Public ledger permissions accepted')
        os.chmod(recovered_path,0o600)
        with sqlite3.connect(recovered_path) as lock:
            lock.execute('BEGIN EXCLUSIVE')
            try:ledger.receive('access')
            except sqlite3.OperationalError:pass
            else:raise AssertionError('Locked ledger write unexpectedly succeeded')
        with make_sessions(engine)() as session:
            user=session.get(User,UUID(manifest['account_erasure']))
            user.disabled_at=now();session.add(DeletionRequest(user_id=user.id,owner_id=user.owner_id));session.commit()
            purge_account(session,cfg,user.id)
            delete_document(session,cfg,session.get(Document,UUID(manifest['document_erasure'])))
        # A real source counter, frozen throughout this replay, supplies authoritative evidence.
        source_engine=make_engine(settings('documind_recovery_source','source').database_url)
        try:
            with source_engine.connect() as connection:
                authoritative=connection.execute(text("SELECT issued_count,closed FROM public_registration_quota WHERE id='public'")).one()
                assert authoritative.issued_count==3 and authoritative.closed is True
        finally:source_engine.dispose()
        assert plan['minimum_issued_count']==authoritative.issued_count
        with engine.begin() as connection:
            connection.execute(text("UPDATE public_registration_quota SET issued_count=greatest(issued_count,:count),closed=true WHERE id='public'"),
                               {'count':authoritative.issued_count})
        with make_sessions(engine)() as session:
            assert session.get(User,UUID(manifest['account_erasure'])) is None
            assert session.get(Document,UUID(manifest['document_erasure'])) is None
            assert session.get(Document,UUID(manifest['retained_document'])) is not None
            assert session.scalar(select(func.count()).select_from(User))==1
            assert session.scalar(select(func.count()).select_from(Document))==1
            quota=session.get(PublicRegistrationQuota,'public');assert quota.issued_count==3 and quota.closed is True
        assert check_document_integrity(engine,cfg.storage_dir)['consistent']
        contents=recovered_path.read_bytes()
        assert b'@example.test' not in contents and MARKER.encode() not in contents
        assert b'synthetic-original-private.txt' not in contents
        save('recovery-replayed.json',{'real_database_restore':True,'restored_counter_before':2,'counter_after':3,
                                      'account_erasure_reapplied':True,'document_erasure_reapplied':True,
                                      'retained_documents':1,'retained_users':1,'source_counter_unchanged':3,
                                      'ledger_restored_independently':True,'unavailable_and_locked_ledger_rejected':True,
                                      'missing_or_incomplete_evidence_did_not_reopen':True,'registration_closed':True,
                                      'ai_enabled':cfg.ai_enabled,'registry_minimized':True})
    finally:engine.dispose()


def main():
    os.umask(0o077)
    parser=argparse.ArgumentParser();parser.add_argument('stage',choices=('bootstrap','mutate','replay'))
    args=parser.parse_args()
    {'bootstrap':bootstrap,'mutate':mutate,'replay':replay}[args.stage]()


if __name__=='__main__':main()
