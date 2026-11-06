"""Root controller / irrevocably non-root API, isolated PostgreSQL and storage only."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend import erasure
from backend.account_models import PublicRegistrationQuota, Workspace, WorkspaceMembership
from backend.auth import User, hash_password
from backend.config import Settings
from backend.db import make_engine, make_sessions
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import ConfirmationStore
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry
from backend.models import Document, DocumentPage, Analysis, now
from tests.conftest import BFF_KEY

pytestmark = pytest.mark.skipif(
    os.name != 'posix' or getattr(os, 'geteuid', lambda: -1)() != 0
    or not os.environ.get('TEST_ERASURE_POSTGRES_DSN'),
    reason='Requires explicit isolated PostgreSQL and native root/non-root separation')

APP_UID = 65534
PASSWORD = 'Fictitious-erasure-test-password-2026!'


@contextmanager
def database(settings):
    engine = make_engine(settings.database_url)
    try:
        with make_sessions(engine)() as session:
            yield session
    finally:
        engine.dispose()


@pytest.fixture
def lab(tmp_path, monkeypatch):
    import psycopg
    from psycopg import sql
    from psycopg.conninfo import conninfo_to_dict
    from sqlalchemy.engine import URL
    from alembic import command
    from alembic.config import Config
    dsn = os.environ['TEST_ERASURE_POSTGRES_DSN']
    conn = conninfo_to_dict(dsn)
    assert (conn.get('host'), conn.get('port'), conn.get('user'), conn.get('dbname')) == (
        '127.0.0.1', '5432', 'erasure_test', 'postgres'), 'Dedicated disposable endpoint required'
    name = 'erasure_case_' + uuid4().hex
    with psycopg.connect(dsn, autocommit=True) as db:
        db.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    url = URL.create('postgresql+psycopg', username=conn['user'], password=conn['password'],
                     host='127.0.0.1', port=5432, database=name).render_as_string(hide_password=False)
    try:
        monkeypatch.setenv('DATABASE_URL', url)
        command.upgrade(Config('alembic.ini'), 'head')
        tmp_path.chmod(0o755)
        tmp_path.parent.chmod(0o755)
        paths = {}
        for key in ('control', 'requests', 'storage', 'registry', 'confirmation', 'authenticated',
                    'keys', 'holds', 'lock'):
            path = tmp_path / key
            path.mkdir(mode=0o755 if key == 'control' else 0o700)
            if key != 'control':
                os.chown(path, APP_UID, APP_UID)
            paths[key] = path
        latch = tmp_path / 'recovery.json'
        latch.write_text('{"format":1,"state":"quarantined"}')
        latch.chmod(0o644)
        settings = Settings(_env_file=None, database_url=url, bff_service_key=BFF_KEY,
            api_keys={}, legacy_api_enabled=False, owner_demo_enabled=False, ai_enabled=False,
            registration_mode='disabled', public_registration_limit=10, extraction_mode='development',
            public_registration_use_lifecycle_receipts=False,
            storage_dir=paths['storage'], recovery_state_path=latch,
            erasure_authority_dir=paths['control'], erasure_requests_dir=paths['requests'],
            erasure_instance_id=uuid4(), erasure_application_uid=APP_UID,
            lifecycle_registry_path=paths['registry'] / 'ledger.sqlite',
            lifecycle_confirmation_path=paths['confirmation'] / 'ledger.sqlite',
            lifecycle_authenticated_confirmation_path=paths['authenticated'] / 'ledger.sqlite',
            lifecycle_authentication_key_path=paths['keys'] / 'authentication.key',
            lifecycle_holds_path=paths['holds'] / 'ledger.sqlite')
        monkeypatch.setenv('LIFECYCLE_BACKUP_LOCK_PATH', str(paths['lock'] / 'backup.lock'))
        with erasure.application_identity(settings):
            settings.lifecycle_authentication_key_path.write_bytes(os.urandom(32))
            settings.lifecycle_authentication_key_path.chmod(0o600)
            Registry(settings.lifecycle_registry_path).initialize()
            ConfirmationStore(settings.lifecycle_confirmation_path).initialize()
            auth = AuthenticatedConfirmationStore(settings.lifecycle_authenticated_confirmation_path,
                    settings.lifecycle_authentication_key_path.read_bytes(), 'documind-local-v2')
            auth.initialize()
            HoldStore(settings.lifecycle_holds_path, auth).initialize()
        erasure.Authority(settings).initialize()
        user_id, owner, doc_id = uuid4(), uuid4(), uuid4()
        content = b'Fictitious private document, never production.'
        stored = uuid4().hex + '.txt'
        source = settings.storage_dir / stored
        source.write_bytes(content)
        os.chown(source, APP_UID, APP_UID)
        source.chmod(0o600)
        with database(settings) as session:
            session.add(User(id=user_id, owner_id=owner, username='erasure-user',
                email='erasure@example.test', password_hash=hash_password(PASSWORD),
                registration_kind='public', email_verified_at=now(), approved_at=now()))
            session.add(Workspace(owner_id=owner))
            session.flush()
            session.add(WorkspaceMembership(user_id=user_id, owner_id=owner))
            session.add(Document(id=doc_id, owner_id=owner, filename='fictitious.txt',
                storage_name=stored, media_type='text/plain', size_bytes=len(content),
                sha256=hashlib.sha256(content).hexdigest()))
            session.flush()
            session.add(DocumentPage(document_id=doc_id, page_number=1, text=content.decode()))
            session.add(Analysis(document_id=doc_id, parameters={}, result={'fictitious': 'private'}))
            session.get(PublicRegistrationQuota, 'public').issued_count = 3
            session.commit()
        policy = tmp_path / 'approved-test-policy.json'
        policy.write_bytes(erasure.canonical({'version': 1, 'policy_id': str(uuid4()),
            'approved_by': str(uuid4()), 'approved_at': erasure.timestamp(), 'owner_accounting': 'erase',
            'backup_retention_days': 30, 'log_retention_days': 7,
            'receipt_retention': 'until_restore_sources_expire'}))
        policy.chmod(0o600)
        evidence = tmp_path / 'private-identity-review'
        evidence.write_bytes(b'Fictitious independent identity review for this isolated test only.')
        evidence.chmod(0o600)
        yield SimpleNamespace(settings=settings, user=user_id, owner=owner, document=doc_id,
                              source=source, policy=policy, evidence=evidence, paths=paths)
    finally:
        with psycopg.connect(dsn, autocommit=True) as db:
            db.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


ACTOR = r'''
import json, os, sys
value = json.load(sys.stdin)
os.setgroups([])
os.setgid(65534)
os.setuid(65534)
assert os.getresuid() == (65534, 65534, 65534)
try:
    os.seteuid(0)
    raise AssertionError('API regained root')
except PermissionError:
    pass
from backend.config import Settings
from backend.main import create_app
from fastapi.testclient import TestClient
value['settings']['bff_service_key'] = value['key']
s = Settings(_env_file=None, **value['settings'])
app = create_app(s)
if value.get('no_recovery'):
    def forbidden(*args, **kwargs):
        raise AssertionError('Recovery must not run before tombstone validation')
    import backend.rag.indexing
    import backend.ai.long_summary
    backend.rag.indexing.recover_jobs = forbidden
    backend.ai.long_summary.recover = forbidden
with TestClient(app) as client:
    client.headers.update({'X-API-Key': value['key'], 'X-Documind-Secure': '1'})
    if value['action'] in ('health', 'live-replay'):
        response = client.get('/api/v1/health')
        if value['action'] == 'live-replay':
            assert response.status_code == 200
            path = s.storage_dir / value['source_name']
            path.write_bytes(b'Fictitious data reintroduced while API is already running.')
            path.chmod(0o600)
            response = client.get('/api/v1/health')
    else:
        login = client.post('/api/v1/auth/login', json={'email':'erasure@example.test','password':value['password']})
        if login.status_code != 200:
            response = login
        else:
            client.headers['Authorization'] = 'Bearer ' + login.json()['session_token']
            if value['action'] == 'account':
                response = client.post('/api/v1/account/deletion-request', json={'password':value.get('confirmation',value['password'])})
            else:
                response = client.delete('/api/v1/documents/' + value['document'])
    result = {'status':response.status_code, 'body':response.json(), 'uid':os.geteuid()}
print('ERASURE_TEST_RESULT:' + json.dumps(result))
'''


def api(lab, action='document', **extra):
    lab.settings.recovery_state_path.write_text('{"format":1,"state":"ready"}')
    payload = {'settings': lab.settings.model_dump(mode='json'), 'action': action,
               'document': str(lab.document), 'password': PASSWORD, 'key': BFF_KEY, **extra}
    result = subprocess.run([sys.executable, '-c', ACTOR], input=json.dumps(payload),
                            text=True, capture_output=True, timeout=30)
    assert result.returncode == 0, result.stderr
    lines = [line for line in result.stdout.splitlines() if line.startswith('ERASURE_TEST_RESULT:')]
    assert len(lines) == 1, result.stdout
    return json.loads(lines[0].split(':', 1)[1])


def maintenance(lab):
    lab.settings.recovery_state_path.write_text('{"format":1,"state":"quarantined"}')


def prepare(lab, kind='document'):
    response = api(lab, kind)
    assert response['status'] == 202, response
    operation = response['body']['operation_id']
    maintenance(lab)
    erasure.plan(lab.settings, operation)
    erasure.authorize(lab.settings, operation, operation, lab.policy, lab.evidence)
    return operation


def independent_verify(lab, operation, *, success=True):
    env = dict(os.environ)
    for key, value in lab.settings.model_dump(mode='json').items():
        if value is not None:
            env[key.upper()] = json.dumps(value) if isinstance(value, (dict, list, bool)) else str(value)
    env['BFF_SERVICE_KEY'] = BFF_KEY
    result = subprocess.run([sys.executable, '-m', 'backend.erasure_admin', 'verify', operation],
                            env=env, text=True, capture_output=True, timeout=20)
    assert (result.returncode == 0) is success, result.stdout + result.stderr
    return json.loads(result.stdout.splitlines()[-1])


@pytest.mark.parametrize('kind', ['document', 'account'])
def test_authorized_physical_erasure_requires_separate_verification(lab, kind):
    operation = prepare(lab, kind)
    result = erasure.execute(lab.settings, operation, operation)
    assert result['state'] == 'verification_pending'
    assert not result['active_erasure_verified'] and not result['completed']
    assert not lab.source.exists()
    with database(lab.settings) as session:
        assert session.get(Document, lab.document) is None
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 3
        assert (session.get(User, lab.user) is None) is (kind == 'account')
        assert not session.scalars(select(DocumentPage)).all()
        assert not session.scalars(select(Analysis)).all()
    verified = independent_verify(lab, operation)
    assert verified['active_erasure_verified'] and not verified['completed']
    assert verified['backups'] == verified['logs'] == 'retention_pending'
    assert api(lab, 'health')['status'] == 200


@pytest.mark.parametrize('kind', ['document', 'account'])
def test_repeated_requests_and_execution_never_recycle_admissions(lab, kind):
    first, second = api(lab, kind), api(lab, kind)
    assert first['body'] == second['body'] and first['body']['completed'] is False
    assert len(list(lab.settings.erasure_requests_dir.glob('*.json'))) == 2  # header + request
    maintenance(lab)
    op = first['body']['operation_id']
    erasure.plan(lab.settings, op)
    erasure.authorize(lab.settings, op, op, lab.policy, lab.evidence)
    erasure.execute(lab.settings, op, op)
    erasure.execute(lab.settings, op, op)
    independent_verify(lab, op)
    with pytest.raises(erasure.ErasureError, match='never replay'):
        erasure.execute(lab.settings, op, op)


def test_wrong_password_foreign_scope_and_api_cannot_authorize(lab):
    assert api(lab, 'account', confirmation='wrong-password')['status'] == 401
    assert api(lab, document=str(uuid4()))['status'] == 503
    assert len(list(lab.settings.erasure_requests_dir.glob('*.json'))) == 1
    op = api(lab)['body']['operation_id']
    maintenance(lab)
    erasure.plan(lab.settings, op)
    with erasure.application_identity(lab.settings):
        with pytest.raises(erasure.ErasureError, match='root authority'):
            erasure.authorize(lab.settings, op, op, lab.policy, lab.evidence)
        with pytest.raises(PermissionError):
            (lab.settings.erasure_authority_dir / 'forged.json').write_text('{}')
    with pytest.raises(erasure.ErasureError, match='authorization'):
        erasure.execute(lab.settings, op, op)
    with pytest.raises(erasure.ErasureError, match='confirmation'):
        erasure.authorize(lab.settings, op, str(uuid4()), lab.policy, lab.evidence)
    assert lab.source.exists()


def test_disabled_account_requires_administrative_intake_and_identity_review(lab):
    with database(lab.settings) as session:
        session.get(User, lab.user).disabled_at = now()
        session.commit()
    assert api(lab, 'account')['status'] == 401
    maintenance(lab)
    with database(lab.settings) as session:
        user = session.get(User, lab.user)
        op = erasure.submit(session, lab.settings, user, administrative=True)['operation_id']
    erasure.plan(lab.settings, op)
    erasure.authorize(lab.settings, op, op, lab.policy, lab.evidence)
    erasure.execute(lab.settings, op, op)
    assert independent_verify(lab, op)['active_erasure_verified']


@pytest.mark.parametrize('stage', ['before_sql_commit', 'after_sql_commit', 'after_unlink'])
def test_interruptions_remain_failed_until_independent_physical_verification(lab, monkeypatch, stage):
    op = prepare(lab)
    if stage == 'before_sql_commit':
        original = erasure.remove_rows
        def interrupted(session, operation):
            original(session, operation)
            raise RuntimeError('Fictitious interruption before COMMIT')
        with monkeypatch.context() as patch:
            patch.setattr(erasure, 'remove_rows', interrupted)
            with pytest.raises(RuntimeError):
                erasure.execute(lab.settings, op, op)
        assert lab.source.exists()
        with database(lab.settings) as session:
            assert session.get(Document, lab.document) is not None
    else:
        original = Path.unlink
        def interrupted(path, *args, **kwargs):
            if path == lab.source:
                if stage == 'after_unlink':
                    original(path, *args, **kwargs)
                raise OSError('Fictitious interrupted file cleanup')
            return original(path, *args, **kwargs)
        with monkeypatch.context() as patch:
            patch.setattr(Path, 'unlink', interrupted)
            with pytest.raises(OSError):
                erasure.execute(lab.settings, op, op)
        with database(lab.settings) as session:
            assert session.get(Document, lab.document) is None
    state = erasure.Authority(lab.settings).operation(op)
    assert state['phase'] == 'failed' and not erasure.summary(state)['completed']
    if stage != 'after_unlink':
        independent_verify(lab, op, success=False)
    assert api(lab, 'health', no_recovery=True)['status'] == 503
    maintenance(lab)
    erasure.execute(lab.settings, op, op)
    assert independent_verify(lab, op)['active_erasure_verified']


@pytest.mark.parametrize('restored', ['file', 'sql', 'counter'])
def test_restored_data_never_reappears_after_resume(lab, restored):
    content = lab.source.read_bytes()
    with database(lab.settings) as session:
        doc = session.get(Document, lab.document)
        values = {column.name: getattr(doc, column.name) for column in Document.__table__.columns}
    op = prepare(lab)
    erasure.execute(lab.settings, op, op)
    independent_verify(lab, op)
    assert api(lab, 'health')['status'] == 200
    if restored == 'file':
        lab.source.write_bytes(content)
        os.chown(lab.source, APP_UID, APP_UID)
        lab.source.chmod(0o600)
    else:
        with database(lab.settings) as session:
            if restored == 'sql':
                session.add(Document(**values))
            else:
                session.get(PublicRegistrationQuota, 'public').issued_count = 2
            session.commit()
    assert api(lab, 'health', no_recovery=True)['status'] == 503
    maintenance(lab)
    result = independent_verify(lab, op, success=False)
    assert result['completed'] is False


def test_missing_policy_changed_source_or_live_database_client_refuses_effects(lab):
    op = api(lab)['body']['operation_id']
    maintenance(lab)
    with database(lab.settings) as session:
        session.execute(select(User.id)).all()
        with pytest.raises(erasure.ErasureError, match='database clients'):
            erasure.plan(lab.settings, op)
    erasure.plan(lab.settings, op)
    with pytest.raises(FileNotFoundError):
        erasure.authorize(lab.settings, op, op, lab.policy.with_name('absent-policy'), lab.evidence)
    lab.source.write_bytes(b'Changed outside the authorized scope.')
    with pytest.raises(erasure.ErasureError, match='source changed'):
        erasure.authorize(lab.settings, op, op, lab.policy, lab.evidence)
    assert erasure.Authority(lab.settings).operation(op)['phase'] == 'planned'


def test_active_hold_blocks_authorization_without_lifting_existing_controls(lab):
    op = api(lab)['body']['operation_id']
    maintenance(lab)
    erasure.plan(lab.settings, op)
    from datetime import timedelta
    from backend.lifecycle_holds import ActiveHoldError
    at = now()
    with erasure.application_identity(lab.settings):
        auth = AuthenticatedConfirmationStore(lab.settings.lifecycle_authenticated_confirmation_path,
            lab.settings.lifecycle_authentication_key_path.read_bytes(), 'documind-local-v2')
        hold = {'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(lab.document),
                'scope_kind': 'document', 'reason': 'legal_hold', 'reviewed_at': at,
                'review_at': at + timedelta(days=1), 'ends_at': None, 'end_event': 'legal_hold_lifted'}
        HoldStore(lab.settings.lifecycle_holds_path, auth).create(hold, at)
    with pytest.raises(ActiveHoldError):
        erasure.authorize(lab.settings, op, op, lab.policy, lab.evidence)
    assert lab.source.exists()


@pytest.mark.parametrize('kind', ['document', 'account'])
def test_unknown_commit_acknowledgment_leaves_files_and_recovers(lab, monkeypatch, kind):
    from sqlalchemy.orm import Session
    op = prepare(lab, kind)
    original = Session.commit
    def lost_ack(session):
        original(session)
        raise ConnectionError('Fictitious COMMIT response loss')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lost_ack)
        with pytest.raises(ConnectionError):
            erasure.execute(lab.settings, op, op)
    assert lab.source.exists()
    assert erasure.Authority(lab.settings).operation(op)['phase'] == 'failed'
    with database(lab.settings) as session:
        assert session.get(Document, lab.document) is None
    erasure.execute(lab.settings, op, op)
    assert independent_verify(lab, op)['active_erasure_verified']


@pytest.mark.parametrize('stage', ['before_commit', 'after_commit', 'after_unlink'])
def test_actual_sigkill_recovers_from_persistent_checkpoint(lab, stage):
    op = prepare(lab, 'account')
    code = r'''
import json, os, signal, sys
from pathlib import Path
from sqlalchemy.orm import Session
from backend import erasure
from backend.config import Settings
value = json.load(sys.stdin)
settings = Settings(_env_file=None, **value['settings'])
def kill():
    os.kill(os.getpid(), signal.SIGKILL)
if value['stage'] == 'before_commit':
    original = erasure.remove_rows
    def interrupted(session, operation):
        original(session, operation)
        kill()
    erasure.remove_rows = interrupted
elif value['stage'] == 'after_commit':
    original = Session.commit
    def interrupted(session):
        original(session)
        kill()
    Session.commit = interrupted
else:
    original = Path.unlink
    def interrupted(path, *args, **kwargs):
        original(path, *args, **kwargs)
        if str(path) == value['source']:
            kill()
    Path.unlink = interrupted
erasure.execute(settings, value['operation'], value['operation'])
'''
    settings = lab.settings.model_dump(mode='json')
    settings['bff_service_key'] = BFF_KEY
    result = subprocess.run([sys.executable, '-c', code], text=True, capture_output=True, timeout=30,
        input=json.dumps({'settings': settings, 'stage': stage, 'operation': op, 'source': str(lab.source)}))
    assert result.returncode == -9, result.stderr
    operation = erasure.Authority(lab.settings).operation(op)
    assert operation['phase'] in ('executing', 'files_pending')
    assert not erasure.summary(operation)['active_erasure_verified']
    assert api(lab, 'health')['status'] == 503
    maintenance(lab)
    erasure.execute(lab.settings, op, op)
    assert independent_verify(lab, op)['active_erasure_verified']


@pytest.mark.parametrize('kind', ['document', 'account'])
def test_all_registered_derived_dependencies_are_removed_without_losing_other_accounts(lab, kind):
    from backend.ai.models import AIReservation, AIUsage, AISummary, AIInteraction, AISource
    from backend.ai.long_models import LongSummaryJob, SummaryStep
    from backend.rag.models import ChunkEmbedding, IndexJob, RAGDocument, RAGResult, OperationDocument
    from backend.models import DocumentChunk
    from backend.account_models import AccountToken
    from datetime import timedelta
    reservation, job, result, chunk, token, other_user, other_owner = [uuid4() for _ in range(7)]
    with database(lab.settings) as session:
        page = session.scalar(select(DocumentPage).where(DocumentPage.document_id == lab.document))
        session.add(DocumentChunk(id=chunk, document_id=lab.document, page_id=page.id,
            chunk_index=0, start_char=0, end_char=10, text='Fictitious derived private text'))
        session.add(AIReservation(id=reservation, owner_id=lab.owner, budget_id='development',
            document_id=lab.document, idempotency_key=uuid4(), request_hash='0'*64,
            feature='summary', status='completed', reserved_usd=0, model='mock', provider='mock'))
        session.add(AccountToken(id=token, digest=uuid4().hex*2, kind='reset',
            email='erasure@example.test', expires_at=now()+timedelta(hours=1)))
        session.add(User(id=other_user, owner_id=other_owner, username='untouched',
            email='untouched@example.test', password_hash=hash_password(PASSWORD), registration_kind='legacy'))
        session.flush()
        common = dict(document_id=lab.document, owner_id=lab.owner, reservation_id=reservation)
        session.add(AISummary(**common, content={'private':'fictitious'}, coverage='complete'))
        session.add(AIInteraction(**common, question='Fictitious question',
            content={'private':'fictitious'}, coverage='complete'))
        session.add(AISource(document_id=lab.document, chunk_id=chunk, reservation_id=reservation))
        session.add(AIUsage(owner_id=lab.owner, document_id=None, reservation_id=reservation,
            feature='summary', model='mock', provider='mock', input_tokens=1, output_tokens=1,
            reasoning_tokens=0, estimated_usd=0, input_rate=0, output_rate=0))
        session.add(LongSummaryJob(id=job, **common, status='completed', plan={}, configuration={}))
        session.add(RAGResult(id=result, owner_id=lab.owner, reservation_id=reservation,
            kind='question', request_hash='1'*64, content={'private':'fictitious'}))
        session.add(ChunkEmbedding(chunk_id=chunk, document_id=lab.document, owner_id=lab.owner,
            vector=[0.1]*8, model='mock', dimensions=8, version='test'))
        session.add(IndexJob(document_id=lab.document, owner_id=lab.owner, model='mock',
            dimensions=8, version='test', status='completed', total=1))
        session.add(OperationDocument(document_id=lab.document, reservation_id=reservation))
        session.flush()
        session.add(SummaryStep(job_id=job, node_id='test', status='completed',
            content={'private':'fictitious'}, chunk_ids=[str(chunk)], pages=[1]))
        session.add(RAGDocument(result_id=result, document_id=lab.document))
        session.commit()
    op = prepare(lab, kind)
    erasure.execute(lab.settings, op, op)
    assert independent_verify(lab, op)['active_erasure_verified']
    with database(lab.settings) as session:
        for model in (AIReservation, AIUsage, AISummary, AIInteraction, AISource, LongSummaryJob,
                      SummaryStep, RAGResult, RAGDocument, OperationDocument, ChunkEmbedding, IndexJob):
            assert not session.scalars(select(model)).all(), model.__tablename__
        assert session.get(User, other_user) is not None
        assert (session.get(AccountToken, token) is None) is (kind == 'account')
        assert (session.get(Workspace, lab.owner) is None) is (kind == 'account')


def test_restored_orphan_account_token_with_different_primary_key_blocks_restart(lab):
    from backend.account_models import AccountToken
    from datetime import timedelta
    op = prepare(lab, 'account')
    erasure.execute(lab.settings, op, op)
    independent_verify(lab, op)
    with database(lab.settings) as session:
        session.add(AccountToken(digest=uuid4().hex*2, kind='reset', email='erasure@example.test',
                                 expires_at=now()+timedelta(hours=1)))
        session.commit()
    assert api(lab, 'health')['status'] == 503


def test_unexecuted_authorization_is_not_verifiable_or_automatically_released(lab):
    op = prepare(lab)
    independent_verify(lab, op, success=False)
    assert lab.source.exists()
    assert erasure.Authority(lab.settings).operation(op)['phase'] == 'authorized'
    assert api(lab, 'health')['status'] == 503


def test_reintroduction_in_an_already_running_api_blocks_next_request(lab):
    op = prepare(lab)
    erasure.execute(lab.settings, op, op)
    independent_verify(lab, op)
    assert api(lab, 'live-replay', source_name=lab.source.name)['status'] == 503


def test_renamed_unattributed_copy_prevents_physical_verification(lab):
    content = lab.source.read_bytes()
    op = prepare(lab)
    erasure.execute(lab.settings, op, op)
    residual = lab.settings.storage_dir / (uuid4().hex+'.txt')
    residual.write_bytes(content)
    os.chown(residual, APP_UID, APP_UID)
    residual.chmod(0o600)
    independent_verify(lab, op, success=False)
    assert erasure.Authority(lab.settings).operation(op)['phase'] == 'failed'


@pytest.mark.parametrize('ddl', [
    'ALTER TABLE ai_budgets ADD COLUMN unknown_private_text text',
    'CREATE MATERIALIZED VIEW unknown_copy AS SELECT * FROM documents',
    'CREATE SCHEMA unknown_archive',
    '''CREATE FUNCTION unknown_copy() RETURNS trigger LANGUAGE plpgsql AS
       $$ BEGIN RETURN OLD; END $$;
       CREATE TRIGGER unknown_copy BEFORE DELETE ON documents FOR EACH ROW EXECUTE FUNCTION unknown_copy()''',
    '''ALTER TABLE document_pages DROP CONSTRAINT document_pages_document_id_fkey;
       ALTER TABLE document_pages ADD FOREIGN KEY (document_id) REFERENCES documents(id) ON DELETE SET NULL''',
])
def test_unknown_storage_schema_and_delete_effects_fail_closed(lab, ddl):
    from sqlalchemy import text
    op = api(lab)['body']['operation_id']
    maintenance(lab)
    with database(lab.settings) as session:
        session.execute(text(ddl))
        session.commit()
    with pytest.raises(erasure.ErasureError, match='Unknown database'):
        erasure.plan(lab.settings, op)
    assert lab.source.exists()
