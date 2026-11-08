"""Synthetic SQL/files and real signed authority; no production data."""
from dataclasses import replace
import hashlib
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.account_models import AccountToken, PublicRegistrationQuota
from backend.auth import User
from backend.lite_authority import (AuthorityError, canonical, digest, operation_payload,
                                     project, sign, export_proposal, OperationalConfirmation, LocalOperations)
from backend.lite_deletions import (apply, prepare_execution, cursor, prepare_request, export_deletion,
                                     validate_plan, verify_effect)
from backend.models import Document, DocumentPage, DocumentChunk, Analysis
from tests.test_lite_authority import domains, real_admissions, prepare_http, confirm_phase
from tests.test_lifecycle_durability import ledgers, enable
from tests.test_lite_admissions import send, PASSWORD, count


@pytest.fixture
def deletions(real_admissions, ledgers):
    client, app, d = real_admissions
    app.state.settings.lite_instance_id = UUID(d['instance'])
    enable(app, ledgers)
    app.state.settings.lifecycle_synthetic_mutations_enabled = False
    body, op = prepare_http(real_admissions)
    confirm_phase(real_admissions, op, 'reserve')
    assert send(client, body).status_code == 202
    confirm_phase(real_admissions, op, 'result')
    assert send(client, body).status_code == 201
    logged = client.post('/api/v1/auth/login', json={'email': body['email'], 'password': PASSWORD})
    assert logged.status_code == 200
    token = logged.json()['session_token']
    client.headers['Authorization'] = 'Bearer '+token
    raw = b'Synthetic personal text, never user data.'
    path = app.state.settings.storage_dir / (uuid4().hex+'.txt')
    path.write_bytes(raw); path.chmod(0o600)
    with app.state.sessions() as session:
        document = Document(owner_id=op.owner_id, filename='synthetic.txt', storage_name=path.name,
                            media_type='text/plain', size_bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
        session.add(document); session.flush()
        page = DocumentPage(document_id=document.id, page_number=1, text=raw.decode())
        session.add(page); session.flush()
        session.add(DocumentChunk(document_id=document.id, page_id=page.id, chunk_index=0,
                                  start_char=0, end_char=len(raw), text=raw.decode()))
        session.add(Analysis(document_id=document.id, parameters={}, result={'synthetic': True}))
        session.commit()
        document_id = document.id
    return client, app, d, op, document_id, path


def mutation(env, kind):
    return next(o for o in env[2]['store'].deletions() if o.kind == kind)


def confirm(env, op, phase):
    _, app, d, *_ = env
    with app.state.sessions() as session:
        session.info['deletion_settings'] = app.state.settings
        proposal = export_proposal(d['adapter'], op.operation_id, phase, session, d['export'])
    receipt = d['ledger'].approve(proposal, confirmation=op.operation_id, reference='synthetic-deletion-operator')
    d['install'](receipt)
    return receipt


def effect(env, op):
    _, app, d, *_ = env
    with app.state.sessions() as session:
        return apply(session, app.state.settings, d['adapter'], op.operation_id,
                     confirmation=op.operation_id, offline_confirmed=True)


def document_request(env):
    client, _, _, _, doc, _ = env
    result = client.delete(f'/api/v1/documents/{doc}')
    assert result.status_code == 202, result.text
    assert result.json()['state'] == 'awaiting_confirmation'
    return mutation(env, 'document_deletion_request')


def execution(env):
    op = document_request(env)
    confirm(env, op, 'authorize')
    effect(env, op); confirm(env, op, 'complete')
    with env[1].state.sessions() as session:
        return prepare_execution(session, env[1].state.settings, env[2]['adapter'],
                                 op.operation_id, 'document_deletion_execution')


def test_document_request_is_idempotent_and_restricts_all_access(deletions):
    client, app, d, _, doc, path = deletions
    first = document_request(deletions)
    again = client.delete(f'/api/v1/documents/{doc}')
    assert again.status_code == 202 and again.json()['operation_id'] == first.operation_id
    assert client.get(f'/api/v1/documents/{doc}').status_code == 200
    with pytest.raises(AuthorityError):
        effect(deletions, first)
    confirm(deletions, first, 'authorize')
    for suffix in ('', '/download', '/analysis'):
        assert client.get(f'/api/v1/documents/{doc}{suffix}').status_code == 410
    assert client.post(f'/api/v1/documents/{doc}/analyze', json={}).status_code == 410
    assert client.get('/api/v1/documents').json()['total'] == 0
    assert path.exists()
    effect(deletions, first); confirm(deletions, first, 'complete')
    assert client.get(f'/api/v1/documents/{doc}/deletion-status').json()['state'] == 'access_restricted'
    assert count(app) == 1
    # Changed proposal cannot reuse the authority's confirmation.
    changed = replace(first, plan={**first.plan, 'sql_sha256': '0'*64})
    with pytest.raises(AuthorityError):
        d['store'].save_deletion(changed)


def test_real_document_effect_and_surviving_receipt(deletions):
    client, app, d, _, doc, path = deletions
    op = execution(deletions)
    with pytest.raises(AuthorityError):
        effect(deletions, op)
    confirm(deletions, op, 'authorize')
    assert effect(deletions, op)['state'] == 'result_pending'
    assert not path.exists()
    with app.state.sessions() as session:
        for model in (Document, DocumentPage, DocumentChunk, Analysis):
            assert session.scalar(select(model.id).limit(1)) is None
    assert client.get(f'/api/v1/documents/{doc}/deletion-status').json()['completed'] is False
    confirm(deletions, op, 'complete')
    assert effect(deletions, op)['completed'] is True
    assert client.get(f'/api/v1/documents/{doc}/deletion-status').json()['state'] == 'completed'
    assert d['ledger'].recover()['events'][-1]['request']['operation'] == operation_payload(op)
    assert count(app) == 1


@pytest.mark.parametrize('point', ['before_sql', 'sql_rollback', 'lost_commit_ack', 'after_sql', 'unlink', 'after_unlink'])
def test_crashes_resume_without_false_completion(deletions, monkeypatch, point):
    from backend import lite_deletions as module
    client, app, d, _, doc, path = deletions
    op = execution(deletions); confirm(deletions, op, 'authorize')
    commit = Session.commit
    save = module.save_cursor
    unlink = Path.unlink
    def fault_commit(session):
        if point == 'sql_rollback':
            raise SQLAlchemyError('synthetic before commit')
        commit(session)
        raise SQLAlchemyError('synthetic lost acknowledgement')
    def fault_save(adapter, operation, value):
        if point == 'before_sql' and value['started']:
            raise OSError('synthetic crash before durable effect')
        if point == 'after_sql' and value['sql_erased']:
            raise OSError('synthetic crash after SQL')
        if point == 'after_unlink' and value['effect_verified']:
            raise OSError('synthetic crash before result')
        return save(adapter, operation, value)
    def fault_unlink(self, *args, **kwargs):
        if self == path:
            raise PermissionError('synthetic unlink denied')
        return unlink(self, *args, **kwargs)
    with monkeypatch.context() as patch:
        if point in ('sql_rollback', 'lost_commit_ack'):
            patch.setattr(Session, 'commit', fault_commit)
        elif point == 'unlink':
            patch.setattr(Path, 'unlink', fault_unlink)
        else:
            patch.setattr(module, 'save_cursor', fault_save)
        with pytest.raises((OSError, SQLAlchemyError)):
            effect(deletions, op)
    with app.state.sessions() as session:
        session.info['deletion_settings'] = app.state.settings
        with pytest.raises(AuthorityError):
            export_proposal(d['adapter'], op.operation_id, 'complete', session, d['export'])
    assert client.get(f'/api/v1/documents/{doc}').status_code in (404, 410)
    effect(deletions, op); confirm(deletions, op, 'complete')
    assert not path.exists() and count(app) == 1


@pytest.mark.parametrize('mode', ['missing', 'replaced', 'symlink', 'hardlink', 'permissions', 'sql_changed'])
def test_changed_plan_or_source_refused_before_effect(deletions, mode):
    _, app, _, _, doc, path = deletions
    op = execution(deletions); confirm(deletions, op, 'authorize')
    if mode == 'missing':
        path.unlink()
    elif mode == 'replaced':
        raw = path.read_bytes(); path.rename(path.with_suffix('.retained')); path.write_bytes(raw); path.chmod(0o600)
    elif mode == 'symlink':
        other = path.with_suffix('.retained'); path.rename(other); path.symlink_to(other)
    elif mode == 'hardlink':
        os.link(path, path.with_suffix('.retained'))
    elif mode == 'permissions':
        path.chmod(0o644)
    else:
        with app.state.sessions() as session:
            session.get(Document, doc).filename = 'changed-after-approval.txt'; session.commit()
    with pytest.raises((AuthorityError, OSError)):
        effect(deletions, op)
    with app.state.sessions() as session:
        assert session.get(Document, doc) is not None
    assert count(app) == 1


def test_owner_isolation_and_authority_outage(deletions):
    client, app, d, _, doc, _ = deletions
    body, op = prepare_http((client, app, d)); confirm_phase((client, app, d), op, 'reserve')
    assert send(client, body).status_code == 202
    confirm_phase((client, app, d), op, 'result'); assert send(client, body).status_code == 201
    token = client.post('/api/v1/auth/login', json={'email': body['email'], 'password': PASSWORD}).json()['session_token']
    client.headers['Authorization'] = 'Bearer '+token
    assert client.delete(f'/api/v1/documents/{doc}').status_code == 404
    assert client.get(f'/api/v1/documents/{doc}').status_code == 404
    assert client.get(f'/api/v1/documents/{doc}/deletion-status').status_code == 404
    assert not d['store'].deletions()
    (d['dirs']['control']/'accepted.json').unlink()
    assert client.delete(f'/api/v1/documents/{doc}').status_code in (401, 503)


def close(env):
    client, app, _, admission, *_ = env
    with app.state.sessions() as session:
        email = session.get(User, admission.user_id).email
        app.state.session_vault.create(session.get(User, admission.user_id))
    assert client.post('/api/v1/account/deletion-request', json={'password': 'wrong'}).status_code == 401
    response = client.post('/api/v1/account/deletion-request', json={'password': PASSWORD})
    assert response.status_code == 202 and response.json()['state'] == 'awaiting_confirmation'
    op = mutation(env, 'account_closure_request')
    confirm(env, op, 'authorize')
    assert client.get('/api/v1/account').status_code == 401
    assert not app.state.session_vault.sessions
    assert client.post('/api/v1/auth/login', json={'email': email,'password': PASSWORD}).status_code == 401
    assert client.post('/api/v1/documents').status_code == 401
    effect(env, op); confirm(env, op, 'complete')
    with app.state.sessions() as session:
        user = session.get(User, admission.user_id)
        assert user.disabled_at is not None
    return op


def test_closure_and_purge_preserve_counter_and_minimal_proofs(deletions):
    client, app, d, admission, doc, path = deletions
    request = close(deletions)
    with app.state.sessions() as session:
        before = session.get(User, admission.user_id).disabled_at
    effect(deletions, request)
    with app.state.sessions() as session:
        assert session.get(User, admission.user_id).disabled_at == before
        op = prepare_execution(session, app.state.settings, d['adapter'], request.operation_id, 'account_purge_execution')
    confirm(deletions, op, 'authorize'); effect(deletions, op)
    assert not path.exists()
    confirm(deletions, op, 'complete'); effect(deletions, op)
    with app.state.sessions() as session:
        assert session.get(User, admission.user_id) is None
        assert session.scalar(select(AccountToken.id)) is None
    assert count(app) == 1
    assert not d['store'].all()
    assert str(admission.id) in d['store'].payloads()
    assert admission.password_hash.encode() not in d['store'].path.read_bytes()
    recovered = d['ledger'].recover()['events']
    assert recovered[1]['request']['operation']['terms_accepted'] is True
    assert recovered[-1]['request']['operation']['kind'] == 'account_purge_execution'
    # A new adapter has no process memory; old boot proof must fail closed.
    restarted = OperationalConfirmation(store=LocalOperations(d['dirs']['application'], 0),
        control=d['dirs']['control'], instance=d['instance'], cohort=str(d['adapter'].cohort_id), public_key=d['public'])
    assert not restarted.ready()
    d['install'](d['ledger'].refresh(restarted.nonce, confirmation=restarted.nonce))
    assert restarted.ready()
    assert any(o.operation_id == op.operation_id for o in restarted.store.deletions())


@pytest.mark.parametrize('point', ['lost_commit_ack', 'unlink'])
def test_purge_partial_effect_is_resumed_and_never_recycles(deletions, monkeypatch, point):
    _, app, d, admission, _, path = deletions
    parent = close(deletions)
    with app.state.sessions() as session:
        op = prepare_execution(session, app.state.settings, d['adapter'], parent.operation_id, 'account_purge_execution')
    confirm(deletions, op, 'authorize')
    commit, unlink = Session.commit, Path.unlink
    def failed_commit(session):
        commit(session)
        raise SQLAlchemyError('synthetic lost acknowledgement')
    def failed_unlink(p, *a, **k):
        if p == path: raise PermissionError('synthetic physical failure')
        return unlink(p, *a, **k)
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', failed_commit) if point == 'lost_commit_ack' else patch.setattr(Path, 'unlink', failed_unlink)
        with pytest.raises((SQLAlchemyError, OSError)):
            effect(deletions, op)
    with app.state.sessions() as session:
        assert session.get(User, admission.user_id) is None
    assert path.exists() and count(app) == 1
    assert effect(deletions, op)['state'] == 'result_pending'
    confirm(deletions, op, 'complete')
    assert effect(deletions, op)['completed'] is True
    assert not path.exists() and count(app) == 1


def test_purge_keeps_other_owner_and_sixth_admission_refused(deletions):
    client, app, d, admission, _, path = deletions
    for _ in range(4):
        body, op = prepare_http((client, app, d))
        confirm_phase((client, app, d), op, 'reserve')
        assert send(client, body).status_code == 202
        confirm_phase((client, app, d), op, 'result')
        assert send(client, body).status_code == 201
    other_owner = op.owner_id
    other_path = app.state.settings.storage_dir / (uuid4().hex+'.txt')
    other_path.write_bytes(b'other synthetic owner'); other_path.chmod(0o600)
    with app.state.sessions() as session:
        other = Document(owner_id=other_owner, filename='other.txt', storage_name=other_path.name,
                         media_type='text/plain', size_bytes=other_path.stat().st_size,
                         sha256=hashlib.sha256(other_path.read_bytes()).hexdigest())
        session.add(other); session.commit()
        other_id = other.id
    parent = close(deletions)
    with app.state.sessions() as session:
        op = prepare_execution(session, app.state.settings, d['adapter'], parent.operation_id, 'account_purge_execution')
    confirm(deletions, op, 'authorize'); effect(deletions, op); confirm(deletions, op, 'complete')
    with app.state.sessions() as session:
        assert session.get(Document, other_id).owner_id == other_owner
        assert session.scalar(select(User.id).where(User.owner_id == other_owner)) is not None
    assert other_path.read_bytes() == b'other synthetic owner'
    assert not path.exists() and count(app) == 5
    from tests.test_lite_admissions import invitation
    assert send(client, invitation(app)).status_code == 403


def test_signed_deletion_rejects_forgery_wrong_cohort_and_replay(deletions):
    _, app, d, _, doc, path = deletions
    op = document_request(deletions)
    receipt = confirm(deletions, op, 'authorize')
    with pytest.raises(AuthorityError):
        d['install'](receipt)
    forged = {**receipt, 'signature': '0'*128}
    with pytest.raises(AuthorityError):
        d['install'](forged)
    with pytest.raises(AuthorityError):
        d['install'](sign({**receipt['payload'], 'cohort': str(uuid4())}, d['signing']))
    assert path.exists()
    with app.state.sessions() as session:
        assert session.get(Document, doc) is not None
        with pytest.raises(AuthorityError):
            prepare_execution(session, app.state.settings, d['adapter'], op.operation_id, 'document_deletion_execution')


def test_purge_unknown_residue_refuses_before_sql(deletions):
    _, app, d, admission, _, path = deletions
    parent = close(deletions)
    with app.state.sessions() as session:
        op = prepare_execution(session, app.state.settings, d['adapter'], parent.operation_id, 'account_purge_execution')
    confirm(deletions, op, 'authorize')
    residue = path.with_suffix('.part'); residue.write_bytes(b'unknown synthetic partial')
    with pytest.raises(AuthorityError, match='residue'):
        effect(deletions, op)
    with app.state.sessions() as session:
        assert session.get(User, admission.user_id) is not None
    assert path.exists() and residue.exists()


def test_root_cli_uses_api_owned_holds_without_bypass(deletions, monkeypatch, capsys, tmp_path):
    from backend.lite_authority import write
    from tools.lite_authority import main
    _, app, d, _, _, path = deletions
    op = document_request(deletions); confirm(deletions, op, 'authorize')
    uid = 10001
    for parent in (tmp_path, *tmp_path.parents):
        if parent in (Path('/tmp'), Path('/')):
            break
        parent.chmod(0o755)
    settings = app.state.settings
    owned = [d['dirs']['application'], settings.storage_dir,
             *(Path(p).parent for p in (settings.lifecycle_registry_path, settings.lifecycle_confirmation_path,
               settings.lifecycle_authenticated_confirmation_path, settings.lifecycle_authentication_key_path,
               settings.lifecycle_holds_path))]
    for directory in owned:
        for item in [*directory.rglob('*'), directory]:
            os.chown(item, uid, uid)
    d['store'].uid = uid
    settings.lite_authority_manifest = d['dirs']['control']/'manifest.json'
    manifest = dict(version=1, instance=d['instance'], cohort=str(d['adapter'].cohort_id), api_uid=uid,
        store=str(d['dirs']['application']), control=str(d['dirs']['control']),
        authority_public_key=d['public'], export_private_key=str(d['dirs']['export_keys']/'signing'),
        export_public_key=d['export_public'], database_sha256=hashlib.sha256(settings.database_url.encode()).hexdigest(),
        independence=d['ledger'].attest_domains(str(uuid4()), str(uuid4()), str(uuid4()), reference=str(uuid4()),
                                               scope='deployment', confirmation=d['instance']))
    write(settings.lite_authority_manifest, canonical(manifest), 0, public=True)
    monkeypatch.setattr('backend.config.Settings', lambda **kwargs: settings)
    flags = ['--instance', d['instance'], '--cohort', str(d['adapter'].cohort_id)]
    common = ['--manifest', str(settings.lite_authority_manifest), '--operation', op.operation_id]
    assert main([*flags, 'app-apply-deletion', *common, '--confirm', op.operation_id, '--offline-confirmed']) == 0
    assert os.geteuid() == 0 and path.exists()
    out = d['dirs']['outbox']/'closure-export.json'
    assert main([*flags, 'app-export', *common, '--phase', 'complete', '--out', str(out)]) == 0
    from backend.lite_authority import strict
    receipt = d['ledger'].approve(strict(out.read_bytes()), confirmation=op.operation_id, reference='synthetic-cli')
    d['install'](receipt)
    assert main([*flags, 'app-prepare-deletion', *common, '--kind', 'document_deletion_execution',
                 '--confirm', op.operation_id, '--offline-confirmed']) == 0
    assert os.geteuid() == 0
    prepared = next(o for o in d['adapter'].store.deletions() if o.parent_id == op.operation_id)
    output = capsys.readouterr().out
    assert prepared.operation_id in output and PASSWORD not in output
    for phase in ('authorize', 'complete'):
        target = d['dirs']['outbox']/('execution-'+phase+'.json')
        flags_for_op = ['--manifest', str(settings.lite_authority_manifest), '--operation', prepared.operation_id]
        assert main([*flags, 'app-export', *flags_for_op, '--phase', phase, '--out', str(target)]) == 0
        d['install'](d['ledger'].approve(strict(target.read_bytes()), confirmation=prepared.operation_id,
                                        reference='synthetic-cli-execution'))
        if phase == 'authorize':
            from backend.lite_deletions import application_identity
            with application_identity(d['adapter']), app.state.sessions() as session:
                with pytest.raises(AuthorityError):
                    apply(session, settings, d['adapter'], prepared.operation_id,
                          confirmation=prepared.operation_id, offline_confirmed=True)
            assert path.exists()
            assert main([*flags, 'app-apply-deletion', *flags_for_op,
                         '--confirm', prepared.operation_id, '--offline-confirmed']) == 0
    assert not path.exists()


def test_real_derived_rows_are_cascaded_not_just_the_original(deletions):
    from backend.ai.models import AIReservation, AISource, AISummary, AIInteraction, AIUsage
    from backend.ai.long_models import LongSummaryJob, SummaryStep
    from backend.rag.models import ChunkEmbedding, IndexJob, RAGDocument, RAGResult, OperationDocument
    _, app, _, admission, doc, path = deletions
    with app.state.sessions() as session:
        reservation = AIReservation(owner_id=admission.owner_id, budget_id='development', document_id=doc,
            idempotency_key=uuid4(), request_hash='a'*64, feature='summary', status='completed',
            reserved_usd=0, model='synthetic', provider='synthetic')
        session.add(reservation); session.flush()
        chunk = session.scalar(select(DocumentChunk).where(DocumentChunk.document_id == doc))
        session.add(AISource(reservation_id=reservation.id, document_id=doc, chunk_id=chunk.id))
        session.add(AISummary(document_id=doc, owner_id=admission.owner_id, reservation_id=reservation.id,
                              content={'synthetic':'derived'}, coverage='complete'))
        session.add(AIInteraction(document_id=doc, owner_id=admission.owner_id, reservation_id=reservation.id,
            question='synthetic', content={'synthetic':'answer'}, coverage='complete'))
        session.add(ChunkEmbedding(chunk_id=chunk.id, document_id=doc, owner_id=admission.owner_id,
            vector=[0.0, 1.0, 0.0], model='synthetic', dimensions=3, version='test'))
        session.add(IndexJob(document_id=doc, owner_id=admission.owner_id, model='synthetic', dimensions=3,
                             version='test', total=1, status='completed'))
        job = LongSummaryJob(owner_id=admission.owner_id, document_id=doc, reservation_id=reservation.id,
                             status='completed', plan={}, configuration={})
        session.add(job); session.flush()
        session.add(SummaryStep(job_id=job.id, node_id='test', status='completed', content={'test':1},
                                chunk_ids=[], pages=[]))
        result = RAGResult(owner_id=admission.owner_id, kind='synthetic', request_hash='b'*64,
                           content={'synthetic':'result'})
        session.add(result); session.flush()
        session.add(RAGDocument(result_id=result.id, document_id=doc))
        session.add(OperationDocument(reservation_id=reservation.id, document_id=doc))
        session.commit()
    op = execution(deletions); confirm(deletions, op, 'authorize')
    effect(deletions, op); confirm(deletions, op, 'complete')
    assert not path.exists()
    with app.state.sessions() as session:
        for model in (Document, DocumentPage, DocumentChunk, Analysis, AISource, AISummary, AIInteraction,
                      ChunkEmbedding, IndexJob, LongSummaryJob, SummaryStep, RAGDocument, RAGResult, OperationDocument):
            assert session.scalar(select(model).limit(1)) is None, model.__tablename__
        assert session.get(AIReservation, reservation.id).document_id is None


def test_cross_owner_derived_reference_blocks_preparation(deletions):
    from backend.rag.models import RAGDocument, RAGResult
    client, app, d, _, doc, path = deletions
    with app.state.sessions() as session:
        result = RAGResult(owner_id=uuid4(), kind='synthetic', request_hash='b'*64, content={'synthetic':'other'})
        session.add(result); session.flush()
        session.add(RAGDocument(result_id=result.id, document_id=doc)); session.commit()
    assert client.delete(f'/api/v1/documents/{doc}').status_code == 503
    assert not d['store'].deletions() and path.exists()


@pytest.mark.parametrize('moment', ['before_request', 'after_preparation', 'after_sql'])
def test_holds_block_without_false_result(deletions, moment):
    from datetime import timedelta
    from backend.lifecycle_holds import HoldStore, ActiveHoldError
    from backend.lifecycle_durability import configured_coordinator
    from backend.lifecycle_registry import configured_registry
    _, app, d, admission, doc, path = deletions
    op = None
    if moment != 'before_request':
        op = execution(deletions); confirm(deletions, op, 'authorize')
    if moment == 'after_sql':
        # A denied unlink leaves a real SQL-absent, file-present residual.
        original = Path.unlink
        from unittest.mock import patch
        def denied(p, *a, **k):
            if p == path: raise PermissionError('synthetic denied')
            return original(p, *a, **k)
        with patch.object(Path, 'unlink', denied), pytest.raises(OSError):
            effect(deletions, op)
    coordinator = configured_coordinator(app.state.settings, configured_registry(app.state.settings))
    store = HoldStore(app.state.settings.lifecycle_holds_path, coordinator.authenticated)
    at = __import__('backend.models', fromlist=['now']).now()
    store.create(dict(id=str(uuid4()), responsible_id=str(uuid4()), scope_kind='owner', scope_id=str(admission.owner_id),
                      reason='legal_hold', reviewed_at=at, review_at=at+timedelta(days=1),
                      ends_at=None, end_event='legal_hold_lifted'), at)
    if moment == 'before_request':
        response = deletions[0].delete(f'/api/v1/documents/{doc}')
        assert response.status_code == 409
        assert not d['store'].deletions()
    else:
        with pytest.raises(ActiveHoldError):
            effect(deletions, op)
    assert path.exists()


def test_cli_and_synthetic_guard_cannot_bypass_authorization(deletions):
    from backend.lifecycle_durability import require_synthetic_mutation
    from backend.account_admin import purge_account
    from backend.services.documents import delete_document
    client, app, d, admission, doc, path = deletions
    with pytest.raises(ValueError):
        require_synthetic_mutation(app.state.settings)
    with app.state.sessions() as session:
        with pytest.raises(ValueError):
            purge_account(session, app.state.settings, admission.user_id)
        with pytest.raises(Exception) as error:
            delete_document(session, app.state.settings, session.get(Document, doc))
        assert error.value.status_code == 503
    op = document_request(deletions)
    with app.state.sessions() as session:
        for kwargs in ({'confirmation': op.operation_id}, {'confirmation': 'wrong', 'offline_confirmed': True}):
            with pytest.raises(AuthorityError):
                apply(session, app.state.settings, d['adapter'], op.operation_id, **kwargs)
    assert path.exists()


def test_deletion_types_have_exact_transitions_and_zero_counter_effect():
    from backend.lite_authority import DeletionOperation, validate_request
    instance, cohort = str(uuid4()), str(uuid4())
    target, owner = str(uuid4()), str(uuid4())
    op = DeletionOperation(str(uuid4()), 'account_closure_request', target, owner, target,
                           None, {'documents': [], 'sql_sha256': 'a'*64, 'result_ids': [], 'token_ids': []},
                           '2026-10-30T00:00:00+00:00')
    request = dict(version=1, instance=instance, cohort=cohort, challenge='b'*64,
                   operation=operation_payload(op), phase='authorize', counter=0, facts='deletion_plan_verified')
    validate_request(request, instance, cohort)
    event = dict(version=1, instance=instance, cohort=cohort, sequence=1, previous='',
                 at=op.requested_at, reference='synthetic', request=request)
    assert project([event], instance, cohort)[1] == 0
    for change in ({'phase':'complete','facts':'deletion_effect_verified'}, {'counter':1}):
        with pytest.raises(AuthorityError):
            project([{**event, 'request': {**request, **change}}], instance, cohort)
