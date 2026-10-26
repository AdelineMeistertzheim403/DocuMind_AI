"""Provider boundaries and authenticated routes: no real credentials or external calls."""
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import UUID

import pytest
from sqlalchemy import select, func

from backend.ai.providers import OpenAIProvider, ProviderError, MockAIProvider
from backend.ai.schemas import AnswerContent
from backend.ai.models import AIUsage, AIReservation
from backend.config import Settings
from backend.models import now
from backend.auth import User
from backend.rag.providers import OpenAIEmbeddingProvider, MockEmbeddingProvider, embed
from tests.test_byok import accounts, login, PERSONAL
from tests.test_ai import upload, payload
from tests.test_long_summary import long_text


@pytest.fixture(params=['legacy', 'public'])
def disabled_account(accounts, request, monkeypatch):
    client, app = accounts
    app.state.settings.ai_enabled = False
    with app.state.sessions() as db:
        user = db.scalar(select(User).where(User.username == 'alice'))
        user.registration_kind = request.param
        user.email_verified_at = now() if request.param == 'public' else None
        db.commit()
    token = login(client, 'alice')
    context = app.state.session_vault.resolve(token)
    context.key, context.validated, context.mode = PERSONAL, True, 'USER_BYOK'
    sdk = Mock(side_effect=AssertionError('External SDK construction forbidden'))
    monkeypatch.setattr('openai.OpenAI', sdk)
    app.state.ai_key_validator = Mock()
    app.state.ai_provider = MockAIProvider()
    app.state.embedding_provider = MockEmbeddingProvider()
    return client, app, context, sdk


def no_calls(app, sdk):
    sdk.assert_not_called()
    app.state.ai_key_validator.assert_not_called()
    assert app.state.ai_provider.calls == []
    assert app.state.embedding_provider.calls == []


def test_disabled_byok_connection_and_validation_do_not_touch_key_or_provider(disabled_account):
    client, app, context, sdk = disabled_account
    for path, body in [('/ai/key', {'api_key': 'fictitious-new-key-never-used-123456'}), ('/ai/key/validate', {})]:
        response = client.post('/api/v1' + path, json=body)
        assert response.status_code == 403, response.text
        assert response.json()['detail']['code'] == 'disabled'
        assert PERSONAL not in response.text
        assert context.key == PERSONAL and context.validated
    no_calls(app, sdk)
    assert client.get('/api/v1/ai/settings').status_code == 200
    assert client.delete('/api/v1/ai/key').status_code == 200
    assert context.key is None and not context.validated
    assert client.post('/api/v1/auth/logout', json={}).status_code == 200
    no_calls(app, sdk)


def test_disabled_generation_matrix_and_local_document_functions(disabled_account):
    client, app, context, sdk = disabled_account
    first = upload(client)
    second = upload(client, b'Docker utilise PostgreSQL. Le budget fictif est different.')
    long_id = upload(client, long_text())
    for path, body in [
        (f'/documents/{first}/summarize', payload()),
        (f'/documents/{first}/ask', payload(question='Que dit Docker ?')),
        (f'/documents/{long_id}/summary-jobs', payload()),
        (f'/documents/{long_id}/summarize', payload()),
        (f'/documents/{first}/index', payload()),
        ('/search/ask', payload(document_ids=[first], query='Docker API', semantic=True)),
    ]:
        response = client.post('/api/v1' + path, json=body)
        assert response.status_code == 403, (path, response.text)
    comparison = client.post('/api/v1/documents/compare', json={'document_a': first, 'document_b': second})
    assert comparison.status_code == 200, comparison.text
    response = client.post(f"/api/v1/comparisons/{comparison.json()['id']}/summarize", json=payload())
    assert response.status_code == 403, response.text
    assert client.post('/api/v1/search/semantic', json=payload(document_ids=[first], query='Docker API', semantic=True)).status_code == 200
    assert client.post(f'/api/v1/documents/{first}/analyze', json={}).status_code == 201
    import pymupdf
    with pymupdf.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Fictitious local PDF for disabled AI tests.')
        imported = client.post('/api/v1/documents', files={'file': ('fictitious.pdf', pdf.tobytes(), 'application/pdf')})
    assert imported.status_code == 201
    assert client.get(f"/api/v1/documents/{imported.json()['id']}").json()['pages'][0]['text']
    for path in [f'/documents/{first}', f'/documents/{first}/analysis', f'/documents/{first}/summaries',
                 f'/documents/{first}/ai-history', '/ai/usage', '/ai/status', '/account']:
        assert client.get('/api/v1' + path).status_code == 200, path
    assert client.delete(f'/api/v1/documents/{second}').status_code == 204
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AIUsage)) == 0
        assert db.scalar(select(func.count()).select_from(AIReservation)) == 0
    no_calls(app, sdk)


def test_disabled_queued_summary_keeps_checkpoint_allows_cancel_not_resume(disabled_account, monkeypatch):
    from backend.ai.long_models import LongSummaryJob
    client, app, context, sdk = disabled_account
    identifier = upload(client, long_text())
    # Setup only: admit a job with mocked providers, without allowing the worker to dispatch it.
    app.state.settings.ai_enabled = True
    monkeypatch.setattr(app.state.summary_worker, 'submit', Mock())
    response = client.post(f'/api/v1/documents/{identifier}/summary-jobs', json=payload())
    assert response.status_code == 202, response.text
    job = response.json()['id']
    app.state.settings.ai_enabled = False
    app.state.summary_worker.run(UUID(job), context)
    with app.state.sessions() as db:
        saved = db.get(LongSummaryJob, UUID(job))
        assert saved.status == 'partial' and saved.error_code == 'disabled' and saved.completed_steps == 0
    assert client.post(f'/api/v1/summary-jobs/{job}/resume', json=payload()).status_code == 403
    assert client.get(f'/api/v1/summary-jobs/{job}').status_code == 200
    assert client.post(f'/api/v1/summary-jobs/{job}/cancel', json={}).status_code == 200
    with app.state.sessions() as db:
        reservation = db.get(AIReservation, saved.reservation_id)
        assert reservation.status != 'reserved' and reservation.provider_calls == 0
    no_calls(app, sdk)


def test_disabled_index_worker_never_invokes_embedding_provider(disabled_account, monkeypatch):
    from backend.rag.indexing import run_job
    from backend.rag.models import IndexJob
    client, app, context, sdk = disabled_account
    identifier = upload(client)
    app.state.settings.ai_enabled = True
    scheduled = Mock()
    monkeypatch.setattr('backend.rag.api.run_job', scheduled)
    response = client.post(f'/api/v1/documents/{identifier}/index', json=payload())
    assert response.status_code == 202, response.text
    admitted = app.state.settings.model_copy()
    app.state.settings.ai_enabled = False
    run_job(app, UUID(response.json()['id']), context, admitted)
    with app.state.sessions() as db:
        job = db.get(IndexJob, UUID(response.json()['id']))
        assert job.error_code == 'disabled'
        assert db.scalar(select(func.count()).select_from(AIUsage)) == 0
    no_calls(app, sdk)


@pytest.mark.parametrize('provider_class', [OpenAIProvider, OpenAIEmbeddingProvider])
def test_disabled_provider_constructor_does_not_construct_sdk(provider_class, monkeypatch):
    sdk = Mock()
    monkeypatch.setattr('openai.OpenAI', sdk)
    with pytest.raises(ProviderError) as caught:
        provider_class(Settings(_env_file=None, ai_enabled=False))
    assert caught.value.code == 'disabled' and caught.value.attempts == 0
    sdk.assert_not_called()


def test_captured_configuration_cannot_override_live_disabled_provider_boundary(disabled_account):
    from backend.ai.api import ConfiguredProvider
    client, app, context, sdk = disabled_account
    snapshot = app.state.settings.model_copy(update={'ai_enabled': True})
    request = SimpleNamespace(app=app, state=SimpleNamespace(user_session=context))
    with pytest.raises(ProviderError, match='disabled'):
        ConfiguredProvider(request, snapshot).generate({}, AnswerContent, 'fictitious')
    with pytest.raises(ProviderError, match='disabled'):
        embed(app, snapshot, ['Fictitious text'], 'fictitious')
    no_calls(app, sdk)


def test_disabled_historical_results_and_indexed_search_remain_local(disabled_account):
    client, app, context, sdk = disabled_account
    identifier = upload(client)
    app.state.settings.ai_enabled = True  # Fictitious setup, injected mock provider only.
    generated = client.post(f'/api/v1/documents/{identifier}/summarize', json=payload())
    assert generated.status_code == 200, generated.text
    indexed = client.post(f'/api/v1/documents/{identifier}/index', json=payload())
    assert indexed.status_code == 202, indexed.text
    assert app.state.ai_provider.calls and app.state.embedding_provider.calls
    app.state.ai_provider.calls.clear()
    app.state.embedding_provider.calls.clear()
    app.state.settings.ai_enabled = False
    history = client.get(f'/api/v1/documents/{identifier}/summaries')
    assert history.status_code == 200 and history.json()['items'][0]['id'] == generated.json()['id']
    result = client.post('/api/v1/search/semantic', json=payload(document_ids=[identifier], query='Docker API', semantic=True))
    assert result.status_code == 200 and result.json()['strategy'] == 'lexical'
    with app.state.sessions() as db:
        usage_before = db.scalar(select(func.count()).select_from(AIUsage))
    cached = client.post(f'/api/v1/documents/{identifier}/summarize', json=payload())
    assert cached.status_code == 200 and cached.json()['cached']
    with app.state.sessions() as db:
        assert db.scalar(select(func.count()).select_from(AIUsage)) == usage_before
    no_calls(app, sdk)


@pytest.mark.parametrize('embedding', [False, True])
def test_existing_sdk_client_is_not_used_after_disabling(embedding):
    settings = Settings(_env_file=None, ai_enabled=True)
    call = Mock()
    client = SimpleNamespace(responses=SimpleNamespace(create=call), embeddings=SimpleNamespace(create=call))
    provider = OpenAIEmbeddingProvider(settings, client) if embedding else OpenAIProvider(settings, client)
    settings.ai_enabled = False
    with pytest.raises(ProviderError, match='disabled') as caught:
        if embedding:
            provider.embed(['Fictitious text'], 'test')
        else:
            provider.generate({}, AnswerContent, 'test')
    assert caught.value.attempts == 0
    call.assert_not_called()


def test_disabled_before_retry_preserves_the_real_attempt_count(monkeypatch):
    import httpx
    import openai
    settings = Settings(_env_file=None, ai_enabled=True)
    calls = []
    def create(**kwargs):
        calls.append(kwargs)
        settings.ai_enabled = False
        response = httpx.Response(429, request=httpx.Request('POST', 'https://example.test/responses'))
        raise openai.RateLimitError('Fictitious rejection', response=response, body={})
    provider = OpenAIProvider(settings, SimpleNamespace(responses=SimpleNamespace(create=create)))
    with pytest.raises(ProviderError, match='disabled') as caught:
        provider.generate({}, AnswerContent, 'test')
    assert len(calls) == 1 and caught.value.attempts == 1 and not caught.value.uncertain


def test_enabled_metadata_validation_keeps_explicit_sdk_behavior_with_fake_client(disabled_account, monkeypatch):
    client, app, context, sdk = disabled_account
    app.state.settings.ai_enabled = True
    app.state.ai_key_validator = None
    retrieve = Mock()
    fake = SimpleNamespace(models=SimpleNamespace(retrieve=retrieve))
    manager = Mock()
    manager.__enter__ = Mock(return_value=fake)
    manager.__exit__ = Mock(return_value=False)
    constructor = Mock(return_value=manager)
    monkeypatch.setattr('openai.OpenAI', constructor)
    result = client.post('/api/v1/ai/key/validate', json={})
    assert result.status_code == 200 and result.json()['key_validated']
    constructor.assert_called_once()
    retrieve.assert_called_once_with(app.state.settings.openai_model)
    assert PERSONAL not in result.text


def test_disabling_between_summary_steps_preserves_billed_checkpoint_and_cancel(disabled_account):
    from tests.test_long_summary import wait_job
    from backend.ai.long_models import LongSummaryJob
    from backend.ai.models import AIBudget
    client, app, context, sdk = disabled_account
    identifier = upload(client, long_text())
    original = app.state.ai_provider.generate
    def generate_then_disable(*args):
        result = original(*args)
        app.state.settings.ai_enabled = False
        return result
    app.state.ai_provider.generate = generate_then_disable
    app.state.settings.ai_enabled = True
    started = client.post(f'/api/v1/documents/{identifier}/summary-jobs', json=payload())
    assert started.status_code == 202, started.text
    identifier = started.json()['id']
    job = wait_job(client, identifier, ('partial',))
    assert job['error_code'] == 'disabled' and job['completed_steps'] == 1
    assert len(app.state.ai_provider.calls) == 1
    assert client.post(f'/api/v1/summary-jobs/{identifier}/resume', json=payload()).status_code == 403
    assert client.post(f'/api/v1/summary-jobs/{identifier}/cancel', json={}).status_code == 200
    with app.state.sessions() as db:
        saved = db.get(LongSummaryJob, UUID(identifier))
        reservation = db.get(AIReservation, saved.reservation_id)
        assert db.scalar(select(func.count()).select_from(AIUsage)) == 1
        assert reservation.provider_calls == 1
        assert db.get(AIBudget, reservation.budget_id).reserved_usd == 0
    assert len(app.state.ai_provider.calls) == 1 and not app.state.embedding_provider.calls
    sdk.assert_not_called()
