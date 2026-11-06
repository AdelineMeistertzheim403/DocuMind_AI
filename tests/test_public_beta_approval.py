"""Ten lifetime public admissions, local review and upgrade of existing accounts."""
import os
from uuid import UUID, uuid4

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import Column, MetaData, Table, Uuid, func, inspect, select, text, update

from backend.account_admin import public_account_control, registration_control
from backend.account_models import AccountToken, DeletionRequest, PublicRegistrationQuota
from backend.auth import DUMMY_HASH, User
from backend.config import Settings
from backend.db import make_engine
from backend.models import Document, now
from backend.public_registration import increment_quota
from tests.test_public_beta import beta, enroll, PASSWORD, PUBLIC
from tests.test_public_beta_state import new_request
from tests.test_upload_admission import raw_request, multipart, completed
from tests.conftest import BFF_KEY


@pytest.fixture
def reviewed_beta(beta):
    client, app, sent = beta
    app.state.settings = Settings(_env_file=None, **{
        **app.state.settings.model_dump(),
        'public_registration_limit': 10, 'public_registration_requires_approval': True,
        'public_registration_use_lifecycle_receipts': False,
        'lifecycle_durable_receipts_required': True,
    })
    return beta


def test_email_verification_requires_local_approval_before_every_authenticated_route(reviewed_beta):
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        identifier, owner = user.id, user.owner_id
        manufactured = app.state.session_vault.create(user)
        with pytest.raises(ValueError, match='vérifié'):
            public_account_control(db, identifier, 'approve', True)
    assert client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD}).status_code == 401
    verified = client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD})
    assert verified.json() == {'verified':True, 'approval_required':True}
    assert client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD}).status_code == 401
    assert client.get('/api/v1/account', headers={'Authorization':'Bearer '+manufactured}).status_code == 401
    with app.state.sessions() as db:
        manufactured = app.state.session_vault.create(db.get(User, identifier))
    result = raw_request(app, {'X-API-Key':BFF_KEY, 'Authorization':'Bearer '+manufactured}, completed(multipart()))
    assert result['status'] == 401 and result['receive_calls'] == 0
    with app.state.sessions() as db:
        simulation = public_account_control(db, identifier, 'approve')
        assert simulation['simulation'] and not simulation['approved']
        approved = public_account_control(db, identifier, 'approve', True)
        assert approved['approved'] and not approved['simulation']
        timestamp = db.get(User, identifier).approved_at
        public_account_control(db, identifier, 'approve', True)
        assert db.get(User, identifier).approved_at == timestamp
        assert db.get(User, identifier).owner_id == owner
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
    login = client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD})
    assert login.status_code == 200
    client.headers['Authorization'] = 'Bearer '+login.json()['session_token']
    assert client.get('/api/v1/account').status_code == 200
    document = client.post('/api/v1/documents', files={'file':('beta.txt', b'Fictitious beta document.')})
    assert document.status_code == 201, document.text
    assert client.post(f"/api/v1/documents/{document.json()['id']}/analyze", json={}).status_code == 201
    assert client.get('/api/v1/documents').json()['total'] == 1
    assert client.post('/api/v1/ai/key', json={'api_key':'fictitious-disabled-provider-key'}).status_code == 403
    # The simplified admission path must not disable unrelated erasure/recovery guards.
    assert client.delete('/api/v1/documents/'+document.json()['id']).status_code == 503
    with app.state.sessions() as db:
        retained = db.get(Document, UUID(document.json()['id']))
        assert retained is not None
        assert (app.state.settings.storage_dir / retained.storage_name).read_bytes() == b'Fictitious beta document.'
    assert client.post('/api/v1/account/deletion-request', json={'password':'wrong-password'}).status_code == 401
    assert client.post('/api/v1/account/deletion-request', json={'password':PASSWORD}).status_code == 503
    with app.state.sessions() as db:
        assert db.get(User, identifier).disabled_at is None
        assert db.scalar(select(func.count()).select_from(DeletionRequest)) == 0
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
        from backend.account_admin import purge_account
        with pytest.raises(ValueError, match='disabled'):
            purge_account(db, app.state.settings, identifier)
    assert client.get('/api/v1/account').status_code == 200
    assert client.post('/api/v1/auth/logout', json={}).status_code == 200
    assert client.get('/api/v1/account').status_code == 401


@pytest.mark.parametrize('after_approval', [False, True])
def test_rejection_revokes_access_and_tokens_without_recycling_a_place(reviewed_beta, after_approval):
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    if after_approval:
        assert client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD}).status_code == 200
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        if after_approval:
            public_account_control(db, user.id, 'approve', True)
        manufactured = app.state.session_vault.create(user)
        result = public_account_control(db, user.id, 'reject', True)
        assert result['blocked'] and not result['approved']
        with pytest.raises(ValueError):
            public_account_control(db, user.id, 'approve', True)
        assert db.scalar(select(func.count()).select_from(AccountToken).where(AccountToken.used_at.is_(None))) == 0
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
    assert client.get('/api/v1/account', headers={'Authorization':'Bearer '+manufactured}).status_code == 401
    assert client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD}).status_code == 401
    assert client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD}).status_code == 400


def test_review_does_not_reactivate_accounts_with_deletion_requests(reviewed_beta):
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    assert client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD}).status_code == 200
    with app.state.sessions() as db:
        user = db.scalar(select(User))
        db.add(DeletionRequest(user_id=user.id, owner_id=user.owner_id))
        db.commit()
        with pytest.raises(ValueError, match='suppression'):
            public_account_control(db, user.id, 'approve', True)
        assert user.approved_at is None


def test_password_recovery_does_not_bypass_administrative_approval(reviewed_beta):
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD})
    assert client.post('/api/v1/auth/forgot-password', json={'email':'alice@example.test'}).status_code == 202
    reset = sent.get(timeout=3)[1]
    assert client.post('/api/v1/auth/reset-password', json={'token':reset, 'password':PASSWORD+'new'}).status_code == 200
    assert client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD+'new'}).status_code == 401
    with app.state.sessions() as db:
        assert db.scalar(select(User)).approved_at is None


def test_ten_public_accounts_include_pending_rejected_and_deleted_but_not_legacy_or_invites(reviewed_beta):
    client, app, sent = reviewed_beta
    with app.state.sessions() as db:
        for kind in ('legacy', 'invite'):
            db.add(User(owner_id=uuid4(), username=kind, password_hash=DUMMY_HASH, registration_kind=kind))
        db.commit()
    for index in range(10):
        email = f'beta-{index}@example.test'
        assert client.post('/api/v1/auth/register', json=new_request(client, email)).status_code == 202
        assert sent.get(timeout=3)[0] == email
    assert client.get('/api/v1/auth/options').json()['public_registration_availability'] == 'full'
    # Avoid conflating the 10/minute anti-abuse ceiling with the lifetime quota.
    from backend.resource_limits import RateLimiter
    app.state.rate_limiter = RateLimiter()
    denied = client.post('/api/v1/auth/register', json=new_request(client, 'eleventh@example.test'))
    assert denied.status_code == 202 and sent.empty()
    with app.state.sessions() as db:
        users = db.scalars(select(User).where(User.registration_kind == 'public')).all()
        assert len(users) == 10 and all(user.approved_at is None for user in users)
        public_account_control(db, users[0].id, 'reject', True)
        db.delete(users[1])
        db.commit()
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 10
        assert increment_quota(db, 10000) is None
        registration_control(db, app.state.settings, 'close', True)
        with pytest.raises(ValueError, match='Aucune admission'):
            registration_control(db, app.state.settings, 'reopen', True)
    assert client.post('/api/v1/auth/register', json=new_request(client, 'no-recycled-place@example.test')).status_code == 202
    assert sent.empty()


def test_close_reopen_and_disabled_mode_keep_review_and_existing_login_available(reviewed_beta):
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    assert client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD}).status_code == 200
    with app.state.sessions() as db:
        public_account_control(db, db.scalar(select(User.id)), 'approve', True)
        registration_control(db, app.state.settings, 'close', True)
    assert client.post('/api/v1/auth/register', json=new_request(client, 'closed@example.test')).status_code == 202
    assert sent.empty()
    with app.state.sessions() as db:
        assert not registration_control(db, app.state.settings, 'reopen', True)['closed']
    assert client.post('/api/v1/auth/register', json=new_request(client, 'reopened@example.test')).status_code == 202
    sent.get(timeout=3)
    app.state.settings.registration_mode = 'disabled'
    assert client.post('/api/v1/auth/register', json=new_request(client, 'disabled@example.test')).status_code == 403
    assert client.post('/api/v1/auth/login', json={'email':'alice@example.test', 'password':PASSWORD}).status_code == 200


@pytest.mark.parametrize('guard', ['receipts', 'approval', 'recovery'])
def test_ten_account_reopening_preserves_other_safety_guards(reviewed_beta, guard):
    client, app, sent = reviewed_beta
    with app.state.sessions() as db:
        registration_control(db, app.state.settings, 'close', True)
        if guard == 'receipts':
            app.state.settings.public_registration_use_lifecycle_receipts = True
        elif guard == 'approval':
            app.state.settings.public_registration_requires_approval = False
        else:
            app.state.settings.recovery_state_path.write_text('{"format":1,"state":"quarantined"}', encoding='utf-8')
        with pytest.raises(ValueError):
            registration_control(db, app.state.settings, 'reopen', True)
        assert db.get(PublicRegistrationQuota, 'public').closed


def test_public_configuration_cannot_raise_the_server_ceiling():
    with pytest.raises(ValidationError, match='10 admissions'):
        Settings(_env_file=None, **{**PUBLIC, 'bff_service_key':BFF_KEY, 'public_registration_limit':11})


def test_approval_cli_is_dry_run_by_default_and_not_an_http_route(reviewed_beta, monkeypatch, capsys):
    from backend import account_admin
    client, app, sent = reviewed_beta
    token = enroll(reviewed_beta)
    client.post('/api/v1/auth/verify-email', json={'token':token, 'password':PASSWORD})
    with app.state.sessions() as db:
        identifier = db.scalar(select(User.id))
    monkeypatch.setattr(account_admin, 'Settings', lambda:app.state.settings)
    monkeypatch.setattr('sys.argv', ['account_admin', 'public-account', 'approve', str(identifier)])
    account_admin.main()
    assert '"simulation": true' in capsys.readouterr().out
    with app.state.sessions() as db:
        assert db.get(User, identifier).approved_at is None
    assert client.post('/api/v1/account/approve', json={'user_id':str(identifier)}).status_code == 404


@pytest.mark.parametrize('issued,public_count', [(0, 2), (7, 2), (12, 11)])
def test_migration_preserves_existing_data_closes_signup_and_never_reduces_lifetime_count(tmp_path, monkeypatch, issued, public_count):
    url = os.environ.get('TEST_DATABASE_URL', f'sqlite:///{(tmp_path / "upgrade.db").as_posix()}')
    engine = make_engine(url)
    assert not set(inspect(engine).get_table_names()) - {'alembic_version'}, 'Dedicated empty test DB required'
    monkeypatch.setenv('DATABASE_URL', url)
    config = Config('alembic.ini')
    command.upgrade(config, '0007')
    try:
        users = Table('users', MetaData(), Column('id', Uuid(), primary_key=True),
                      Column('owner_id', Uuid()), autoload_with=engine)
        with engine.begin() as connection:
            for index in range(public_count + 2):
                connection.execute(users.insert().values(id=uuid4(), owner_id=uuid4(),
                    username=f'prior-{index}', email=f'prior-{index}@example.test',
                    password_hash=DUMMY_HASH, ai_limit_usd=0, created_at=now(),
                    registration_kind='public' if index < public_count else ('legacy' if index == public_count else 'invite'),
                    email_verified_at=now(), disabled_at=now() if index == 0 else None))
            connection.execute(text('UPDATE public_registration_quota SET issued_count=:count, closed=false'), {'count':issued})
            before = [tuple(row) for row in connection.execute(select(users).order_by(users.c.id))]
        command.upgrade(config, 'head')
        command.upgrade(config, 'head')
        with engine.connect() as connection:
            assert [tuple(row) for row in connection.execute(select(users).order_by(users.c.id))] == before
            assert tuple(connection.execute(text('SELECT issued_count,closed FROM public_registration_quota')).one()) == (max(issued, public_count), True)
            assert connection.scalar(text('SELECT count(*) FROM users WHERE approved_at IS NOT NULL')) == 0
        with pytest.raises(RuntimeError, match='Downgrade refusé'):
            command.downgrade(config, '0007')
    finally:
        with engine.begin() as connection:
            connection.execute(text('DELETE FROM users'))
            connection.execute(update(PublicRegistrationQuota).values(issued_count=0))
        engine.dispose()
        command.downgrade(config, 'base')
