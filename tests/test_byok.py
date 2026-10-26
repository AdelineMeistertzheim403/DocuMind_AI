import time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select

from backend.auth import User, hash_password
from backend.ai.models import AIBudget, AIReservation
from backend.ai.providers import MockAIProvider
from tests.conftest import BFF_KEY

PASSWORD = 'test-password-minimum-12'
PERSONAL = 'test-personal-key-not-a-real-secret-12345'


@pytest.fixture
def accounts(gateway_client, app):
    # BYOK positive scenarios explicitly use the enabled feature, with a fake validator.
    app.state.settings.ai_enabled = True
    client = gateway_client
    with app.state.sessions() as db:
        for number, name in [(101, 'alice'), (202, 'bob')]:
            owner = UUID(int=number)
            db.add(User(owner_id=owner, username=name, password_hash=hash_password(PASSWORD)))
            db.add(AIBudget(id=f'byok:{owner}:openai'))
        db.commit()
    app.state.ai_key_validator = lambda key, model: None
    return client, app


def login(client, username):
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': PASSWORD}, headers={'X-API-Key': BFF_KEY, 'X-Documind-Secure': '1', 'Authorization': ''})
    assert response.status_code == 200, response.text
    token = response.json()['session_token']
    client.headers['X-API-Key'] = BFF_KEY
    client.headers['Authorization'] = f'Bearer {token}'
    client.headers['X-Documind-Secure'] = '1'
    return token


def connect(client):
    result = client.post('/api/v1/ai/key', json={'api_key': PERSONAL})
    assert result.status_code == 200, result.text
    assert PERSONAL not in result.text
    assert not result.json()['key_validated']
    return client.post('/api/v1/ai/key/validate', json={})


def test_https_session_key_validation_and_expiration(accounts):
    client, app = accounts
    assert client.post('/api/v1/ai/key', json={'api_key': PERSONAL}).status_code == 403
    token = login(client, 'alice')
    assert connect(client).json()['key_validated']
    result = client.get('/api/v1/ai/settings')
    assert result.json()['username'] == 'alice' and PERSONAL not in result.text
    context = app.state.session_vault.resolve(token)
    context.expires_at = time.time() - 1
    assert client.get('/api/v1/ai/settings').status_code == 401
    assert context.key is None


def test_keys_do_not_leak_in_validation_errors(accounts):
    client, app = accounts
    login(client, 'alice')
    invalid = 'short-sensitive-key'
    response = client.post('/api/v1/ai/key', json={'api_key': invalid})
    assert response.status_code == 422 and invalid not in response.text
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        assert PASSWORD not in user.password_hash


def test_byok_isolation_budgets_and_no_owner_key_fallback(accounts, monkeypatch):
    client, app = accounts
    app.state.settings.ai_enabled = True
    captured = []
    provider = MockAIProvider()
    def factory(settings):
        captured.append(settings.openai_api_key.get_secret_value())
        return provider
    monkeypatch.setattr('backend.ai.api.OpenAIProvider', factory)
    alice = login(client, 'alice')
    document = client.post('/api/v1/documents', files={'file': ('alice.txt', b'Docker utilise une API.')}).json()['id']
    assert connect(client).status_code == 200
    result = client.post(f'/api/v1/documents/{document}/summarize', json={'consent':True, 'idempotency_key':str(uuid4())})
    assert result.status_code == 200, result.text
    assert captured == [PERSONAL]
    assert client.get('/api/v1/ai/status').json()['mode'] == 'USER_BYOK'
    client.put('/api/v1/ai/settings', json={'mode':'USER_BYOK', 'limit_usd': 0})
    result = client.post(f'/api/v1/documents/{document}/ask', json={'consent':True, 'idempotency_key':str(uuid4()), 'question':'Que dit Docker ?'})
    assert result.status_code == 402
    bob = login(client, 'bob')
    assert client.get(f'/api/v1/documents/{document}').status_code == 404
    assert not client.get('/api/v1/ai/settings').json()['key_connected']
    assert client.get('/api/v1/ai/status').json()['spent_usd'] == 0
    client.headers['Authorization'] = f'Bearer {alice}'
    client.delete('/api/v1/ai/key')
    result = client.get('/api/v1/ai/settings').json()
    assert not result['key_connected']
    with app.state.sessions() as db:
        row = db.scalar(select(AIReservation))
        assert row.budget_id == f'byok:{UUID(int=101)}:openai'
        assert db.get(AIBudget, 'development').spent_usd == 0


def test_logout_revokes_key_and_session(accounts):
    client, app = accounts
    token = login(client, 'alice')
    connect(client)
    state = app.state.session_vault.resolve(token)
    assert client.post('/api/v1/auth/logout', json={}).status_code == 200
    assert state.key is None
    assert client.get('/api/v1/ai/settings').status_code == 401


def test_byok_concurrent_requests_cannot_exceed_personal_cap(accounts):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from backend.ai.service import cost
    client, app = accounts
    app.state.settings.ai_enabled = True
    login(client, 'alice'); connect(client)
    identifiers = [client.post('/api/v1/documents',files={'file':('test.txt', b'Docker utilise une API.')}).json()['id'] for _ in range(2)]
    limit = cost(app.state.settings, app.state.settings.ai_max_input_tokens, app.state.settings.ai_max_output_tokens) * 2
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username=='alice')); user.ai_limit_usd=limit; db.commit()
    entered, release = Event(), Event()
    provider = MockAIProvider()
    original = provider.generate
    def block(*args):
        entered.set(); assert release.wait(10); return original(*args)
    provider.generate=block; app.state.ai_provider=provider
    with ThreadPoolExecutor(max_workers=2) as executor:
        first=executor.submit(client.post, f'/api/v1/documents/{identifiers[0]}/summarize', json={'consent':True,'idempotency_key':str(uuid4())})
        assert entered.wait(10)
        try:
            second=client.post(f'/api/v1/documents/{identifiers[1]}/summarize',json={'consent':True,'idempotency_key':str(uuid4())})
            assert second.status_code==402
        finally: release.set()
        assert first.result().status_code==200
