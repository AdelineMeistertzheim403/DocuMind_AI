"""Synthetic qualification: legacy SQL capacity versus strict lifecycle blockers.

Passing legacy-profile cases DO NOT qualify production lifecycle for ten admissions.
"""
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.account_admin import registration_control
from backend.account_models import PublicRegistrationQuota
from backend.auth import User
from backend.main import create_app
from backend.lifecycle_admissions import configured_admissions
from backend.lifecycle_durability import ConfirmationStore
from tools.public_beta_policy import validate_registration_config, PublicBetaPolicyError
from tests.conftest import BFF_KEY
from tests.test_public_beta import beta, signup_body, PASSWORD
from tests.test_public_beta_postgresql_concurrency import actors, rendezvous, parallel


@pytest.fixture
def ten(beta, monkeypatch):
    client, app, sent = beta
    assert app.state.engine.dialect.name == 'postgresql'
    app.state.settings.public_registration_limit = 10
    # Simulate requests >60s apart, only for the rate-limiter module. No real sleep.
    import backend.resource_limits as limits
    clock = [10000.0]
    monkeypatch.setattr(limits, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    return beta, clock


def enroll_ten(ten, count):
    (client, app, sent), clock = ten
    for index in range(count):
        clock[0] += 61
        client.headers['X-Documind-Client-IP'] = f'192.0.2.{index+1}'
        email = f'synthetic-{index}@example.test'
        response = client.post('/api/v1/auth/register', json=signup_body(client, email))
        assert response.status_code == 202
        assert sent.get(timeout=3)[0] == email


def test_first_tenth_eleventh_no_recycling_and_no_numeric_public_count(ten):
    (client, app, sent), clock = ten
    enroll_ten(ten, 10)
    clock[0] += 61
    refused = client.post('/api/v1/auth/register', json=signup_body(client, 'eleventh@example.test'))
    assert refused.status_code == 202 and sent.empty()
    options = client.get('/api/v1/auth/options').json()
    assert options['public_registration_availability'] == 'full'
    assert options['public_capacity_configured'] is False
    assert 'issued_count' not in options and 'remaining' not in options
    with app.state.sessions() as db:
        quota = db.get(PublicRegistrationQuota, 'public')
        assert quota.issued_count == 10 and quota.closed is False
        users = db.scalars(select(User)).all()
        assert len(users) == 10 and all(u.email_verified_at is None for u in users)
        assert all(u.terms_version == 'beta-test-v1' and u.terms_accepted_at for u in users)
        db.delete(users[0]); db.commit()
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 10


def test_two_independent_http_instances_race_for_tenth(ten):
    beta, clock = ten
    client, parent, sent = beta
    enroll_ten(ten, 9)
    with actors(beta) as (instances, output):
        bodies = [signup_body(http, f'race-{i}@example.test') for i,(http,_) in enumerate(instances)]
        with rendezvous(instances, lambda sql: sql.startswith('UPDATE public_registration_quota')) as pids:
            results = parallel([lambda i=i: instances[i][0].post('/api/v1/auth/register', json=bodies[i]) for i in range(2)])
        assert len(set(pids)) == 2
        assert [r.status_code for r in results] == [202, 202]
        output.get(timeout=3)
        assert output.empty()
    with parent.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 10
        assert db.scalar(select(func.count()).select_from(User)) == 10


def test_new_api_instance_retains_counter_and_pending_account(ten):
    beta, clock = ten
    client, parent, sent = beta
    enroll_ten(ten, 1)
    application = create_app(parent.state.settings.model_copy())
    try:
        with TestClient(application) as fresh:
            fresh.headers.update({'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1'})
            assert fresh.get('/api/v1/auth/options').status_code == 200
            with application.state.sessions() as db:
                assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
                assert db.scalar(select(func.count()).select_from(User)) == 1
    finally:
        application.state.authentication_engine.dispose()
        application.state.engine.dispose()


def test_strict_mutations_refuse_signup_without_synthetic_opt_in(ten):
    (client, app, sent), clock = ten
    app.state.settings.lifecycle_durable_receipts_required = True
    app.state.settings.lifecycle_synthetic_mutations_enabled = False
    response = client.post('/api/v1/auth/register', json=signup_body(client))
    assert response.status_code == 503 and sent.empty()
    assert client.get('/api/v1/auth/options').json()['public_registration_availability'] == 'closed'
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 0


def test_strict_ten_limit_is_rejected_before_reading_keys(ten, tmp_path):
    (client, app, sent), clock = ten
    app.state.settings.lifecycle_admission_anchor_path = tmp_path / 'anchor.sqlite'
    app.state.settings.lifecycle_admission_key_path = tmp_path / 'synthetic.key'
    with pytest.raises(ValueError, match='five'):
        configured_admissions(app.state.settings, SimpleNamespace())


def test_durable_witness_sixth_sequence_is_rejected(tmp_path):
    store = ConfirmationStore(tmp_path / 'synthetic.sqlite')
    with pytest.raises(ValueError, match='sequence'):
        store.reserve_admission(6, uuid4())


def test_admin_cannot_reopen_ten_even_legacy_profile(ten):
    (client, app, sent), clock = ten
    with app.state.sessions() as db:
        registration_control(db, app.state.settings, 'close', True)
        with pytest.raises(ValueError, match='public/5'):
            registration_control(db, app.state.settings, 'reopen', True)
        assert db.get(PublicRegistrationQuota, 'public').closed is True
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 0


def test_delivery_policy_refuses_ten():
    with pytest.raises(PublicBetaPolicyError, match='five'):
        validate_registration_config({'REGISTRATION_MODE':'public','PUBLIC_REGISTRATION_LIMIT':'10'}, '0007', approved=True)
