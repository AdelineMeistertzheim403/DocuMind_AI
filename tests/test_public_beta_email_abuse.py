"""Real loopback TLS, queue failures and default anti-abuse policy; fictitious data only."""
import queue
import json
import ssl
import threading
from email import policy
from email.parser import BytesParser
from types import SimpleNamespace

import pytest
from pydantic import SecretStr
from sqlalchemy import select

from backend.account_api import send_account_link
from backend.account_models import PublicRegistrationQuota
from backend.auth import User
from backend.config import Settings
from tests.fake_smtp import FakeSMTP, mail_certificate
from tests.test_public_beta import beta, signup_body, PASSWORD
from tests.test_security_audit import records, assert_private


def smtp_settings(port, starttls=False):
    return SimpleNamespace(smtp_host='127.0.0.1', smtp_port=port, smtp_starttls=starttls,
        smtp_from='sender@example.test', smtp_username='fictitious-user',
        smtp_password=SecretStr('fictitious-smtp-password'), account_base_url='https://localhost')


@pytest.mark.parametrize('starttls', [False, True])
def test_real_smtp_tls_verification_and_reset(mail_certificate, monkeypatch, starttls, capsys):
    original = ssl.create_default_context
    monkeypatch.setattr('backend.account_api.ssl.create_default_context',
                        lambda: original(cafile=str(mail_certificate[0])))
    with FakeSMTP(mail_certificate, starttls=starttls) as smtp:
        for verification in (True, False):
            send_account_link(smtp_settings(smtp.port, starttls), 'recipient@example.test',
                              'fictitious-token-never-logged', verification=verification)
            message = BytesParser(policy=policy.default).parsebytes(smtp.messages.get(timeout=3))
            route = 'verify-email' if verification else 'reset-password'
            assert f'https://localhost/{route}#token=fictitious-token-never-logged' in message.get_content()
            assert str(message['To']) == 'recipient@example.test'
        assert smtp.tls_connections == 2
        assert smtp.commands.count(b'AUTH') == 2
    output = capsys.readouterr()
    assert not output.out and not output.err


@pytest.mark.parametrize('starttls', [False, True])
def test_untrusted_certificate_never_sends_auth_or_message(mail_certificate, starttls):
    with FakeSMTP(mail_certificate, starttls=starttls) as smtp:
        with pytest.raises(ssl.SSLCertVerificationError):
            send_account_link(smtp_settings(smtp.port, starttls), 'recipient@example.test', 'fake-token')
        assert smtp.messages.empty() and b'AUTH' not in smtp.commands and b'DATA' not in smtp.commands


def test_worker_delivery_failure_is_private_and_resend_recovers(beta, records):
    client, app, sent = beta
    failed = threading.Event()
    def broken(email, token):
        failed.set()
        raise OSError(f'SECRET-SMTP {email} {token}')
    app.state.mail_sender = broken
    assert client.post('/api/v1/auth/register', json=signup_body(client)).status_code == 202
    assert failed.wait(3)
    app.state.mail_sender = lambda email, token: sent.put((email, token))
    assert client.post('/api/v1/auth/resend-verification', json=signup_body(client)).status_code == 202
    _, token = sent.get(timeout=3)
    assert client.post('/api/v1/auth/verify-email', json={'token': token, 'password': PASSWORD}).status_code == 200
    # Receipt of the second mail proves the single consumer finished the first failure.
    output = json.dumps(records)
    assert 'system.mail.failed' in output
    assert 'SECRET-SMTP' not in output and 'alice@example.test' not in output and token not in output
    assert_private(records, token)
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1


def test_full_queue_preserves_admission_and_reset_failure_is_logged(beta, records, monkeypatch):
    client, app, sent = beta
    def full(item):
        raise queue.Full
    # Keep the real consumer queue intact; only simulate producer saturation.
    with monkeypatch.context() as patch:
        patch.setattr(app.state.mail_queue,'put_nowait',full)
        assert client.post('/api/v1/auth/register', json=signup_body(client)).status_code == 202
        assert client.post('/api/v1/auth/forgot-password', json={'email': 'alice@example.test'}).status_code == 202
    assert sent.empty()
    output = json.dumps(records)
    assert sum(row['event']=='system.mail.failed' for row in records) == 2
    assert 'alice@example.test' not in output and PASSWORD not in output
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1
        assert db.scalar(select(User)).email_verified_at is None


@pytest.fixture
def default_beta(beta):
    client, app, _ = beta
    defaults = Settings(_env_file=None)
    app.state.settings.public_challenge_difficulty = defaults.public_challenge_difficulty
    app.state.settings.public_registration_per_hour = defaults.public_registration_per_hour
    app.state.settings.public_registration_limit = 5
    assert defaults.public_challenge_difficulty == 12 and defaults.public_registration_per_hour == 3
    return beta


def test_default_pow_nat_limit_is_three_not_five(default_beta):
    client, app, sent = default_beta
    for index in range(4):
        body = signup_body(client, f'nat-{index}@example.test')
        response = client.post('/api/v1/auth/register', json=body)
        assert response.status_code == (202 if index < 3 else 429)
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 3
    assert sent.qsize() <= 3


def test_default_email_limit_across_distinct_gateway_ips(default_beta):
    client, app, _ = default_beta
    for index in range(4):
        client.headers['X-Documind-Client-IP'] = f'192.0.2.{index+1}'
        response = client.post('/api/v1/auth/register', json=signup_body(client))
        assert response.status_code == (202 if index < 3 else 429)
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 1


def test_default_global_limit_even_for_invalid_proofs(default_beta):
    client, app, _ = default_beta
    for index in range(11):
        client.headers['X-Documind-Client-IP'] = f'192.0.2.{index+1}'
        # Invalid proofs are still charged to admission rate limits; no password hashing.
        response = client.post('/api/v1/auth/register', json={
            'email': f'global-{index}@example.test', 'password': PASSWORD,
            'terms_accepted': True, 'terms_version': 'beta-test-v1', 'proof': '0'})
        assert response.status_code == (202 if index < 10 else 429)
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 0


def test_default_pow_honeypot_consumes_nonce_and_replay_is_generic(default_beta):
    client, app, sent = default_beta
    body = signup_body(client, website='fictitious-bot')
    first = client.post('/api/v1/auth/register', json=body)
    second = client.post('/api/v1/auth/register', json={**body, 'website': ''})
    assert first.status_code == second.status_code == 202 and first.json() == second.json()
    assert sent.empty()
    with app.state.sessions() as db:
        assert db.get(PublicRegistrationQuota, 'public').issued_count == 0


@pytest.mark.parametrize('state,expected', [('available','available'), ('closed','closed'), ('full','full'), ('missing','closed'), ('negative','closed')])
def test_options_aggregate_availability_not_identity(beta, state, expected):
    client, app, _ = beta
    with app.state.sessions() as db:
        quota = db.get(PublicRegistrationQuota, 'public')
        if state == 'closed': quota.closed = True
        if state == 'full': quota.issued_count = app.state.settings.public_registration_limit
        if state == 'missing': db.delete(quota)
        if state == 'negative': quota.issued_count = -1
        db.commit()
    result = client.get('/api/v1/auth/options').json()
    assert result['public_registration_availability'] == expected
    assert result['public_capacity_configured'] == (expected == 'available')
    assert 'issued_count' not in result
