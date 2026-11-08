"""Lifetime quota and pending-account identity, always using fictitious accounts."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, func

from backend.account_models import AccountToken, PublicRegistrationQuota, Workspace, WorkspaceMembership
from backend.auth import User, DUMMY_HASH, SessionVault
from backend.models import now
from tests.test_public_beta import beta, enroll, signup_body, PASSWORD


def new_request(client, email):
    client.headers['X-Documind-Client-IP'] = '192.0.2.' + str(1 + int(email.split('@')[0].encode().hex(), 16) % 200)
    return signup_body(client, email)


@pytest.mark.parametrize('invalid', ['missing', 'negative', 'above_limit'])
def test_invalid_quota_fails_closed_without_account_or_workspace(beta, invalid):
    client, app, sent = beta
    app.state.settings.public_registration_limit = 5
    with app.state.sessions() as db:
        quota = db.get(PublicRegistrationQuota, 'public')
        if invalid == 'missing':
            db.delete(quota)
        else:
            quota.issued_count = -1 if invalid == 'negative' else 6
        db.commit()
    assert client.get('/api/v1/auth/options').json()['public_capacity_configured'] is False
    result = client.post('/api/v1/auth/register', json=new_request(client, 'refused@example.test'))
    assert result.status_code == 202 and sent.empty()
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(User)) == 0
        assert db.scalar(select(func.count()).select_from(Workspace)) == 0


def test_administrative_disabled_timestamp_is_not_cleared_by_verification(beta):
    client, app, sent = beta
    token = enroll(beta)
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        user.disabled_at = now()  # Existing operator action, not an email-pending marker.
        owner = user.owner_id
        db.commit()
    response = client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD})
    assert response.status_code == 400
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        assert user.disabled_at is not None and user.email_verified_at is None and user.owner_id == owner
        assert db.get(Workspace, owner) is not None
        assert db.scalar(select(AccountToken).where(AccountToken.kind == 'verify')).used_at is None


def test_five_public_admissions_exclude_existing_and_invited_accounts(beta):
    from backend.account_api import issue_token
    client, app, sent = beta
    with app.state.sessions() as db:
        historical = User(owner_id=uuid4(), username='historical', email='historical@example.test', password_hash=DUMMY_HASH)
        db.add(historical)
        db.add(Workspace(owner_id=historical.owner_id))
        db.flush()
        db.add(WorkspaceMembership(user_id=historical.id, owner_id=historical.owner_id))
        invitation = issue_token(db, 'invite', 'invited@example.test', 3600)
        db.commit()
    app.state.settings.registration_mode = 'invite'
    invited = client.post('/api/v1/auth/register', json={'email': 'invited@example.test', 'password': PASSWORD, 'invitation': invitation})
    assert invited.status_code == 201
    app.state.settings.registration_mode = 'public'
    app.state.settings.public_registration_limit = 5
    for index in range(1, 6):
        email = f'public-{index}@example.test'
        response = client.post('/api/v1/auth/register', json=new_request(client, email))
        assert response.status_code == 202
        assert sent.get(timeout=3)[0] == email
        with app.state.sessions() as db:
            assert db.get(PublicRegistrationQuota, 'public').issued_count == index
            assert db.scalar(select(func.count()).select_from(User)) == 2 + index
            assert db.scalar(select(func.count()).select_from(Workspace)) == 2 + index
    refused = client.post('/api/v1/auth/register', json=new_request(client, 'sixth@example.test'))
    assert refused.status_code == 202 and refused.json() == response.json() and sent.empty()
    with app.state.sessions() as db:
        users = db.scalars(select(User).where(User.registration_kind == 'public')).all()
        assert len(users) == 5 and all(user.email_verified_at is None for user in users)
        users[0].disabled_at = now()
        db.delete(users[1])
        db.commit()
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 5
        assert db.scalar(select(func.count()).select_from(Workspace)) == 7
    assert client.post('/api/v1/auth/register', json=new_request(client, 'still-full@example.test')).status_code == 202
    assert sent.empty()


@pytest.mark.parametrize('invalid', ['expired', 'replayed', 'altered', 'password'])
def test_verification_errors_preserve_identity_and_token_atomicity(beta, invalid):
    client, app, sent = beta
    token = enroll(beta)
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        identity = (user.id, user.owner_id)
        if invalid == 'expired':
            db.scalar(select(AccountToken)).expires_at = now() - timedelta(seconds=1)
            db.commit()
    if invalid == 'replayed':
        assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 200
    response = client.post('/api/v1/auth/verify-email', json={
        'token': token if invalid != 'altered' else 'Z' * 43,
        'password': PASSWORD + '-wrong' if invalid == 'password' else PASSWORD})
    assert response.status_code == 400
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        assert (user.id, user.owner_id) == identity
        assert bool(user.email_verified_at) == (invalid == 'replayed')
        if invalid == 'password':
            assert db.scalar(select(AccountToken)).used_at is None
    if invalid == 'password':
        assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 200
    assert not app.state.session_vault.sessions  # Verification never logs the browser in.


def test_pending_block_release_invalidates_links_and_never_purges_or_consumes_a_slot(beta):
    from backend.account_admin import pending_account_control, purge_pending
    client, app, sent = beta
    token = enroll(beta)
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        identifier, owner = user.id, user.owner_id
        assert pending_account_control(db, identifier, 'block')['simulation']
        assert user.disabled_at is None
        result = pending_account_control(db, identifier, 'block', True)
        assert result['blocked'] and result['tokens_invalidated'] == 1
        user.created_at = now() - timedelta(hours=72)
        db.commit()
        assert purge_pending(db, app.state.settings, execute=True) == 0
    assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 400
    assert client.post('/api/v1/auth/login', json={'email': 'alice@example.test', 'password': PASSWORD}).status_code == 401
    assert client.post('/api/v1/auth/resend-verification', json=signup_body(client)).status_code == 202
    assert client.post('/api/v1/auth/forgot-password', json={'email': 'alice@example.test'}).status_code == 202
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.used_at.is_(None))) == 0
        assert db.get(Workspace, owner) is not None
        assert pending_account_control(db, identifier, 'release')['blocked']
        assert not pending_account_control(db, identifier, 'release', True)['blocked']
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
    assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 400
    response = client.post('/api/v1/auth/resend-verification', json=signup_body(client))
    assert response.status_code == 202
    address, fresh = sent.get(timeout=3)
    assert address == 'alice@example.test' and fresh != token
    assert client.post('/api/v1/auth/verify-email', json={'token': fresh, 'password': PASSWORD}).status_code == 200
    assert not app.state.session_vault.sessions
    with app.state.sessions() as db:
        with pytest.raises(ValueError):
            pending_account_control(db, identifier, 'block', True)
        assert db.get(User, identifier).email_verified_at is not None
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
