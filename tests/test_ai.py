from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import func, select

from backend.ai.models import AIBudget, AIInteraction, AIReservation, AISource, AISummary, AIUsage
from backend.ai.providers import MockAIProvider, ProviderError, ProviderResult
from tests.conftest import OTHER_KEY


@pytest.fixture
def ai(client, app, monkeypatch):
    # No OpenAI HTTP request is possible in these tests, even if a real key exists in .env.
    import openai
    monkeypatch.setattr(openai, 'OpenAI', lambda **kwargs: pytest.fail('Real OpenAI client forbidden in tests'))
    app.state.settings.ai_enabled = True
    app.state.settings.openai_api_key = SecretStr('test-not-a-real-openai-key')
    app.state.settings.ai_requests_per_minute = 60
    provider = MockAIProvider()
    app.state.ai_provider = provider
    return client, app, provider


def upload(client, text=b'Docker utilise une API. Le projet comporte trois modules.'):
    response = client.post('/api/v1/documents', files={'file': ('synthetic.txt', text, 'text/plain')})
    assert response.status_code == 201, response.text
    return response.json()['id']


def payload(**extra):
    return {'consent': True, 'idempotency_key': str(uuid4()), **extra}


def test_ai_disabled_and_consent(client):
    identifier = upload(client)
    assert client.get('/api/v1/ai/status').json()['enabled'] is False
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).status_code == 403
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload(consent=False)).status_code == 422
    assert client.get(f'/api/v1/documents/{identifier}/summaries').json()['items'] == []


def test_summary_usage_idempotence_cache_and_sources(ai):
    client, app, provider = ai
    identifier = upload(client)
    request = payload()
    response = client.post(f'/api/v1/documents/{identifier}/summarize', json=request)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data['feature'] == 'summary' and data['content']['key_points']
    assert data['sources'][0]['page_number'] == 1
    assert 'Docker' in data['sources'][0]['excerpt']
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=request).json()['cached']
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).json()['id'] == data['id']
    assert len(provider.calls) == 1
    history = client.get(f'/api/v1/documents/{identifier}/summaries').json()
    assert history['total'] == 1 and history['items'][0]['id'] == data['id']
    stats = client.get('/api/v1/ai/status').json()
    assert stats['spent_usd'] > 0 and stats['reserved_usd'] == 0
    assert stats['input_tokens'] > 0 and stats['output_tokens'] == 120
    usage = client.get('/api/v1/ai/usage').json()
    assert usage['total'] == 1 and usage['items'][0]['estimated_usd'] > 0
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AIUsage)) == 1


def test_question_and_no_matching_information(ai):
    client, app, provider = ai
    identifier = upload(client)
    response = client.post(f'/api/v1/documents/{identifier}/ask', json=payload(question='Quels modules comporte le projet ?'))
    assert response.status_code == 200, response.text
    assert response.json()['sources'][0]['page_number'] == 1
    assert not response.json()['content']['insufficient_information']
    count = len(provider.calls)
    missing = client.post(f'/api/v1/documents/{identifier}/ask', json=payload(question='Quelle est la température à Neptune ?'))
    assert missing.status_code == 200 and missing.json()['content']['insufficient_information']
    assert missing.json()['sources'] == [] and len(provider.calls) == count
    assert client.get(f'/api/v1/documents/{identifier}/ai-history').json()['total'] == 2


@pytest.mark.parametrize('mode', ['invalid_source', 'invalid_schema', 'refusal', 'insufficient_with_sources'])
def test_invalid_provider_output_is_accounted_but_not_persisted(ai, mode):
    client, app, provider = ai
    identifier = upload(client)
    original = provider.generate
    def invalid(data, schema, request_id):
        response = original(data, schema, request_id)
        if mode == 'invalid_source': response.content['source_ids'] = [str(uuid4())]
        if mode == 'invalid_schema': response.content = {'unexpected': 'value'}
        if mode == 'refusal': response.valid_response = False
        if mode == 'insufficient_with_sources': response.content['insufficient_information'] = True
        return response
    provider.generate = invalid
    response = client.post(f'/api/v1/documents/{identifier}/ask', json=payload(question='Que contient le projet Docker ?'))
    assert response.status_code == 502, response.text
    assert client.get(f'/api/v1/documents/{identifier}/ai-history').json()['total'] == 0
    stats = client.get('/api/v1/ai/status').json()
    assert stats['spent_usd'] > 0 and stats['reserved_usd'] == 0


@pytest.mark.parametrize('code,http_status,uncertain', [('provider_rate_limit',429,False), ('provider_uncertain',503,True), ('provider_unavailable',503,True)])
def test_provider_errors_and_uncertain_reservations(ai, code, http_status, uncertain):
    client, app, provider = ai
    identifier = upload(client)
    calls = []
    def failing(*args):
        calls.append(1)
        raise ProviderError(code, http_status, uncertain)
    provider.generate = failing
    request = payload()
    response = client.post(f'/api/v1/documents/{identifier}/summarize', json=request)
    assert response.status_code == http_status
    again = client.post(f'/api/v1/documents/{identifier}/summarize', json=request)
    assert again.status_code == http_status and len(calls) == 1
    stats = client.get('/api/v1/ai/status').json()
    assert (stats['reserved_usd'] > 0) == uncertain


def test_quotas_budget_configuration_and_rate(ai):
    client, app, _ = ai
    identifier = upload(client)
    app.state.settings.ai_summary_quota = 0
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).json()['detail']['code'] == 'quota_reached'
    app.state.settings.ai_summary_quota = 20
    app.state.settings.ai_budget_usd = Decimal('0.00001')
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).status_code == 402
    app.state.settings.ai_budget_usd = Decimal(4)
    app.state.settings.ai_pricing_model = 'other'
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).json()['detail']['code'] == 'pricing_unverified'
    app.state.settings.ai_pricing_model = app.state.settings.openai_model
    app.state.settings.ai_requests_per_minute = 1
    assert client.post(f'/api/v1/documents/{identifier}/summarize', json=payload()).status_code == 200
    assert client.post(f'/api/v1/documents/{identifier}/ask', json=payload(question='Que contient Docker ?')).json()['detail']['code'] == 'rate_limit'


def test_long_document_rejected_without_call_and_hierarchical_summary(ai):
    client, app, provider = ai
    app.state.settings.ai_max_input_tokens = 6000
    app.state.settings.ai_max_summary_steps = 1
    app.state.settings.long_summary_max_calls = 1
    identifier = upload(client, ('Docker décrit le projet et ses modules.\n' * 170).encode())
    response = client.post(f'/api/v1/documents/{identifier}/summarize', json=payload())
    assert response.status_code == 413 and not provider.calls
    app.state.settings.ai_max_summary_steps = 5
    app.state.settings.long_summary_max_calls = 255
    response = client.post(f'/api/v1/documents/{identifier}/summarize', json=payload())
    assert response.status_code == 202, response.text
    from tests.test_long_summary import wait_job
    result = wait_job(client, response.json()['id'])
    assert result['status'] == 'completed', result['error_code']
    assert len(provider.calls) >= 3
    sent = {item['chunk_id'] for data, _ in provider.calls for item in data.get('passages', [])}
    with app.state.sessions() as db:
        from backend.models import DocumentChunk
        expected = set(str(value) for value in db.scalars(select(DocumentChunk.id).where(DocumentChunk.document_id == UUID(identifier))))
    assert sent == expected
    assert 'intégral' in result['result']['coverage']


def test_owner_isolation_and_cascades_preserve_financial_ledger(ai):
    client, app, _ = ai
    identifier = upload(client)
    client.post(f'/api/v1/documents/{identifier}/summarize', json=payload())
    client.post(f'/api/v1/documents/{identifier}/ask', json=payload(question='Que contient le projet ?'))
    key = client.headers['X-API-Key']
    client.headers['X-API-Key'] = OTHER_KEY
    assert client.get('/api/v1/ai/usage').json()['total'] == 0
    for suffix in ['summaries', 'ai-history']:
        assert client.get(f'/api/v1/documents/{identifier}/{suffix}').status_code == 404
    for suffix in ['summarize', 'ask']:
        assert client.post(f'/api/v1/documents/{identifier}/{suffix}', json=payload(**({'question':'Que contient Docker ?'} if suffix == 'ask' else {}))).status_code == 404
    client.headers['X-API-Key'] = key
    assert client.delete(f'/api/v1/documents/{identifier}').status_code == 204
    with app.state.sessions() as db:
        for table in (AISummary, AIInteraction, AISource):
            assert db.scalar(select(func.count()).select_from(table)) == 0
        assert db.scalar(select(func.count()).select_from(AIUsage)) == 2
        assert all(row.document_id is None for row in db.scalars(select(AIReservation)))
    assert client.get('/api/v1/ai/status').json()['spent_usd'] > 0


def test_concurrent_budget_reservation_and_duplicate_requests(ai):
    client, app, provider = ai
    first, second = upload(client), upload(client)
    settings = app.state.settings
    from backend.ai.service import cost
    settings.ai_budget_usd = cost(settings, settings.ai_max_input_tokens, settings.ai_max_output_tokens) * 2
    entered, release = Event(), Event()
    original = provider.generate
    def block(*args):
        entered.set()
        assert release.wait(10)
        return original(*args)
    provider.generate = block
    body = payload()
    with ThreadPoolExecutor(max_workers=2) as executor:
        pending = executor.submit(client.post, f'/api/v1/documents/{first}/summarize', json=body)
        assert entered.wait(10)
        try:
            assert client.post(f'/api/v1/documents/{first}/summarize', json=body).status_code == 409
            assert client.delete(f'/api/v1/documents/{first}').status_code == 409
            assert client.post(f'/api/v1/documents/{second}/summarize', json=payload()).status_code == 402
        finally:
            release.set()
        assert pending.result().status_code == 200
    assert len(provider.calls) == 1


def test_idempotency_key_cannot_change_question(ai):
    client, _, _ = ai
    identifier = upload(client)
    body = payload(question='Que contient le projet Docker ?')
    assert client.post(f'/api/v1/documents/{identifier}/ask', json=body).status_code == 200
    body['question'] = 'Quel est le budget Docker ?'
    assert client.post(f'/api/v1/documents/{identifier}/ask', json=body).status_code == 409
