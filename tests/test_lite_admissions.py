"""Synthetic contract authority ONLY. Never imported by application code."""
from contextlib import contextmanager
from dataclasses import replace
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
import itertools
import threading
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import SQLAlchemyError

from backend.config import Settings
from backend.main import create_app
from backend.account_api import issue_token
from backend.account_models import AccountToken, PublicRegistrationQuota, WorkspaceMembership
from backend.auth import User
from backend.models import now
from tests.conftest import BFF_KEY

PASSWORD = 'Lite-fictitious-password-2026!'
COHORT = UUID('ce30ca0c-70ab-4629-b1ea-bfeebbb2a001')


class SyntheticConfirmation:
    """In-memory test double, not an independent durable production authority."""
    cohort_id = COHORT

    def __init__(self):
        self.lock = threading.RLock()
        self.operations = {}
        self.reservations = {}
        self.results = {}
        self.fail_result_record = False

    @contextmanager
    def exclusive(self):
        with self.lock:
            yield

    def binding(self, op):
        return (op.id, op.cohort_id, op.invitation_digest, op.email_digest, op.user_id,
                op.owner_id, op.terms_version, op.terms_sha256, op.accepted_at,
                op.adult_declared, op.terms_accepted)

    def find(self, invitation, email):
        return next((o for o in self.operations.values()
                     if o.invitation_digest == invitation and o.email_digest == email), None)

    def for_user(self, user):
        return next((o for o in self.operations.values() if o.user_id == user), None)

    def prepare(self, op):
        self.operations[op.id] = op
        return op

    # These explicit approval controls exist only in this test module.
    def confirm_reservation(self, op, count):
        op.reserved_count = count + 1
        self.reservations[op.id] = (self.binding(op), count)
        op.state = 'reservation_confirmed'

    def reservation_verified(self, op, count):
        if any(o.state in ('uncertain', 'result_pending', 'sql_committed') for o in self.operations.values() if o.id != op.id):
            return False
        return self.reservations.get(op.id) == (self.binding(op), count)

    def committed(self, op, count):
        if self.fail_result_record:
            raise OSError('synthetic independent proof unavailable')
        if op.id not in self.reservations or count != op.reserved_count:
            raise ValueError('Unbound SQL result')
        if op.issued_count not in (None, count):
            raise ValueError('Conflicting result')
        op.issued_count = count
        op.state = 'result_pending'

    def confirm_result(self, op):
        assert op.issued_count is not None
        self.results[op.id] = (self.binding(op), op.issued_count)

    def result_verified(self, op):
        valid = self.results.get(op.id) == (self.binding(op), op.issued_count)
        if valid:
            op.state = 'admitted'
        return valid

    def uncertain(self, op):
        op.state = 'uncertain'

    def counter_verified(self, count):
        settled = max((op.issued_count or 0 for op in self.operations.values()), default=0)
        possible = {settled}
        possible.update(op.reserved_count for op in self.operations.values()
                        if op.id in self.reservations and op.state not in ('cancelled', 'refused')
                        and self.reservations[op.id][0] == self.binding(op))
        return count in possible and 0 <= count <= 5

    def reconcile(self, op, sql_evidence):
        # Test-only independent corroboration. Never a production approval API.
        if sql_evidence != {'account_absent': True, 'invitation_unused': True} or op.issued_count is not None:
            raise ValueError('Absence of commit must be corroborated')
        op.state = 'cancelled'


def lite_settings(base, **changes):
    fields = {**base.model_dump(), 'application_profile': 'beta_lite', 'lite_cohort_id': COHORT,
              'lite_terms_sha256': 'a'*64, 'registration_mode': 'invite', 'public_registration_limit': 5,
              'ai_enabled': False, 'owner_demo_enabled': False, 'legacy_api_enabled': False,
              'api_keys': {}, 'lifecycle_durable_receipts_required': True,
              'lifecycle_synthetic_mutations_enabled': False, 'public_legal_ready': True,
              'public_operator_name': 'Synthetic test operator', 'public_contact_email': 'operator@example.test',
              'public_terms_version': 'lite-test-v1', 'smtp_host': 'smtp.example.test',
              'smtp_from': 'test@example.test', 'public_terms_url': 'https://example.test/terms/v1',
              'public_privacy_url': 'https://example.test/privacy',
              'public_legal_notice_url': 'https://example.test/notice'}
    return Settings(_env_file=None, **{**fields, **changes})


@pytest.fixture
def lite(app):
    confirmation = SyntheticConfirmation()
    application = create_app(lite_settings(app.state.settings), lite_confirmation=confirmation)
    application.state.mail_sender = lambda *args: None
    # This explicitly synthetic fixture's isolated database only.
    with application.state.sessions() as db:
        db.execute(update(PublicRegistrationQuota).where(PublicRegistrationQuota.id == 'public').values(closed=False))
        db.commit()
    with TestClient(application) as client:
        client.headers.update({'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1'})
        yield client, application, confirmation


counter = itertools.count(1)


def send(client, body):
    return client.post('/api/v1/auth/register', json=body,
                       headers={'X-Documind-Client-IP': f'198.18.{next(counter)//250}.{next(counter)%250}'})


def invitation(application, email=None, ttl=86400):
    email = email or f'person-{uuid4().hex}@example.test'
    with application.state.sessions() as db:
        token = issue_token(db, 'invite', email, ttl)
        db.commit()
    return dict(email=email, password=PASSWORD, invitation=token, adult_declared=True,
                terms_accepted=True, terms_version='lite-test-v1')


def count(application):
    with application.state.sessions() as db:
        return db.get(PublicRegistrationQuota, 'public').issued_count


def prepare(lite, body=None):
    client, app, proof = lite
    body = body or invitation(app)
    result = send(client, body)
    assert result.status_code == 202, result.text
    assert result.json()['state'] == 'proposal_created' and not result.json()['created']
    op = proof.operations[UUID(result.json()['operation_id'])]
    return {**body, 'operation_id': str(op.id)}, op


def enroll(lite, body=None):
    client, app, proof = lite
    body, op = prepare(lite, body)
    proof.confirm_reservation(op, count(app))
    result = send(client, body)
    assert result.status_code == 202 and result.json()['state'] == 'result_pending', result.text
    proof.confirm_result(op)
    result = send(client, body)
    assert result.status_code == 201 and result.json()['created'], result.text
    return body, op


@pytest.mark.parametrize('change', [dict(lite_cohort_id=None), dict(registration_mode='public'),
    dict(application_profile='standard'),
    dict(public_registration_limit=6), dict(ai_enabled=True), dict(legacy_api_enabled=True),
    dict(owner_demo_enabled=True), dict(lifecycle_durable_receipts_required=False),
    dict(lifecycle_synthetic_mutations_enabled=True), dict(public_legal_ready=False),
    dict(lite_terms_sha256=''), dict(bff_service_key=''), dict(public_terms_url='http://example.test')])
def test_incomplete_or_permissive_profile_rejected(tmp_path, change):
    base = Settings(_env_file=None, recovery_state_path=tmp_path/'ready')
    with pytest.raises(ValidationError):
        lite_settings(base, **change)


def test_invitation_and_preparation_never_consume_capacity_or_leak_credentials(lite):
    client, app, proof = lite
    body = invitation(app)
    assert count(app) == 0
    body, op = prepare(lite, body)
    assert count(app) == 0
    response = send(client, body)
    assert response.status_code == 202 and count(app) == 0
    assert response.json()['state'] == 'reservation_pending'
    assert len(proof.operations) == 1
    exported = str(op.export()) + response.text + repr(op)
    assert PASSWORD not in exported and body['invitation'] not in exported
    assert op.password_hash not in str(op.export())


@pytest.mark.parametrize('change', [dict(adult_declared=False), dict(terms_accepted=False),
    dict(terms_version=''), dict(terms_version='old'), dict(invitation='x'*43), dict(email='wrong@example.test')])
def test_invalid_consent_version_or_invitation_refused(lite, change):
    client, app, proof = lite
    result = send(client, {**invitation(app), **change})
    assert result.status_code == 400
    assert count(app) == 0 and not proof.operations


@pytest.mark.parametrize('field', ['adult_declared', 'terms_accepted'])
def test_missing_declaration_refused(lite, field):
    client, app, proof = lite
    body = invitation(app); body.pop(field)
    assert send(client, body).status_code == 400
    body[field] = 'true'
    assert send(client, body).status_code == 422
    assert count(app) == 0


@pytest.mark.parametrize('kind', ['expired', 'used', 'revoked'])
def test_expired_used_revoked_invitation(lite, kind):
    client, app, _ = lite
    body = invitation(app, ttl=-1 if kind == 'expired' else 86400)
    if kind != 'expired':
        with app.state.sessions() as db:
            if kind == 'used': db.execute(update(AccountToken).values(used_at=now()))
            else: db.execute(delete(AccountToken))
            db.commit()
    assert send(client, body).status_code == 400 and count(app) == 0


def test_missing_or_wrong_cohort_confirmation_cannot_admit(lite):
    client, app, proof = lite
    body = invitation(app)
    for value in (None, SyntheticConfirmation()):
        if value: value.cohort_id = uuid4()
        app.state.lite_confirmation = value
        assert send(client, body).status_code == 503
    assert count(app) == 0


def test_runtime_configuration_cannot_bypass_strict_mode(lite):
    client, app, _ = lite
    body = invitation(app)
    app.state.settings.lifecycle_synthetic_mutations_enabled = True
    assert send(client, body).status_code == 503 and count(app) == 0


def test_pending_sql_account_cannot_login_or_use_a_forged_session(lite):
    client, app, proof = lite
    body, op = prepare(lite)
    proof.confirm_reservation(op, 0)
    result = send(client, body)
    assert result.status_code == 202 and count(app) == 1
    assert client.post('/api/v1/auth/login', json={'email': body['email'], 'password': PASSWORD}).status_code == 401
    with app.state.sessions() as db:
        user = db.get(User, op.user_id)
        assert user.disabled_at is None and user.terms_version == 'lite-test-v1'
        token = app.state.session_vault.create(user)
    assert client.get('/api/v1/account', headers={'Authorization': 'Bearer '+token}).status_code == 401
    proof.confirm_result(op)
    assert send(client, body).status_code == 201
    login = client.post('/api/v1/auth/login', json={'email': body['email'], 'password': PASSWORD})
    assert login.status_code == 200
    bearer = {'Authorization': 'Bearer '+login.json()['session_token']}
    assert client.get('/api/v1/account', headers=bearer).status_code == 200
    app.state.lite_confirmation = None
    assert client.get('/api/v1/account', headers=bearer).status_code == 401


def test_five_cumulative_admissions_sixth_and_deleted_account_do_not_recycle(lite):
    client, app, proof = lite
    operations = [enroll(lite)[1] for _ in range(5)]
    assert count(app) == 5
    with app.state.sessions() as db:
        db.execute(delete(User).where(User.id == operations[0].user_id))
        db.commit()  # Synthetic deletion only, not an enabled purge feature.
    assert count(app) == 5
    assert send(client, invitation(app)).status_code == 403
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 4
    assert proof.operations[operations[0].id].terms_accepted


def test_retry_payload_mismatch_response_loss_and_old_confirmation(lite):
    client, app, proof = lite
    body, op = enroll(lite)
    assert send(client, body).status_code == 201 and count(app) == 1
    for change in ({'password': PASSWORD+'changed'}, {'terms_version': 'other'}, {'operation_id': str(uuid4())}):
        assert send(client, {**body, **change}).status_code == 409
    second, other = prepare(lite)
    proof.reservations[other.id] = proof.reservations[op.id]
    assert send(client, second).status_code == 202
    assert count(app) == 1


@pytest.mark.parametrize('kind', ['expiry', 'terms', 'closed'])
def test_revalidation_after_waiting(lite, kind):
    client, app, proof = lite
    body, op = prepare(lite); proof.confirm_reservation(op, 0)
    with app.state.sessions() as db:
        if kind == 'expiry': db.execute(update(AccountToken).values(expires_at=now()-timedelta(seconds=1)))
        elif kind == 'closed': db.execute(update(PublicRegistrationQuota).values(closed=True))
        else: app.state.settings.public_terms_version = 'new'
        db.commit()
    assert send(client, body).status_code in (400, 403)
    assert count(app) == 0 and op.state == 'reservation_confirmed'


def test_commit_uncertainty_never_recycles_or_activates(lite, monkeypatch):
    from sqlalchemy.orm import Session
    client, app, proof = lite
    body, op = prepare(lite); proof.confirm_reservation(op, 0)
    original = Session.commit
    def lost_response(session):
        admitting = any(isinstance(obj, WorkspaceMembership) for obj in session.new)
        original(session)
        if admitting: raise SQLAlchemyError('synthetic lost COMMIT acknowledgement')
    with monkeypatch.context() as patch:
        patch.setattr(Session, 'commit', lost_response)
        assert send(client, body).status_code == 503
    assert count(app) == 1 and op.state == 'uncertain'
    assert send(client, body).status_code == 409
    assert client.post('/api/v1/auth/login', json={'email':body['email'], 'password':PASSWORD}).status_code == 401


def test_result_record_failure_recovers_without_a_second_admission(lite):
    client, app, proof = lite
    body, op = prepare(lite); proof.confirm_reservation(op, 0)
    proof.fail_result_record = True
    assert send(client, body).status_code == 503 and count(app) == 1
    proof.fail_result_record = False
    assert send(client, body).status_code == 202 and count(app) == 1
    proof.confirm_result(op)
    assert send(client, body).status_code == 201 and count(app) == 1


def test_restored_lower_counter_stays_closed(lite):
    client, app, proof = lite
    body, op = enroll(lite)
    with app.state.sessions() as db:
        db.execute(update(PublicRegistrationQuota).values(issued_count=0))
        db.commit()  # Deliberately corrupt a synthetic restored projection.
    assert send(client, invitation(app)).status_code == 409
    assert send(client, body).status_code == 409
    assert count(app) == 0  # No automatic repair/reset or reopened admission.


def test_missing_admission_history_cannot_be_inferred_from_sql_counter(lite):
    client, app, proof = lite
    with app.state.sessions() as db:
        db.execute(update(PublicRegistrationQuota).values(issued_count=3))
        db.commit()
    assert send(client, invitation(app)).status_code == 409
    assert count(app) == 3 and not proof.operations


def test_uncertain_reservation_requires_corroboration_before_cancellation(lite):
    client, app, proof = lite
    body, op = prepare(lite)
    proof.confirm_reservation(op, 0)
    proof.uncertain(op)
    assert send(client, body).status_code == 409 and count(app) == 0
    with pytest.raises(ValueError): proof.reconcile(op, {})
    with app.state.sessions() as db:
        assert db.get(User, op.user_id) is None
        assert db.scalar(select(AccountToken.used_at)) is None
    proof.reconcile(op, {'account_absent': True, 'invitation_unused': True})
    assert send(client, body).status_code == 409 and count(app) == 0
    # A distinct reissued invitation can be prepared; nothing decremented a quota.
    enroll(lite, invitation(app, email=body['email']))
    assert count(app) == 1


def test_result_confirmation_is_bound_and_disabled_account_never_reactivated(lite):
    client, app, proof = lite
    body, op = enroll(lite)
    other_body, other = prepare(lite)
    proof.confirm_reservation(other, 1)
    assert send(client, other_body).status_code == 202
    proof.results[other.id] = proof.results[op.id]
    assert send(client, other_body).status_code == 202
    assert client.post('/api/v1/auth/login', json={'email':other_body['email'], 'password':PASSWORD}).status_code == 401
    with app.state.sessions() as db:
        db.execute(update(User).where(User.id == op.user_id).values(disabled_at=now()))
        db.commit()
    assert send(client, body).status_code == 409
    with app.state.sessions() as db:
        assert db.get(User, op.user_id).disabled_at is not None


def test_client_cannot_self_approve_or_suppress_security_rate_limits(lite):
    client, app, proof = lite
    body = invitation(app)
    assert send(client, {**body, 'approved': True}).status_code == 422
    headers = {'X-Documind-Client-IP': '198.18.252.252'}
    for _ in range(5):
        assert client.post('/api/v1/auth/register', json={**body, 'adult_declared': False}, headers=headers).status_code == 400
    assert client.post('/api/v1/auth/register', json=body, headers=headers).status_code == 429
    assert count(app) == 0 and not proof.operations


def test_confirmation_handoffs_do_not_hold_sql_connections(lite, monkeypatch):
    client, app, proof = lite
    for name in ('prepare', 'reservation_verified', 'committed'):
        original = getattr(proof, name)
        def checked(*args, _original=original):
            assert app.state.engine.pool.checkedout() == 0
            return _original(*args)
        monkeypatch.setattr(proof, name, checked)
    body, op = enroll(lite)
    assert count(app) == 1 and send(client, body).status_code == 201


def test_success_shaped_projection_without_sql_or_proof_never_claims_creation(lite):
    client, app, proof = lite
    body, op = prepare(lite)
    op.state = 'admitted'
    assert send(client, body).status_code == 409
    assert count(app) == 0 and op.state == 'uncertain'


def test_postgresql_concurrent_last_slot(lite):
    client, app, proof = lite
    if app.state.engine.dialect.name != 'postgresql':
        pytest.skip('Requires the dedicated disposable PostgreSQL database')
    for _ in range(4): enroll(lite)
    requests = [prepare(lite) for _ in range(2)]
    for _, op in requests: proof.confirm_reservation(op, 4)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda row: send(client, row[0]).status_code, requests))
    assert sorted(results) == [202, 403] and count(app) == 5


@pytest.mark.parametrize('path', ['/ai/settings', '/ai/key', '/ai/status', '/search/status',
    '/search/semantic', '/documents/compare', '/comparisons/fake', '/documents/fake/index',
    '/documents/fake/summarize', '/documents/fake/summary-jobs', '/documents/fake/embeddings'])
def test_disabled_functions_are_denied_server_side(lite, path):
    client, _, _ = lite
    assert client.get('/api/v1'+path).status_code == 403
    assert client.post('/api/v1'+path, json={}).status_code == 403


def test_cli_rejects_ambiguous_targets_and_has_no_local_approval(lite, monkeypatch):
    from backend import account_admin
    _, app, _ = lite
    monkeypatch.setattr(account_admin, 'Settings', lambda: app.state.settings)
    monkeypatch.setattr(account_admin, 'make_engine', lambda *args: pytest.fail('Must refuse before database access'))
    for args in (['invite', 'person@example.test'], ['invite','person@example.test','--cohort',str(uuid4())],
                 ['public-registration','reopen','--execute'], ['purge',str(uuid4())],
                 ['lite-admissions',str(uuid4()),'--cohort',str(COHORT)]):
        monkeypatch.setattr('sys.argv', ['account-admin', *args])
        with pytest.raises(SystemExit): account_admin.main()
