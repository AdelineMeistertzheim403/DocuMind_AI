"""All fixtures are temporary; no VPS, SMTP, B2 or real provider access."""
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.lifecycle_registry import Registry
from backend.account_admin import plan_pending_cleanup, purge_pending, purge_account
from backend.account_models import AccountToken, PublicRegistrationQuota
from backend.auth import User
from backend.maintenance import reconcile, reconciliation_plan
from backend.models import now
from tests.test_public_beta import beta, enroll, verify_and_login, PASSWORD
from tools import retention_production as retention
from tests.test_retention import inventory, NOW


@pytest.fixture
def registry(tmp_path):
    directory=tmp_path/'ledger'
    directory.mkdir(mode=0o700)
    ledger=Registry(directory/'cases.sqlite')
    ledger.initialize()
    return ledger


def test_registry_retention_requires_decision_and_restore_evidence(registry):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    user,owner=uuid4(),uuid4()
    identifier=registry.receive('erasure',user_id=user,owner_id=owner,received_at=start)
    assert registry.receive('erasure',user_id=user,owner_id=owner)==identifier
    registry.finish(identifier,closed_at=start+timedelta(days=1))
    assert registry.expiry_plan(at=start+timedelta(days=200))['requests'][0]['reason']=='policy_undecided'
    # Separate approved case: closing with a chosen period, no implicit 3-year default.
    case=registry.receive('erasure',user_id=uuid4(),owner_id=uuid4(),received_at=start)
    registry.finish(case,closed_at=start+timedelta(days=1),retention_days=10)
    at=start+timedelta(days=11)
    reasons={r['id']:r['reason'] for r in registry.expiry_plan(at=at)['requests']}
    assert reasons[case]=='restore_evidence_required'
    assert registry.expire(at=at,backup_safe_before=start)['eligible']==0
    assert registry.expire(at=at,backup_safe_before=at)['eligible']==1
    assert len(registry.expiry_plan(at=at)['requests'])==2
    with pytest.raises(ValueError,match='execution disabled'):
        registry.expire(at=at,backup_safe_before=at,execute=True)
    assert {r['id'] for r in registry.expiry_plan(at=at)['requests']}=={identifier,case}


def test_registry_retries_failures_no_free_text_and_monotonic_watermark(registry):
    identifier=registry.receive('access')
    registry.finish(identifier,failed=True)
    assert registry.expiry_plan()['requests'][0]['reason']=='not_closed'
    registry.finish(identifier,retention_days=1)
    with registry.connection() as db:
        expires=db.execute('SELECT expires_at FROM requests').fetchone()[0]
    registry.finish(identifier,retention_days=999)
    with registry.connection() as db:
        assert db.execute('SELECT expires_at FROM requests').fetchone()[0]==expires
    registry.observe_admissions(5)
    registry.observe_admissions(2)
    assert registry.restore_plan(1)['minimum_issued_count']==5
    assert registry.restore_plan(6)['minimum_issued_count']==6
    assert registry.restore_plan(0)['opening_authorized'] is False
    with pytest.raises(ValueError):registry.receive('email:private@example.test')
    with pytest.raises(ValueError):registry.observe_admissions(True)
    with pytest.raises(ValueError):registry.finish(identifier,retention_days=0)


def test_registry_missing_or_unsafe_never_created_implicitly(tmp_path):
    path=tmp_path/'missing.sqlite'
    with pytest.raises((FileNotFoundError,ValueError)):Registry(path).receive('access')
    assert not path.exists()
    if os.name=='posix':
        directory=tmp_path/'public';directory.mkdir(mode=0o755)
        directory.chmod(0o755)  # Establish the unsafe fixture regardless of runner umask.
        with pytest.raises(ValueError):Registry(directory/'ledger').initialize()


def test_receipt_survives_account_purge_and_plans_restore(beta, registry):
    client,app,_=beta
    app.state.settings.lifecycle_registry_path=registry.path
    verify_and_login(beta)
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD}).status_code==202
    with app.state.sessions() as session:
        user=session.scalar(select(User))
        identifier=str(user.id)
        purge_account(session,app.state.settings,user.id)
        assert session.scalar(select(User)) is None
        assert session.get(PublicRegistrationQuota,'public').issued_count==1
    plan=registry.restore_plan(0)
    assert plan['minimum_issued_count']==1
    assert plan['erasure_requests'][0]['user_id']==identifier
    with registry.connection() as db:
        assert db.execute('SELECT state FROM requests').fetchone()[0]=='active_erased'
    assert 'alice@example.test' not in registry.path.read_bytes().decode('latin1')


def test_missing_configured_registry_blocks_deletion_before_account_mutation(beta,tmp_path):
    client,app,_=beta
    verify_and_login(beta)
    app.state.settings.lifecycle_registry_path=tmp_path/'not-provisioned.sqlite'
    response=client.post('/api/v1/account/deletion-request',json={'password':PASSWORD})
    assert response.status_code==503
    assert 'not-provisioned' not in response.text
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None


def test_pending_plan_shared_predicate_no_mutation_and_readonly_runner(beta):
    from tools.pending_lifecycle import run
    client,app,_=beta
    enroll(beta)
    with app.state.sessions() as session:
        user=session.scalar(select(User));user.created_at=now()-timedelta(days=8)
        session.commit()
        assert plan_pending_cleanup(session,168)['counts']=={'valid_verification_link':1}
        session.scalar(select(AccountToken)).expires_at=now()-timedelta(seconds=1);session.commit()
        assert plan_pending_cleanup(session,168)['counts']=={'eligible':1}
        assert purge_pending(session,app.state.settings)==1
        assert session.scalar(select(User)).disabled_at is None
        assert session.get(PublicRegistrationQuota,'public').issued_count==1
    assert run(app.state.settings,168)['counts']=={'eligible':1}
    with pytest.raises(ValueError):run(app.state.settings,24)


def test_historical_archive_diagnostic_preserves_all_copies(inventory):
    root,repo,rows,days=inventory
    row,files=days[12]
    manifest=json.loads(files['manifest.json']);manifest['migration']='0005'
    files['manifest.json']=json.dumps(manifest).encode()
    directory=root/'var/backups'/row['tags'][1]
    (directory/'manifest.json').write_bytes(files['manifest.json'])
    before={p:p.read_bytes() for p in (root/'var/backups').rglob('*') if p.is_file()}
    plan=retention.build_plan(root,repo,'0006',NOW)
    excluded=next(r for r in plan['local']['excluded'] if r.get('ref')==row['tags'][1])
    assert excluded['reason']=='archive_metadata_inconsistent'
    assert excluded['checks']==['historical_schema_review_required']
    assert not plan['local']['would_remove'] and not plan['remote']['would_remove']
    assert before=={p:p.read_bytes() for p in before}


def test_metadata_diagnostics_are_sanitized():
    codes=retention.metadata_diagnostics({'migration':'private secret','created_at':'bad'}, {},'0007',NOW,NOW)
    assert 'schema_invalid_or_unknown' in codes
    assert 'private secret' not in json.dumps(codes)


def test_reconciliation_requires_offline_unchanged_approval(app):
    app.state.settings.storage_dir.mkdir()
    path=app.state.settings.storage_dir/('a'*32+'.part')
    path.write_bytes(b'fake')
    seal=reconciliation_plan(app.state.settings)['plan_sha256']
    with pytest.raises(ValueError):reconcile(app.state.settings,True)
    path.write_bytes(b'changed')
    with pytest.raises(ValueError):reconcile(app.state.settings,True,offline_confirmed=True,approved_plan_sha256=seal)
    assert path.exists()
    fresh=reconciliation_plan(app.state.settings)['plan_sha256']
    reconcile(app.state.settings,True,offline_confirmed=True,approved_plan_sha256=fresh)
    assert not path.exists()


def test_reconciliation_refuses_hardlinks_before_any_deletion(app,tmp_path):
    app.state.settings.storage_dir.mkdir()
    outside=tmp_path/'original';outside.write_bytes(b'protected')
    target=app.state.settings.storage_dir/('b'*32+'.part')
    os.link(outside,target)
    with pytest.raises(ValueError):reconciliation_plan(app.state.settings)
    assert outside.read_bytes()==target.read_bytes()==b'protected'


def test_scheduler_and_alert_are_explicitly_non_destructive(monkeypatch):
    from tools import lifecycle_alert
    events=[]
    monkeypatch.setattr(lifecycle_alert,'send',events.append)
    assert lifecycle_alert.main()==0
    assert events[0]['event']=='lifecycle-inventory-failed'
    service=Path('ops/systemd/documind-pending-inventory.service.example').read_text()
    assert '--simulate' in service and '--execute' not in service
    assert 'OnFailure=documind-lifecycle-alert.service' in service
    monkeypatch.setattr(lifecycle_alert,'send',lambda event:(_ for _ in ()).throw(RuntimeError('secret')))
    assert lifecycle_alert.main()==1


def test_document_receipt_survives_sql_delete_and_residual_requires_reconciliation(client,app,registry,monkeypatch):
    from backend.models import Document
    from backend.services import documents
    app.state.settings.lifecycle_registry_path=registry.path
    created=client.post('/api/v1/documents',files={'file':('fake.txt',b'Fictitious document.','text/plain')})
    assert created.status_code==201
    identifier=created.json()['id']
    with app.state.sessions() as session:
        document=session.scalar(select(Document))
        source=app.state.settings.storage_dir/document.storage_name
        owner=document.owner_id
    with monkeypatch.context() as patch:
        patch.setattr(documents,'cleanup_file',lambda path:False)
        assert client.delete('/api/v1/documents/'+identifier).status_code==204
    assert source.exists()
    assert registry.pending_document_files(owner)==[source.name]
    with pytest.raises(ValueError):registry.confirm_document_absent(identifier,app.state.settings)
    seal=reconciliation_plan(app.state.settings)['plan_sha256']
    reconcile(app.state.settings,True,offline_confirmed=True,approved_plan_sha256=seal)
    registry.confirm_document_absent(identifier,app.state.settings)
    assert not registry.pending_document_files(owner)
    assert registry.restore_plan(0)['document_erasures'][0]['document_id']==identifier
    # No expiry before an explicit period AND a verified backup boundary.
    future=now()+timedelta(days=31)
    assert registry.expire_documents(retention_days=30,at=future,backup_safe_before=now()-timedelta(days=1))['eligible']==0
    assert registry.expire_documents(retention_days=30,at=future,backup_safe_before=future)['eligible']==1
    with pytest.raises(ValueError):registry.expire_documents(retention_days=30,at=future,backup_safe_before=future,execute=True)
    with registry.connection() as db:
        # Artificial old receipt: never advance the real deletion clock.
        old=(now()-timedelta(days=31)).isoformat()
        db.execute('UPDATE document_erasures SET requested_at=?,completed_at=?',(old,old))
    checkpoint=now()
    with pytest.raises(ValueError,match='execution disabled'):
        registry.expire_documents(retention_days=30,at=checkpoint,backup_safe_before=checkpoint,execute=True)
    assert len(registry.restore_plan(0)['document_erasures'])==1


def test_purge_failure_preserves_receipt_and_disabled_account(beta,registry,monkeypatch):
    import backend.account_admin as admin
    client,app,_=beta
    app.state.settings.lifecycle_registry_path=registry.path
    verify_and_login(beta)
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD}).status_code==202
    monkeypatch.setattr(admin,'_purge_account',lambda *args:(_ for _ in ()).throw(RuntimeError('sensitive failure')))
    with app.state.sessions() as session:
        user=session.scalar(select(User))
        with pytest.raises(RuntimeError):admin.purge_account(session,app.state.settings,user.id)
        assert session.get(User,user.id).disabled_at is not None
        assert session.get(PublicRegistrationQuota,'public').issued_count==1
    with registry.connection() as db:
        row=db.execute('SELECT state,failure_code FROM requests').fetchone()
        assert tuple(row)==('failed','processing_failed')
    assert 'sensitive failure' not in registry.path.read_bytes().decode('latin1')


def test_real_account_purge_stops_on_file_residual_then_resumes(beta,registry,monkeypatch):
    from backend.models import Document
    from backend.services import documents
    client,app,_=beta
    app.state.settings.lifecycle_registry_path=registry.path
    verify_and_login(beta)
    assert client.post('/api/v1/documents',files={'file':('fake.txt',b'Synthetic private source.','text/plain')}).status_code==201
    with app.state.sessions() as session:
        document=session.scalar(select(Document));document_id=document.id
    assert client.post('/api/v1/account/deletion-request',json={'password':PASSWORD}).status_code==202
    with monkeypatch.context() as patch:
        patch.setattr(documents,'cleanup_file',lambda path:False)
        with app.state.sessions() as session:
            user=session.scalar(select(User));identifier=user.id
            with pytest.raises(ValueError,match='residual reconciliation'):purge_account(session,app.state.settings,identifier)
            assert session.get(User,identifier).disabled_at is not None
    seal=reconciliation_plan(app.state.settings)['plan_sha256']
    reconcile(app.state.settings,True,offline_confirmed=True,approved_plan_sha256=seal)
    registry.confirm_document_absent(document_id,app.state.settings)
    with app.state.sessions() as session:
        purge_account(session,app.state.settings,identifier)
        assert session.get(User,identifier) is None
        assert session.get(PublicRegistrationQuota,'public').issued_count==1
    with registry.connection() as db:
        assert db.execute('SELECT state FROM requests').fetchone()[0]=='active_erased'


def test_pending_plan_explains_disabled_verified_and_young_exceptions(beta):
    client,app,_=beta
    enroll(beta)
    with app.state.sessions() as session:
        user=session.scalar(select(User))
        assert plan_pending_cleanup(session,168)['counts']=={'too_recent':1}
        user.disabled_at=now();session.commit()
        assert plan_pending_cleanup(session,168)['counts']=={'disabled':1}
        user.email_verified_at=now();session.commit()
        assert plan_pending_cleanup(session,168)['counts']=={'verified':1}


def test_calendar_log_policy_has_no_implicit_duration_or_global_install():
    from tools.lifecycle_logs import journald_policy
    policy=journald_policy(31,256)
    assert 'MaxRetentionSec=31day' in policy and 'MaxFileSec=1day' in policy
    assert 'journald@documind-lifecycle' in policy
    for days in (0,True,3651):
        with pytest.raises(ValueError):journald_policy(days,256)


def test_registry_cli_defaults_and_failure_output_are_private(registry,monkeypatch,capsys,tmp_path):
    from tools import lifecycle_admin, pending_lifecycle
    lock=registry.path.parent/'.backup.lock'
    monkeypatch.setenv('LIFECYCLE_BACKUP_LOCK_PATH',str(lock))
    monkeypatch.setattr('sys.argv',['lifecycle_admin','--registry',str(registry.path),'receive','access'])
    assert lifecycle_admin.main()==0
    identifier=json.loads(capsys.readouterr().out)['id']
    monkeypatch.setattr('sys.argv',['lifecycle_admin','--registry',str(registry.path),'close',identifier,'--retention-days','30'])
    assert lifecycle_admin.main()==0
    capsys.readouterr()
    monkeypatch.setattr('sys.argv',['lifecycle_admin','--registry',str(registry.path),'expiry-plan'])
    assert lifecycle_admin.main()==0
    assert json.loads(capsys.readouterr().out)['simulation'] is True
    monkeypatch.setattr('sys.argv',['lifecycle_admin','--registry',str(tmp_path/'private-missing'),'restore-plan','--restored-count','1'])
    assert lifecycle_admin.main()==1
    assert 'private-missing' not in capsys.readouterr().out
    monkeypatch.setattr('sys.argv',['pending_lifecycle','--simulate','--older-than-hours','168'])
    monkeypatch.setattr(pending_lifecycle,'run',lambda *args:(_ for _ in ()).throw(RuntimeError('private database connection')))
    assert pending_lifecycle.main()==1
    assert 'private database connection' not in capsys.readouterr().out


def test_registry_timezone_policy_assignment_and_no_future_backup_boundary(registry):
    start=datetime(2026,1,1,tzinfo=timezone.utc)
    case=registry.receive('restriction',received_at=start)
    with pytest.raises(ValueError):registry.finish(case,closed_at=start-timedelta(seconds=1))
    with pytest.raises(ValueError):registry.expiry_plan(at=datetime(2026,1,1))
    registry.finish(case,closed_at=start)
    registry.finish(case,retention_days=2)
    assert registry.expiry_plan(at=start+timedelta(days=2))['requests'][0]['reason']=='eligible'
    with pytest.raises(ValueError):registry.expire(at=start,backup_safe_before=start+timedelta(days=1),execute=True)
    assert len(registry.expiry_plan()['requests'])==1


@pytest.mark.skipif(os.name=='nt',reason='Symlink creation requires Windows privileges; Linux deployment proof')
@pytest.mark.posix
def test_symlinked_registry_and_document_storage_refused(tmp_path,app):
    actual=tmp_path/'private-ledger';actual.mkdir(mode=0o700)
    alias=tmp_path/'alias';alias.symlink_to(actual,target_is_directory=True)
    with pytest.raises(ValueError):Registry(alias/'ledger').initialize()
    app.state.settings.storage_dir.symlink_to(actual,target_is_directory=True)
    with pytest.raises(ValueError):reconciliation_plan(app.state.settings)
