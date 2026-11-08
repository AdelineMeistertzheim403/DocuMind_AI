from types import SimpleNamespace
from uuid import UUID

import pytest
from pydantic import SecretStr
from fastapi import HTTPException

from backend.gateway import client_ip, secure_gateway, trusted_gateway
from backend.auth import User
from backend.models import now
from tests.conftest import BFF_KEY, KEY, OTHER_KEY
from tests.test_upload_admission import completed, multipart, raw_request


def test_legacy_api_key_cannot_authenticate_gateway():
    legacy_key = 'legacy-owner-test-key-0000000000000001'
    settings = SimpleNamespace(
        bff_service_key=SecretStr(''),
        api_keys={legacy_key: UUID(int=1)},
    )
    request = SimpleNamespace(
        headers={'x-api-key': legacy_key},
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
    )

    assert trusted_gateway(request) is False


def test_valid_bff_service_key_authenticates_gateway():
    service_key = 'test-bff-service-credential-000000000001'
    settings = SimpleNamespace(
        bff_service_key=SecretStr(service_key),
        api_keys={},
    )
    request = SimpleNamespace(
        headers={'x-api-key': service_key},
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
    )

    assert trusted_gateway(request) is True


def test_legacy_key_rejected_when_bff_key_exists():
    legacy_key = 'legacy-owner-test-key-0000000000000001'
    settings = SimpleNamespace(
        bff_service_key=SecretStr('test-bff-service-credential-000000000001'),
        api_keys={legacy_key: UUID(int=1)},
    )
    request = SimpleNamespace(
        headers={'x-api-key': legacy_key},
        app=SimpleNamespace(state=SimpleNamespace(settings=settings)),
    )

    assert trusted_gateway(request) is False


@pytest.mark.parametrize('service,key,secure,allowed', [
    ('', '', '1', False), ('', KEY, '1', False), ('', BFF_KEY, '1', False),
    (BFF_KEY, None, '1', False), (BFF_KEY, '', '1', False), (BFF_KEY, 'incorrect', '1', False),
    (BFF_KEY, KEY, '1', False), (BFF_KEY, OTHER_KEY, '1', False),
    (BFF_KEY, BFF_KEY, None, False), (BFF_KEY, BFF_KEY, '0', False),
    (BFF_KEY, BFF_KEY, 'true', False), (BFF_KEY, BFF_KEY, '1', True),
])
def test_secure_gateway_requires_dedicated_key_and_exact_secure_marker(service, key, secure, allowed):
    headers = {} if key is None else {'x-api-key': key}
    if secure is not None:
        headers['x-documind-secure'] = secure
    request = SimpleNamespace(headers=headers, app=SimpleNamespace(state=SimpleNamespace(
        settings=SimpleNamespace(bff_service_key=SecretStr(service), api_keys={KEY: UUID(int=1)}))))
    if allowed:
        assert secure_gateway(request) is None
    else:
        with pytest.raises(HTTPException) as failure:
            secure_gateway(request)
        assert failure.value.status_code == 403


@pytest.mark.parametrize('service,key,trusted', [
    ('', KEY, False), (BFF_KEY, KEY, False), (BFF_KEY, '', False),
    (BFF_KEY, 'incorrect', False), (BFF_KEY, BFF_KEY, True),
])
def test_only_bff_can_supply_client_ip(service, key, trusted):
    request = SimpleNamespace(
        headers={'x-api-key': key, 'x-documind-client-ip': '192.0.2.123'},
        client=SimpleNamespace(host='127.0.0.1'),
        app=SimpleNamespace(state=SimpleNamespace(settings=SimpleNamespace(
            bff_service_key=SecretStr(service), api_keys={KEY: UUID(int=1)}))))
    assert client_ip(request) == ('192.0.2.123' if trusted else '127.0.0.1')


@pytest.mark.parametrize('key', [KEY, 'incorrect', BFF_KEY])
def test_ip_admission_uses_only_gateway_authenticated_forwarding(app, client, monkeypatch, key):
    calls = []
    monkeypatch.setattr(app.state.rate_limiter, 'check', lambda bucket, *args: calls.append(bucket))
    response = client.get('/api/v1/documents', headers={'X-API-Key': key, 'X-Documind-Client-IP': '192.0.2.123'})
    assert response.status_code == (200 if key == KEY else 401)
    assert calls[0] == ('ip:192.0.2.123' if key == BFF_KEY else 'ip:testclient')


@pytest.fixture
def personal_session(app):
    with app.state.sessions() as db:
        user = User(owner_id=UUID(int=941), username='gateway-test', password_hash='unused-test-hash')
        db.add(user)
        db.commit()
        token = app.state.session_vault.create(user)
        return token, user.id


@pytest.mark.parametrize('key,marker,expected', [
    ('', '1', 403), ('incorrect', '1', 403), (KEY, '1', 403),
    (BFF_KEY, '', 403), (BFF_KEY, '0', 403), (BFF_KEY, '1', 204),
])
def test_preflight_requires_both_gateway_and_personal_session(client, personal_session, key, marker, expected):
    token, _ = personal_session
    response = client.get('/api/v1/internal/upload-admission', headers={
        'X-API-Key': key, 'X-Documind-Secure': marker, 'Authorization': 'Bearer ' + token})
    assert response.status_code == expected


@pytest.mark.parametrize('state', ['absent', 'invented', 'expired', 'revoked', 'disabled', 'owner_changed'])
def test_gateway_cannot_bypass_session_checks_or_early_upload_admission(app, client, personal_session, state):
    token, user_id = personal_session
    if state == 'expired':
        app.state.session_vault.resolve(token).expires_at = 0
    elif state == 'revoked':
        app.state.session_vault.revoke(token)
    elif state in {'disabled', 'owner_changed'}:
        with app.state.sessions() as db:
            user = db.get(User, user_id)
            if state == 'disabled':
                user.disabled_at = now()
            else:
                user.owner_id = UUID(int=942)
            db.commit()
    headers = {'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1'}
    if state != 'absent':
        headers['Authorization'] = 'Bearer ' + ('invented-session' if state == 'invented' else token)
    for path in ['/api/v1/documents', '/api/v1/ai/settings', '/api/v1/internal/upload-admission']:
        assert client.get(path, headers=headers).status_code == 401
    result = raw_request(app, {**headers, 'content-type': 'multipart/form-data; boundary=test'},
                         completed(multipart()))
    assert result['status'] == 401
    assert result['receive_calls'] == result['bytes'] == 0
    assert app.state.upload_capacity.active == app.state.upload_capacity.reserved == 0
    assert not list(app.state.settings.storage_dir.glob('*'))


@pytest.mark.parametrize('legacy_enabled', [True, False])
def test_legacy_identity_switch_is_independent_of_gateway(app, client, legacy_enabled):
    app.state.settings.legacy_api_enabled = legacy_enabled
    assert client.get('/api/v1/documents', headers={'X-API-Key': KEY}).status_code == (200 if legacy_enabled else 401)
    for key in [BFF_KEY, 'incorrect', '']:
        headers = {'X-API-Key': key, 'X-Documind-Secure': '1'}
        assert client.get('/api/v1/documents', headers=headers).status_code == 401
    assert client.get('/api/v1/account', headers={'X-API-Key': KEY, 'X-Documind-Secure': '1'}).status_code == 403


def test_bff_session_upload_owner_isolation_and_revocation(app, gateway_client, personal_session):
    client = gateway_client
    token, _ = personal_session
    app.state.settings.legacy_api_enabled = False
    client.headers.update({'Authorization': 'Bearer ' + token, 'X-Documind-Secure': '1'})
    assert client.get('/api/v1/internal/upload-admission').status_code == 204
    response = client.post('/api/v1/documents', files={'file': ('synthetic.txt', b'Synthetic gateway test.', 'text/plain')})
    assert response.status_code == 201, response.text
    identifier = response.json()['id']
    with app.state.sessions() as db:
        other = User(owner_id=UUID(int=943), username='other-gateway-test', password_hash='unused-test-hash')
        db.add(other)
        db.commit()
        other_token = app.state.session_vault.create(other)
    assert client.get('/api/v1/documents/' + identifier, headers={'Authorization': 'Bearer ' + other_token}).status_code == 404
    assert client.delete('/api/v1/documents/' + identifier, headers={'Authorization': 'Bearer ' + other_token}).status_code == 404
    assert client.get('/api/v1/documents/' + identifier).status_code == 200
    assert client.post('/api/v1/auth/logout', json={}).status_code == 200
    assert client.get('/api/v1/internal/upload-admission').status_code == 401
    assert client.get('/api/v1/documents/' + identifier).status_code == 401
