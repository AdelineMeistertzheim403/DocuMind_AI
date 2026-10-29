"""Local synthetic-only integration and interruption tests for lot 2.2."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import sqlite3
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import select

from backend.account_admin import _purge_account, purge_account, registration_control
from backend.account_models import DeletionRequest, PublicRegistrationQuota
from backend.auth import User
from backend.lifecycle_admissions import AdmissionCoordinator, configured_admissions
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import AuthenticatedCoordinator, DurableCoordinator, configured_coordinator
from backend.lifecycle_holds import HoldStore
from backend.models import Document
from tests.test_lifecycle_durability import attach_legacy_owner, enable, ledgers
from tests.test_public_beta import PASSWORD, beta, enroll, signup_body, verify_and_login


def authenticated(settings):
    return AuthenticatedConfirmationStore(settings.lifecycle_authenticated_confirmation_path,
        settings.lifecycle_authentication_key_path.read_bytes(), 'documind-local-v2')


def holds(settings):
    return HoldStore(settings.lifecycle_holds_path, authenticated(settings))


def hold_for(kind, identifier):
    at = datetime.now(timezone.utc) - timedelta(seconds=1)
    return {'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(identifier),
            'scope_kind': kind, 'reason': 'legal_hold', 'reviewed_at': at,
            'review_at': at + timedelta(days=29), 'ends_at': None,
            'end_event': 'legal_hold_lifted'}, at


def strict_beta(beta, ledgers):
    client, app, _ = beta
    app.state.settings.public_registration_limit = 5
    enable(app, ledgers)
    verify_and_login(beta)
    return client, app


@pytest.mark.posix
def test_synthetic_mutation_switch_defaults_closed_even_with_provisioned_stores(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    app.state.settings.lifecycle_synthetic_mutations_enabled = False
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert response.status_code == 201
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    options = client.get('/api/v1/auth/options').json()
    assert options['public_registration_availability'] == 'closed'
    client.headers['X-Documind-Client-IP'] = '192.0.2.80'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'second@example.test')).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is not None
        assert session.scalar(select(User)).disabled_at is None
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1
    with ledgers[0].connection() as db:
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 0
        assert db.execute('SELECT count(*) FROM document_erasures').fetchone()[0] == 0


@pytest.mark.parametrize('kind', ['account', 'owner', 'document'])
@pytest.mark.posix
def test_scoped_hold_blocks_document_until_evidenced_release(beta, ledgers, kind):
    client, app = strict_beta(beta, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert response.status_code == 201
    with app.state.sessions() as session:
        user = session.scalar(select(User))
        document = session.scalar(select(Document))
        source = app.state.settings.storage_dir / document.storage_name
        target = {'account': user.id, 'owner': user.owner_id, 'document': document.id}[kind]
    registry = holds(app.state.settings)
    hold, at = hold_for(kind, target)
    registry.create(hold, at)
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 409
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is not None
    assert source.exists()
    with pytest.raises(ValueError, match='evidence'):
        registry.release(hold['id'], hold['responsible_id'], str(uuid4()), b'', datetime.now(timezone.utc))
    registry.release(hold['id'], hold['responsible_id'], str(uuid4()),
                     b'synthetic documented decision', datetime.now(timezone.utc))
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 204
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is None
    assert not source.exists()


@pytest.mark.posix
def test_account_hold_blocks_deactivation_without_creating_receipt(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    with app.state.sessions() as session:
        user = session.scalar(select(User))
        identifier = user.id
    hold, at = hold_for('account', identifier)
    registry = holds(app.state.settings)
    registry.create(hold, at)
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 409
    with app.state.sessions() as session:
        assert session.get(User, identifier).disabled_at is None
        assert session.scalar(select(DeletionRequest)) is None
    with ledgers[0].connection() as db:
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 0
    registry.release(hold['id'], hold['responsible_id'], str(uuid4()),
                     b'synthetic release proof', datetime.now(timezone.utc))
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 202
    with app.state.sessions() as session:
        assert session.get(User, identifier).disabled_at is not None


@pytest.mark.posix
def test_unrelated_hold_does_not_block_mutation(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    hold, at = hold_for('document', uuid4())
    holds(app.state.settings).create(hold, at)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 204


@pytest.mark.parametrize('kind', ['account', 'owner', 'unrelated'])
@pytest.mark.posix
def test_failed_upload_cleanup_respects_known_hold_scope(beta, ledgers, monkeypatch, kind):
    from backend.services import documents
    client, app = strict_beta(beta, ledgers)
    with app.state.sessions() as session:
        user = session.scalar(select(User))
        target = {'account': user.id, 'owner': user.owner_id, 'unrelated': uuid4()}[kind]
    hold, at = hold_for('owner' if kind == 'unrelated' else kind, target)
    holds(app.state.settings).create(hold, at)
    monkeypatch.setattr(documents, 'run_worker',
                        lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic extraction failure')))
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert response.status_code == 500
    retained = list(app.state.settings.storage_dir.glob('*.part'))
    assert len(retained) == (0 if kind == 'unrelated' else 1)
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is None


@pytest.mark.posix
def test_failed_upload_retains_temporary_file_when_holds_unavailable(beta, ledgers, monkeypatch):
    from backend.services import documents
    client, app = strict_beta(beta, ledgers)
    app.state.settings.lifecycle_holds_path = app.state.settings.lifecycle_holds_path.parent / 'absent.sqlite'
    monkeypatch.setattr(documents, 'run_worker',
                        lambda *args: (_ for _ in ()).throw(RuntimeError('synthetic extraction failure')))
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert response.status_code == 500
    assert len(list(app.state.settings.storage_dir.glob('*.part'))) == 1


def test_hold_writer_waits_for_mutation_fence(app, ledgers):
    enable(app, ledgers)
    registry = holds(app.state.settings)
    hold, at = hold_for('document', uuid4())
    started = Event()
    def create():
        started.set()
        registry.create(hold, at)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with registry.guard([('owner', uuid4())]):
            future = pool.submit(create)
            assert started.wait(2)
            assert not future.done()
        future.result(timeout=5)
    with pytest.raises(ValueError, match='Active hold'):
        with registry.guard([('document', hold['scope_id'])]):
            pytest.fail('A held mutation must not start')


@pytest.mark.posix
def test_hold_creation_serializes_with_document_commit(beta, ledgers, monkeypatch):
    client, app = strict_beta(beta, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    identifier = response.json()['id']
    registry = holds(app.state.settings)
    hold, at = hold_for('document', identifier)
    authorized, proceed, creator_started = Event(), Event(), Event()
    original = AuthenticatedCoordinator.authorize_document
    def pause_after_authorization(self, document_id):
        original(self, document_id)
        authorized.set()
        if not proceed.wait(4):
            raise RuntimeError('Synthetic synchronization timeout')
    def create():
        creator_started.set()
        registry.create(hold, at)
    monkeypatch.setattr(AuthenticatedCoordinator, 'authorize_document', pause_after_authorization)
    with ThreadPoolExecutor(max_workers=2) as pool:
        deletion = pool.submit(client.delete, '/api/v1/documents/' + identifier)
        assert authorized.wait(3)
        creation = pool.submit(create)
        assert creator_started.wait(2)
        assert not creation.done()
        proceed.set()
        assert deletion.result(timeout=5).status_code == 204
        creation.result(timeout=5)
    with pytest.raises(ValueError, match='Active hold'):
        with registry.guard([('document', identifier)]):
            pytest.fail('The subsequent hold must be durable')


@pytest.mark.parametrize('tamper', ['remove_local', 'alter_release', 'alter_tag'])
def test_hold_divergence_or_missing_evidence_blocks_mutation(app, ledgers, tamper):
    enable(app, ledgers)
    registry = holds(app.state.settings)
    hold, at = hold_for('owner', uuid4())
    registry.create(hold, at)
    if tamper == 'remove_local':
        with registry.store.connection() as db:
            db.execute('DELETE FROM hold_decisions_v2')
            db.execute('DELETE FROM holds_v2')
    elif tamper == 'alter_release':
        with registry.store.connection() as db:
            db.execute('UPDATE holds_v2 SET released=1')
    else:
        with registry.authenticated.store.connection() as db:
            db.execute("UPDATE hold_mirrors SET tag=?", ('0' * 64,))
    with pytest.raises(ValueError):
        with registry.guard([('owner', uuid4())]):
            pytest.fail('Divergent hold stores must close all mutations')


def test_interrupted_hold_publication_fails_closed(app, ledgers, monkeypatch):
    enable(app, ledgers)
    registry = holds(app.state.settings)
    hold, at = hold_for('owner', uuid4())
    original = registry.authenticated.update_hold
    def lost_reply(expected, snapshot):
        original(expected, snapshot)
        raise OSError('synthetic response lost')
    monkeypatch.setattr(registry.authenticated, 'update_hold', lost_reply)
    with pytest.raises(OSError):
        registry.create(hold, at)
    with pytest.raises(ValueError, match='registries differ'):
        with registry.guard([('owner', hold['scope_id'])]):
            pytest.fail('Uncertain hold creation must block mutation')


@pytest.mark.posix
def test_legacy_digest_is_not_promoted_to_authenticated_proof(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    with app.state.sessions() as session:
        user = session.scalar(select(User))
        identifier, owner = user.id, user.owner_id
    receipt = ledgers[0].receive('erasure', user_id=identifier, owner_id=owner)
    DurableCoordinator(*ledgers).confirm_account(receipt)
    with ledgers[1].connection() as db:
        before = tuple(db.execute('SELECT operation,payload,digest FROM confirmations').fetchone())
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.get(User, identifier).disabled_at is None
    with ledgers[1].connection() as db:
        assert tuple(db.execute('SELECT operation,payload,digest FROM confirmations').fetchone()) == before
    with authenticated(app.state.settings).store.connection() as db:
        assert db.execute('SELECT count(*) FROM synthetic_transitions').fetchone()[0] == 0


@pytest.mark.posix
def test_lost_authorization_reply_never_reauthorizes_mutation(beta, ledgers, monkeypatch):
    client, app = strict_beta(beta, ledgers)
    original = AuthenticatedCoordinator.authorize_account
    def lost_reply(self, identifier):
        original(self, identifier)
        raise OSError('synthetic authorization response lost')
    monkeypatch.setattr(AuthenticatedCoordinator, 'authorize_account', lost_reply)
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    monkeypatch.setattr(AuthenticatedCoordinator, 'authorize_account', original)
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None
        assert session.scalar(select(DeletionRequest)) is None
    with authenticated(app.state.settings).store.connection() as db:
        assert db.execute('SELECT count(*) FROM synthetic_transitions').fetchone()[0] == 3
    with pytest.raises(ValueError, match='reconciliation'):
        configured_coordinator(app.state.settings, ledgers[0]).verify_recovery_receipts()


@pytest.mark.posix
def test_concurrent_authorization_is_issued_only_once(app, ledgers):
    enable(app, ledgers)
    registry, _ = ledgers
    coordinator = configured_coordinator(app.state.settings, registry)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    coordinator.confirm_account(receipt)
    def authorize():
        try:
            return coordinator.authorize_account(receipt)
        except ValueError:
            return 'reconciliation_required'
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: authorize(), range(2)))
    assert sorted(outcomes) == ['authorized', 'reconciliation_required']


@pytest.mark.posix
def test_signed_prefix_rollback_can_hide_prior_authorization(app, ledgers):
    enable(app, ledgers)
    registry, _ = ledgers
    coordinator = configured_coordinator(app.state.settings, registry)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    coordinator.confirm_account(receipt)
    assert coordinator.authorize_account(receipt) == 'authorized'
    with coordinator.authenticated.store.connection() as db:
        db.execute('DELETE FROM synthetic_transitions WHERE sequence=3')
    assert not coordinator.verify_recovery_receipts()['opening_authorized']
    assert coordinator.authorize_account(receipt) == 'authorized'


@pytest.mark.posix
def test_wrong_confirmation_key_is_refused_even_for_empty_ledger(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    app.state.settings.lifecycle_authentication_key_path.write_bytes(os.urandom(32))
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with ledgers[0].connection() as db:
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 0
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None


def test_missing_hold_registry_blocks_document_before_receipt(client, app, ledgers):
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    app.state.settings.lifecycle_holds_path = app.state.settings.lifecycle_holds_path.parent / 'absent.sqlite'
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is not None
    with ledgers[0].connection() as db:
        assert db.execute('SELECT count(*) FROM document_erasures').fetchone()[0] == 0


@pytest.mark.posix
def test_older_registry_cannot_hide_newer_authenticated_receipt(app, ledgers, tmp_path):
    enable(app, ledgers)
    registry, witness = ledgers
    recovery_dir = tmp_path / 'old-registry'
    recovery_dir.mkdir(mode=0o700)
    old_path = recovery_dir / 'registry.sqlite'
    with registry.connection() as source, sqlite3.connect(old_path) as target:
        source.backup(target)
    os.chmod(old_path, 0o600)
    coordinator = configured_coordinator(app.state.settings, registry)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    coordinator.confirm_account(receipt)
    assert coordinator.verify_recovery_receipts()['complete_for_observed_stores']
    recovered = AuthenticatedCoordinator(type(registry)(old_path), witness, authenticated(app.state.settings))
    with pytest.raises(ValueError, match='sets differ'):
        recovered.verify_recovery_receipts()


@pytest.mark.posix
def test_result_failure_after_commit_is_visible_and_blocks_recovery(beta, ledgers, monkeypatch):
    client, app = strict_beta(beta, ledgers)
    monkeypatch.setattr(AuthenticatedCoordinator, 'account_result',
                        lambda *args: (_ for _ in ()).throw(OSError('synthetic result failure')))
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is not None
        assert session.scalar(select(DeletionRequest)) is not None
    with ledgers[0].connection() as db:
        assert db.execute('SELECT state FROM requests').fetchone()[0] == 'deactivated'
    with pytest.raises(ValueError, match='reconciliation'):
        configured_coordinator(app.state.settings, ledgers[0]).verify_recovery_receipts()


@pytest.mark.posix
def test_successful_receipt_recovery_checks_state_and_rejects_truncation(beta, ledgers):
    client, app = strict_beta(beta, ledgers)
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 202
    coordinator = configured_coordinator(app.state.settings, ledgers[0])
    assert not coordinator.verify_recovery_receipts()['opening_authorized']
    with coordinator.authenticated.store.connection() as db:
        db.execute('DELETE FROM synthetic_transitions WHERE sequence>2')
    with pytest.raises(ValueError, match='reconciliation'):
        coordinator.verify_recovery_receipts()


@pytest.mark.posix
def test_commit_response_lost_keeps_document_reconciliation_closed(client, app, ledgers, monkeypatch):
    from backend.services.documents import delete_document
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert response.status_code == 201
    with app.state.sessions() as session:
        document = session.scalar(select(Document))
        path = app.state.settings.storage_dir / document.storage_name
        original = session.commit
        def lost_reply():
            original()
            raise RuntimeError('synthetic SQL commit response lost')
        monkeypatch.setattr(session, 'commit', lost_reply)
        with pytest.raises(RuntimeError, match='response lost'):
            delete_document(session, app.state.settings, document)
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is None
    assert not path.exists()
    with ledgers[0].connection() as db:
        assert db.execute('SELECT state FROM document_erasures').fetchone()[0] == 'requested'
    with pytest.raises(ValueError, match='reconciliation'):
        configured_coordinator(app.state.settings, ledgers[0]).verify_recovery_receipts()


@pytest.mark.posix
def test_failure_after_file_cleanup_is_not_reported_as_success(client, app, ledgers, monkeypatch):
    from backend.lifecycle_registry import Registry
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    with app.state.sessions() as session:
        document = session.scalar(select(Document))
        path = app.state.settings.storage_dir / document.storage_name
    monkeypatch.setattr(Registry, 'document_finished',
                        lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError('synthetic ledger failure')))
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    assert not path.exists()
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is None
    with pytest.raises(ValueError, match='reconciliation'):
        configured_coordinator(app.state.settings, ledgers[0]).verify_recovery_receipts()


@pytest.mark.posix
def test_lost_reply_after_recorded_result_does_not_repeat_document_deletion(client, app, ledgers, monkeypatch):
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    original = AuthenticatedCoordinator.document_result
    def lost_reply(self, identifier):
        original(self, identifier)
        raise OSError('synthetic result response lost')
    monkeypatch.setattr(AuthenticatedCoordinator, 'document_result', lost_reply)
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 404
    coordinator = configured_coordinator(app.state.settings, ledgers[0])
    assert coordinator.verify_recovery_receipts()['complete_for_observed_stores']
    assert not coordinator.verify_recovery_receipts()['opening_authorized']


def test_unlinked_document_account_scope_blocks_strict_deletion(client, app, ledgers):
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake', 'text/plain')})
    assert client.delete('/api/v1/documents/' + response.json()['id']).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is not None
    with ledgers[0].connection() as db:
        assert db.execute('SELECT count(*) FROM document_erasures').fetchone()[0] == 0


def test_strict_account_purge_is_blocked_even_at_internal_entry(app, ledgers):
    enable(app, ledgers)
    for function in (purge_account, _purge_account):
        with pytest.raises(ValueError, match='Account purge disabled'):
            function(None, app.state.settings, uuid4())


def test_stale_witness_and_wrong_anchor_key_block_new_admission(beta, ledgers):
    client, app, _ = beta
    app.state.settings.public_registration_limit = 5
    enroll(beta, 'first@example.test')
    enable(app, ledgers)
    options = client.get('/api/v1/auth/options').json()
    assert not options['public_capacity_configured']
    assert options['public_registration_availability'] == 'closed'
    client.headers['X-Documind-Client-IP'] = '192.0.2.77'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'second@example.test')).status_code == 503
    with app.state.sessions() as session:
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1
        with pytest.raises(ValueError, match='Réouverture interdite'):
            registration_control(session, app.state.settings, 'reopen', execute=True)


@pytest.mark.posix
def test_pending_admission_after_commit_blocks_following_admission(beta, ledgers, monkeypatch):
    client, app, sent = beta
    app.state.settings.public_registration_limit = 5
    enable(app, ledgers)
    monkeypatch.setattr(AdmissionCoordinator, 'settle',
                        lambda *args: (_ for _ in ()).throw(OSError('synthetic settlement failure')))
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'first@example.test')).status_code == 503
    assert sent.empty()
    with app.state.sessions() as session:
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1
    coordinator = configured_coordinator(app.state.settings, ledgers[0])
    admissions = configured_admissions(app.state.settings, coordinator)
    assert admissions.inspect(1)['state'] == 'reconciliation_required'
    assert admissions.inspect(1)['keep_registration_closed']
    options = client.get('/api/v1/auth/options').json()
    assert not options['public_capacity_configured']
    assert options['public_registration_availability'] == 'closed'
    client.headers['X-Documind-Client-IP'] = '192.0.2.78'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'second@example.test')).status_code == 503
    with app.state.sessions() as session:
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1


@pytest.mark.posix
def test_wrong_anchor_key_rejected_without_witness_change(beta, ledgers):
    client, app, _ = beta
    app.state.settings.public_registration_limit = 5
    enable(app, ledgers)
    enroll(beta, 'first@example.test')
    app.state.settings.lifecycle_admission_key_path.write_bytes(os.urandom(32))
    client.headers['X-Documind-Client-IP'] = '192.0.2.79'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'second@example.test')).status_code == 503
    assert len(ledgers[1].admission_entries()) == 1
