"""Synthetic-only tests for opt-in confirmation and retention prototypes."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import os
import sqlite3
from uuid import UUID, uuid4

import pytest
from cryptography.exceptions import InvalidTag
from sqlalchemy import select

from backend.account_admin import purge_account, registration_control
from backend.account_models import DeletionRequest, PublicRegistrationQuota
from backend.auth import User
from backend.config import Settings
from backend.lifecycle_admissions import AdmissionAnchor
from backend.lifecycle_authenticated import AuthenticatedConfirmationStore
from backend.lifecycle_durability import AuthenticatedCoordinator, ConfirmationStore, DurableCoordinator
from backend.lifecycle_holds import HoldStore
from backend.lifecycle_registry import Registry
from backend.lifecycle_retention_policy import receipt_expiry_plan
from backend.models import now
from ops.testing.lifecycle_lot2_backup import encrypted_snapshot, verify_snapshot
from tests.test_public_beta import beta, enroll, signup_body, verify_and_login, PASSWORD
from tests.test_public_beta_postgresql_concurrency import pg_beta, actors, seed, parallel, rendezvous, counts


@pytest.fixture
def ledgers(tmp_path):
    for name in ('local', 'independent', 'authenticated', 'key', 'holds', 'anchor', 'anchor-key'):
        (tmp_path / name).mkdir(mode=0o700)
    local, independent = tmp_path / 'local', tmp_path / 'independent'
    registry = Registry(local / 'registry.sqlite')
    registry.initialize()
    store = ConfirmationStore(independent / 'confirm.sqlite')
    store.initialize()
    key = os.urandom(32)
    key_path = tmp_path / 'key' / 'synthetic.key'
    key_path.write_bytes(key)
    os.chmod(key_path, 0o600)
    authenticated = AuthenticatedConfirmationStore(tmp_path / 'authenticated' / 'proof.sqlite',
                                                   key, 'documind-local-v2')
    authenticated.initialize()
    HoldStore(tmp_path / 'holds' / 'holds.sqlite', authenticated).initialize()
    admission_key = os.urandom(32)
    admission_key_path = tmp_path / 'anchor-key' / 'synthetic.key'
    admission_key_path.write_bytes(admission_key)
    os.chmod(admission_key_path, 0o600)
    AdmissionAnchor(tmp_path / 'anchor' / 'anchor.sqlite', admission_key).initialize()
    return registry, store


def enable(app, ledgers):
    registry, store = ledgers
    app.state.settings.lifecycle_registry_path = registry.path
    app.state.settings.lifecycle_confirmation_path = store.path
    root = registry.path.parent.parent
    app.state.settings.lifecycle_authenticated_confirmation_path = root / 'authenticated' / 'proof.sqlite'
    app.state.settings.lifecycle_authentication_key_path = root / 'key' / 'synthetic.key'
    app.state.settings.lifecycle_holds_path = root / 'holds' / 'holds.sqlite'
    app.state.settings.lifecycle_admission_anchor_path = root / 'anchor' / 'anchor.sqlite'
    app.state.settings.lifecycle_admission_key_path = root / 'anchor-key' / 'synthetic.key'
    app.state.settings.lifecycle_durable_receipts_required = True
    app.state.settings.lifecycle_synthetic_mutations_enabled = True


def attach_legacy_owner(app):
    with app.state.sessions() as session:
        session.add(User(owner_id=UUID(int=1), username='synthetic-owner', password_hash='unused-synthetic-hash'))
        session.commit()


def test_strict_confirmation_is_default():
    assert Settings(_env_file=None).lifecycle_durable_receipts_required is True
    assert Settings(_env_file=None).lifecycle_synthetic_mutations_enabled is False


@pytest.mark.posix
def test_account_confirmation_idempotence_and_divergence(ledgers):
    registry, store = ledgers
    coordinator = DurableCoordinator(registry, store)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: coordinator.confirm_account(receipt), range(2)))
    assert results[0] == results[1]
    with registry.connection() as db:
        db.execute('UPDATE requests SET owner_id=? WHERE id=?', (str(uuid4()), receipt))
    with pytest.raises(ValueError, match='Conflicting'):
        coordinator.confirm_account(receipt)


@pytest.mark.parametrize('point', ['local', 'before_confirm', 'during_confirm',
                                   pytest.param('after_confirm', marks=pytest.mark.posix)])
def test_account_deletion_fails_closed_at_boundaries(beta, ledgers, monkeypatch, point):
    client, app, _ = beta
    verify_and_login(beta)
    enable(app, ledgers)
    registry, store = ledgers
    if point == 'local':
        monkeypatch.setattr(Registry, 'receive', lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError()))
    elif point == 'before_confirm':
        monkeypatch.setattr(AuthenticatedCoordinator, 'confirm_account', lambda *args: (_ for _ in ()).throw(OSError()))
    elif point == 'during_confirm':
        monkeypatch.setattr(AuthenticatedConfirmationStore, 'confirm', lambda *args: (_ for _ in ()).throw(sqlite3.OperationalError()))
    else:
        original = AuthenticatedCoordinator.confirm_account
        def lost_reply(self, identifier):
            original(self, identifier)
            raise OSError('synthetic response lost')
        monkeypatch.setattr(AuthenticatedCoordinator, 'confirm_account', lost_reply)
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None
    if point == 'after_confirm':
        with sqlite3.connect(app.state.settings.lifecycle_authenticated_confirmation_path) as db:
            assert db.execute('SELECT count(*) FROM synthetic_transitions').fetchone()[0] == 2
        monkeypatch.setattr(AuthenticatedCoordinator, 'confirm_account', original)
        assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 202


def test_document_failure_prevents_sql_and_file_deletion(client, app, ledgers, monkeypatch):
    from backend.models import Document
    attach_legacy_owner(app)
    enable(app, ledgers)
    response = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake document', 'text/plain')})
    assert response.status_code == 201
    identifier = response.json()['id']
    with app.state.sessions() as db:
        document = db.scalar(select(Document))
        source = app.state.settings.storage_dir / document.storage_name
    monkeypatch.setattr(AuthenticatedConfirmationStore, 'confirm', lambda *args: (_ for _ in ()).throw(OSError()))
    assert client.delete('/api/v1/documents/' + identifier).status_code == 503
    with app.state.sessions() as db:
        assert db.scalar(select(Document)) is not None
    assert source.exists()


@pytest.mark.posix
def test_authenticated_receipts_survive_deactivation_and_document_erasure(beta, ledgers):
    from backend.models import Document
    from backend.services.documents import delete_document
    client, app, _ = beta
    verify_and_login(beta)
    enable(app, ledgers)
    created = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake document', 'text/plain')})
    assert created.status_code == 201
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 202
    with app.state.sessions() as session:
        user = session.scalar(select(User))
        with pytest.raises(ValueError, match='Account purge disabled'):
            purge_account(session, app.state.settings, user.id)
        delete_document(session, app.state.settings, session.scalar(select(Document)))
        assert session.scalar(select(User)) is not None
        assert session.scalar(select(Document)) is None
        assert session.get(PublicRegistrationQuota, 'public').issued_count == 1
    with sqlite3.connect(app.state.settings.lifecycle_authenticated_confirmation_path) as db:
        rows = db.execute('SELECT envelope FROM synthetic_transitions').fetchall()
    assert len(rows) == 8
    assert all('example.test' not in row[0] and 'fake document' not in row[0] for row in rows)


def test_missing_or_unavailable_confirmation_blocks_strict_mode(beta, ledgers):
    client, app, _ = beta
    verify_and_login(beta)
    enable(app, ledgers)
    app.state.settings.lifecycle_confirmation_path = ledgers[1].path.parent / 'absent.sqlite'
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None


def test_missing_both_ledgers_blocks_default_strict_mode(beta):
    client, app, _ = beta
    verify_and_login(beta)
    app.state.settings.lifecycle_durable_receipts_required = True
    assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as session:
        assert session.scalar(select(User)).disabled_at is None


@pytest.mark.posix
def test_document_cleanup_failure_retains_confirmed_receipt(client, app, ledgers, monkeypatch):
    from backend.services import documents
    attach_legacy_owner(app)
    enable(app, ledgers)
    created = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake document', 'text/plain')})
    assert created.status_code == 201
    monkeypatch.setattr(documents, 'cleanup_file', lambda path: False)
    assert client.delete('/api/v1/documents/' + created.json()['id']).status_code == 503
    with ledgers[0].connection() as db:
        assert db.execute('SELECT state FROM document_erasures').fetchone()[0] == 'cleanup_pending'
    with sqlite3.connect(app.state.settings.lifecycle_authenticated_confirmation_path) as db:
        assert db.execute('SELECT count(*) FROM synthetic_transitions').fetchone()[0] == 3


def test_strict_reconciliation_refuses_destructive_execution(app, ledgers):
    from backend.maintenance import reconcile, reconciliation_plan
    enable(app, ledgers)
    app.state.settings.storage_dir.mkdir()
    residual = app.state.settings.storage_dir / ('a' * 32 + '.part')
    residual.write_bytes(b'synthetic')
    plan = reconciliation_plan(app.state.settings)
    with pytest.raises(ValueError, match='Destructive reconciliation disabled'):
        reconcile(app.state.settings, True, offline_confirmed=True, approved_plan_sha256=plan['plan_sha256'])
    assert residual.exists()


@pytest.mark.posix
def test_document_sql_failure_preserves_file_and_confirmed_receipt(client, app, ledgers, monkeypatch):
    from backend.models import Document
    from backend.services.documents import delete_document
    attach_legacy_owner(app)
    enable(app, ledgers)
    created = client.post('/api/v1/documents', files={'file': ('fiction.txt', b'fake document', 'text/plain')})
    assert created.status_code == 201
    with app.state.sessions() as session:
        document = session.scalar(select(Document))
        source = app.state.settings.storage_dir / document.storage_name
        monkeypatch.setattr(session, 'commit', lambda: (_ for _ in ()).throw(RuntimeError('synthetic commit error')))
        with pytest.raises(RuntimeError, match='synthetic commit error'):
            delete_document(session, app.state.settings, document)
    with app.state.sessions() as session:
        assert session.scalar(select(Document)) is not None
    assert source.exists()
    with sqlite3.connect(app.state.settings.lifecycle_authenticated_confirmation_path) as db:
        assert db.execute('SELECT count(*) FROM synthetic_transitions').fetchone()[0] == 3


def test_locked_confirmation_store_blocks_mutation(beta, ledgers):
    client, app, _ = beta
    verify_and_login(beta)
    enable(app, ledgers)
    with sqlite3.connect(ledgers[1].path) as connection:
        connection.execute('BEGIN EXCLUSIVE')
        assert client.post('/api/v1/account/deletion-request', json={'password': PASSWORD}).status_code == 503
    with app.state.sessions() as db:
        assert db.scalar(select(User)).disabled_at is None


@pytest.mark.posix
def test_confirmation_tampering_is_refused(ledgers):
    registry, store = ledgers
    coordinator = DurableCoordinator(registry, store)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    coordinator.confirm_account(receipt)
    with store.connection() as db:
        db.execute("UPDATE confirmations SET digest=?", ('0' * 64,))
    with pytest.raises(ValueError, match='Conflicting'):
        coordinator.confirm_account(receipt)


@pytest.mark.posix
def test_recovery_requires_matching_receipt_sets(ledgers):
    registry, store = ledgers
    coordinator = DurableCoordinator(registry, store)
    receipt = registry.receive('erasure', user_id=uuid4(), owner_id=uuid4())
    with pytest.raises(ValueError, match='sets differ'):
        coordinator.verify_recovery_receipts()
    coordinator.confirm_account(receipt)
    assert coordinator.verify_recovery_receipts()['opening_authorized'] is False
    with registry.connection() as db:
        db.execute('DELETE FROM requests WHERE id=?', (receipt,))
    with pytest.raises(ValueError, match='sets differ'):
        coordinator.verify_recovery_receipts()


@pytest.mark.posix
def test_recovery_rejects_unlinked_erasure_receipt(ledgers):
    registry, store = ledgers
    registry.receive('erasure')
    with pytest.raises(ValueError, match='Incomplete account receipt'):
        DurableCoordinator(registry, store).verify_recovery_receipts()


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permission proof')
@pytest.mark.parametrize('fault', ['permissions', 'symlink', 'hardlink'])
@pytest.mark.posix
def test_confirmation_rejects_unsafe_storage(ledgers, fault):
    registry, store = ledgers
    if fault == 'permissions':
        os.chmod(store.path, 0o644)
    elif fault == 'symlink':
        alias = store.path.parent / 'alias.sqlite'
        alias.symlink_to(store.path)
        store = ConfirmationStore(alias)
    else:
        os.link(store.path, store.path.parent / 'alias.sqlite')
    with pytest.raises(ValueError):
        DurableCoordinator(registry, store)


def test_admission_witness_reservation_and_divergence(ledgers):
    _, store = ledgers
    users = [uuid4() for _ in range(5)]
    for index, user in enumerate(users, 1):
        store.reserve_admission(index, user)
        store.reserve_admission(index, user)
    with pytest.raises(ValueError):
        store.reserve_admission(6, uuid4())
    with pytest.raises(ValueError, match='Conflicting'):
        store.reserve_admission(3, uuid4())
    assert store.restore_evidence(2) == {'minimum_issued_count': 5, 'witness_count': 5,
                                         'keep_registration_closed': True, 'opening_authorized': False,
                                         'reconciliation_required': True}


@pytest.mark.posix
def test_five_admissions_and_sixth_refused_in_strict_mode(beta, ledgers):
    client, app, sent = beta
    enable(app, ledgers)
    app.state.settings.public_registration_limit = 5
    for index in range(5):
        client.headers['X-Documind-Client-IP'] = f'192.0.2.{index + 1}'
        enroll(beta, f'fake-{index}@example.test')
    client.headers['X-Documind-Client-IP'] = '192.0.2.6'
    response = client.post('/api/v1/auth/register', json=signup_body(client, 'sixth@example.test'))
    assert response.status_code == 202 and sent.empty()
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 5
        account = db.scalar(select(User).where(User.email == 'fake-0@example.test'))
        account.disabled_at = now()
        db.add(DeletionRequest(user_id=account.id, owner_id=account.owner_id))
        db.commit()
        with pytest.raises(ValueError, match='Account purge disabled'):
            purge_account(db, app.state.settings, account.id)
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 5
        with pytest.raises(ValueError, match='Réouverture interdite'):
            registration_control(db, app.state.settings, 'reopen', execute=True)
    assert ledgers[1].restore_evidence(2)['minimum_issued_count'] == 5


def test_reservation_before_sql_rollback_blocks_new_identity(ledgers):
    _, store = ledgers
    first = uuid4()
    store.reserve_admission(1, first)
    with pytest.raises(ValueError, match='Conflicting'):
        store.reserve_admission(1, uuid4())
    assert store.restore_evidence(0)['minimum_issued_count'] == 1
    assert store.restore_evidence(0)['opening_authorized'] is False
    assert store.restore_evidence(3)['minimum_issued_count'] == 3


@pytest.mark.posix
def test_admission_response_lost_before_sql_commit_blocks_retry(beta, ledgers, monkeypatch):
    client, app, _ = beta
    enable(app, ledgers)
    app.state.settings.public_registration_limit = 5
    original = ConfirmationStore.reserve_admission
    def response_lost(self, count, user_id):
        original(self, count, user_id)
        raise OSError('synthetic response lost')
    monkeypatch.setattr(ConfirmationStore, 'reserve_admission', response_lost)
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'first@example.test')).status_code == 503
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 0
    monkeypatch.setattr(ConfirmationStore, 'reserve_admission', original)
    client.headers['X-Documind-Client-IP'] = '192.0.2.77'
    assert client.post('/api/v1/auth/register', json=signup_body(client, 'second@example.test')).status_code == 503
    assert ledgers[1].restore_evidence(0)['witness_count'] == 1


@pytest.mark.posix
def test_duplicate_after_success_does_not_consume_second_witness(beta, ledgers):
    client, app, sent = beta
    enable(app, ledgers)
    app.state.settings.public_registration_limit = 5
    enroll(beta, 'duplicate@example.test')
    response = client.post('/api/v1/auth/register', json=signup_body(client, 'duplicate@example.test'))
    assert response.status_code == 202 and sent.empty()
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
    assert ledgers[1].restore_evidence(0)['witness_count'] == 1


@pytest.mark.posix
def test_concurrent_last_admission_with_independent_witness(pg_beta, ledgers):
    _, parent, _ = pg_beta
    enable(parent, ledgers)
    seed(pg_beta, 4)
    before = counts(parent)
    with actors(pg_beta) as (instances, output):
        bodies = [signup_body(client, f'last-{index}@example.test')
                  for index, (client, _) in enumerate(instances)]
        with rendezvous(instances, lambda sql: sql.startswith('UPDATE public_registration_quota')) as pids:
            responses = parallel([lambda i=i: instances[i][0].post('/api/v1/auth/register', json=bodies[i])
                                  for i in range(2)])
        assert [response.status_code for response in responses] == [202, 202]
        assert len(set(pids)) == 2
        assert counts(parent) == tuple(value + 1 for value in before)
        assert output.get(timeout=3)[0].endswith('@example.test') and output.empty()
    assert ledgers[1].restore_evidence(4)['witness_count'] == 5


def test_encrypted_snapshot_integrity_and_wrong_key(ledgers):
    registry, _ = ledgers
    registry.receive('access')
    key = os.urandom(32)
    encrypted = encrypted_snapshot(registry, key)
    assert b'SQLite format' not in encrypted
    plaintext = verify_snapshot(encrypted, key)
    assert plaintext.startswith(b'SQLite format')
    with sqlite3.connect(':memory:') as db:
        db.deserialize(plaintext)
        assert db.execute('SELECT count(*) FROM requests').fetchone()[0] == 1
    with pytest.raises(InvalidTag):
        verify_snapshot(encrypted, os.urandom(32))
    corrupted = encrypted[:-1] + bytes([encrypted[-1] ^ 1])
    with pytest.raises(InvalidTag):
        verify_snapshot(corrupted, key)


def test_receipt_calendar_and_attested_backup_boundary():
    closed = datetime(2024, 2, 29, tzinfo=timezone.utc)
    neutral = datetime(2025, 2, 26, tzinfo=timezone.utc)
    common = {'coverage_attested': True, 'exceptions_complete': True, 'holds': []}
    plan = receipt_expiry_plan(closed, neutral, neutral, **common)
    assert plan['due_at'].startswith('2025-03-05') and not plan['eligible']
    assert receipt_expiry_plan(closed, neutral + timedelta(days=7), neutral, **common)['eligible']
    assert not receipt_expiry_plan(closed, neutral + timedelta(days=7), None,
                                   coverage_attested=False, exceptions_complete=True, holds=[])['eligible']


def test_active_and_invalid_holds_block():
    now = datetime(2026, 10, 27, tzinfo=timezone.utc)
    hold = {'id': str(uuid4()), 'responsible_id': str(uuid4()), 'scope_id': str(uuid4()),
            'reason': 'legal_hold', 'reviewed_at': now - timedelta(days=1),
            'review_at': now + timedelta(days=2), 'ends_at': now + timedelta(days=5), 'end_event': None}
    args = (now - timedelta(days=400), now, now - timedelta(days=30))
    assert receipt_expiry_plan(*args, coverage_attested=True, exceptions_complete=True, holds=[hold])['reason'] == 'active_hold'
    hold['review_at'] = now
    with pytest.raises(ValueError):
        receipt_expiry_plan(*args, coverage_attested=True, exceptions_complete=True, holds=[hold])
